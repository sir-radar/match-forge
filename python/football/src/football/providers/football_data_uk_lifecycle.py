from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor

from football.contracts.source import canonical_json_bytes
from football.ingestion.registration import RegisteredSource
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.providers.football_data_uk_evidence import FootballDataUkAcquisitionEvidenceV1
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1

_POLICY_VERSION = "football-data-uk-phase1b-frozen-sync-v1"
LifecycleRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class FootballDataUkLifecycleRegistrationError(ValueError):
    """Frozen Football-Data lifecycle evidence conflicts with stored records."""


@dataclass(frozen=True, slots=True)
class RegisteredFootballDataUkLifecycleV1:
    sync_run_id: UUID
    acquisition_job_ids: dict[str, UUID]
    acquired_resource_ids: dict[str, UUID]
    status: LifecycleRegistrationStatusV1


class FootballDataUkPostgresLifecycleRegistryV1:
    """Register frozen acquisition lifecycle rows idempotently."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        source: RegisteredSource,
        evidence: FootballDataUkAcquisitionEvidenceV1,
    ) -> RegisteredFootballDataUkLifecycleV1:
        _verify_source_provider(cursor, source)
        _verify_source_resources(source, evidence)
        sync_run_id, sync_inserted = self._sync_run(cursor, source.provider_id, evidence)
        job_ids: dict[str, UUID] = {}
        acquired_ids: dict[str, UUID] = {}
        inserted = sync_inserted
        for receipt in evidence.receipts:
            job_id, job_inserted = self._job(cursor, sync_run_id, source.provider_id, receipt)
            acquired_id, resource_inserted = self._resource(
                cursor,
                job_id,
                source.snapshot_id,
                source.resource_ids[receipt.source_path],
                receipt,
            )
            job_ids[receipt.source_path] = job_id
            acquired_ids[receipt.source_path] = acquired_id
            inserted = inserted or job_inserted or resource_inserted
        status: LifecycleRegistrationStatusV1 = "inserted" if inserted else "verified_existing"
        return RegisteredFootballDataUkLifecycleV1(
            sync_run_id=sync_run_id,
            acquisition_job_ids=job_ids,
            acquired_resource_ids=acquired_ids,
            status=status,
        )

    @staticmethod
    def _sync_run(
        cursor: Cursor[Any],
        provider_id: UUID,
        evidence: FootballDataUkAcquisitionEvidenceV1,
    ) -> tuple[UUID, bool]:
        started_at = min(_request_started_at(receipt) for receipt in evidence.receipts)
        completed_at = max(receipt.observed_by_matchforge_at for receipt in evidence.receipts)
        values = (
            provider_id,
            _POLICY_VERSION,
            "succeeded",
            _run_key(evidence),
            started_at,
            completed_at,
            None,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.provider_sync_runs
                (provider_id, policy_version, status, run_key, started_at, completed_at,
                 error_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, provider_id, policy_version, status, run_key, started_at, completed_at,
                   error_code
            FROM football.provider_sync_runs
            WHERE run_key = %s
            """,
            (_run_key(evidence),),
        ).fetchone()
        if row is None or row[1:] != values:
            raise FootballDataUkLifecycleRegistrationError(
                "provider sync run conflicts with frozen lifecycle evidence"
            )
        return UUID(str(row[0])), inserted == 1

    @staticmethod
    def _job(
        cursor: Cursor[Any],
        sync_run_id: UUID,
        provider_id: UUID,
        receipt: FootballDataUkSourceResourceV1,
    ) -> tuple[UUID, bool]:
        values = (
            sync_run_id,
            provider_id,
            receipt.resource_type,
            _scope_key(receipt),
            receipt.source_path,
            receipt.raw_sha256,
            "acquired",
            1,
            None,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.acquisition_jobs
                (sync_run_id, provider_id, resource_key, scope_key, resource_identity,
                 resource_revision, status, attempt_count, last_error_code)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_id, resource_key, scope_key, resource_identity,
                         resource_revision) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, sync_run_id, provider_id, resource_key, scope_key, resource_identity,
                   resource_revision, status, attempt_count, last_error_code
            FROM football.acquisition_jobs
            WHERE provider_id = %s AND resource_key = %s AND scope_key = %s
              AND resource_identity = %s AND resource_revision = %s
            """,
            values[1:6],
        ).fetchone()
        if row is None or row[1:] != values:
            raise FootballDataUkLifecycleRegistrationError(
                f"acquisition job conflicts with frozen resource: {receipt.source_path}"
            )
        return UUID(str(row[0])), inserted == 1

    @staticmethod
    def _resource(
        cursor: Cursor[Any],
        job_id: UUID,
        snapshot_id: UUID,
        source_resource_id: UUID,
        receipt: FootballDataUkSourceResourceV1,
    ) -> tuple[UUID, bool]:
        values = (
            job_id,
            snapshot_id,
            source_resource_id,
            FootballDataUkRawStoreV1.relative_path(receipt),
            receipt.raw_sha256,
            receipt.raw_byte_size,
            "acquired",
            receipt.observed_by_matchforge_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.acquired_resources
                (acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
                 raw_sha256, size_bytes, status, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_resource_id) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, acquisition_job_id, source_snapshot_id, source_resource_id, raw_path,
                   raw_sha256, size_bytes, status, acquired_at
            FROM football.acquired_resources
            WHERE source_resource_id = %s
            """,
            (source_resource_id,),
        ).fetchone()
        if row is None or row[1:] != values:
            raise FootballDataUkLifecycleRegistrationError(
                f"acquired resource conflicts with frozen bytes: {receipt.source_path}"
            )
        return UUID(str(row[0])), inserted == 1


def _verify_source_resources(
    source: RegisteredSource,
    evidence: FootballDataUkAcquisitionEvidenceV1,
) -> None:
    receipt_paths = {receipt.source_path for receipt in evidence.receipts}
    if set(source.resource_ids) != receipt_paths:
        raise FootballDataUkLifecycleRegistrationError(
            "registered source resources do not match frozen receipt paths"
        )


def _verify_source_provider(cursor: Cursor[Any], source: RegisteredSource) -> None:
    row = cursor.execute(
        """
        SELECT provider.code
        FROM football.source_snapshots AS snapshot
        JOIN football.providers AS provider ON provider.id = snapshot.provider_id
        WHERE snapshot.id = %s AND snapshot.provider_id = %s
        """,
        (source.snapshot_id, source.provider_id),
    ).fetchone()
    if row != ("football_data_uk",):
        raise FootballDataUkLifecycleRegistrationError(
            "registered source is not a Football-Data snapshot for its provider"
        )


def _run_key(evidence: FootballDataUkAcquisitionEvidenceV1) -> str:
    payload = canonical_json_bytes(
        {
            "provider_id": "football_data_uk",
            "policy_version": _POLICY_VERSION,
            "source_snapshot_sha256": evidence.sha256,
        }
    )
    return hashlib.sha256(payload).hexdigest()


def _scope_key(receipt: FootballDataUkSourceResourceV1) -> str:
    if receipt.provider_competition_code is None:
        return "global"
    return f"competition={receipt.provider_competition_code}/season={receipt.provider_season_code}"


def _request_started_at(receipt: FootballDataUkSourceResourceV1) -> datetime:
    if receipt.request_started_at is None:
        raise AssertionError("validated Football-Data receipt lacks request start time")
    return receipt.request_started_at
