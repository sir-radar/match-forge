from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Cursor

from football.ingestion.registration import RegisteredSource
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.providers.football_data_uk_evidence import FootballDataUkAcquisitionEvidenceV1

_PROVIDER_CODE = "football_data_uk"
_PROVIDER_NAME = "Football-Data.co.uk"
_SOURCE_IDENTITY = "football_data_uk/phase1b/frozen-resource-bundle"
_REPOSITORY = "https://www.football-data.co.uk"


class FootballDataUkSourceRegistrationError(ValueError):
    """A frozen Football-Data receipt bundle conflicts with PostgreSQL lineage."""


class FootballDataUkPostgresSourceRegistryV1:
    """Register one immutable Football-Data receipt bundle before downstream use."""

    def register(
        self,
        cursor: Cursor[Any],
        evidence: FootballDataUkAcquisitionEvidenceV1,
    ) -> RegisteredSource:
        provider_id = self._provider(cursor)
        manifest_path = _manifest_path(evidence)
        snapshot_id = self._snapshot(cursor, provider_id, evidence, manifest_path)
        return RegisteredSource(
            provider_id=provider_id,
            snapshot_id=snapshot_id,
            resource_ids={
                receipt.source_path: self._resource(cursor, snapshot_id, receipt)
                for receipt in evidence.receipts
            },
        )

    @staticmethod
    def _provider(cursor: Cursor[Any]) -> UUID:
        cursor.execute(
            """
            INSERT INTO football.providers (code, name, source_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (code) DO NOTHING
            """,
            (_PROVIDER_CODE, _PROVIDER_NAME, "file_download"),
        )
        row = cursor.execute(
            "SELECT id, name, source_type FROM football.providers WHERE code = %s",
            (_PROVIDER_CODE,),
        ).fetchone()
        if row is None or row[1:] != (_PROVIDER_NAME, "file_download"):
            raise FootballDataUkSourceRegistrationError(
                "provider metadata conflicts with Football-Data source registration"
            )
        return UUID(str(row[0]))

    @staticmethod
    def _snapshot(
        cursor: Cursor[Any],
        provider_id: UUID,
        evidence: FootballDataUkAcquisitionEvidenceV1,
        manifest_path: str,
    ) -> UUID:
        acquired_at = _acquired_at(evidence)
        values = (
            provider_id,
            _SOURCE_IDENTITY,
            evidence.sha256,
            _REPOSITORY,
            acquired_at,
            manifest_path,
            evidence.sha256,
        )
        cursor.execute(
            """
            INSERT INTO football.source_snapshots
                (provider_id, source_identity, source_revision, repository, acquired_at,
                 manifest_path, manifest_sha256, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'acquired')
            ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
            """,
            values,
        )
        row = cursor.execute(
            """
            SELECT id, repository, acquired_at, manifest_path, manifest_sha256
            FROM football.source_snapshots
            WHERE provider_id = %s AND source_identity = %s AND source_revision = %s
            """,
            (provider_id, _SOURCE_IDENTITY, evidence.sha256),
        ).fetchone()
        expected = (_REPOSITORY, acquired_at, manifest_path, evidence.sha256)
        if row is None or row[1:] != expected:
            raise FootballDataUkSourceRegistrationError(
                "source snapshot revision conflicts with frozen receipt evidence"
            )
        return UUID(str(row[0]))

    @staticmethod
    def _resource(
        cursor: Cursor[Any],
        snapshot_id: UUID,
        receipt: FootballDataUkSourceResourceV1,
    ) -> UUID:
        parse_status, validation_status = _resource_status(receipt.resource_type)
        cursor.execute(
            """
            INSERT INTO football.source_resources
                (source_snapshot_id, provider_path, sha256, size_bytes, media_type,
                 parse_status, validation_status, acquired_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
            """,
            (
                snapshot_id,
                receipt.source_path,
                receipt.raw_sha256,
                receipt.raw_byte_size,
                receipt.content_type,
                parse_status,
                validation_status,
                receipt.observed_by_matchforge_at,
            ),
        )
        row = cursor.execute(
            """
            SELECT id, sha256, size_bytes, media_type, parse_status, validation_status,
                   acquired_at
            FROM football.source_resources
            WHERE source_snapshot_id = %s AND provider_path = %s
            """,
            (snapshot_id, receipt.source_path),
        ).fetchone()
        expected = (
            receipt.raw_sha256,
            receipt.raw_byte_size,
            receipt.content_type,
            parse_status,
            validation_status,
            receipt.observed_by_matchforge_at,
        )
        if row is None or row[1:] != expected:
            raise FootballDataUkSourceRegistrationError(
                f"source resource conflicts with frozen receipt: {receipt.source_path}"
            )
        return UUID(str(row[0]))


def _manifest_path(evidence: FootballDataUkAcquisitionEvidenceV1) -> str:
    return (
        "manifests/provider=football_data_uk/"
        f"acquisition_sha256={evidence.sha256}/acquisition-evidence-v1.json"
    )


def _acquired_at(evidence: FootballDataUkAcquisitionEvidenceV1) -> datetime:
    return max(receipt.observed_by_matchforge_at for receipt in evidence.receipts)


def _resource_status(resource_type: str) -> tuple[str, str]:
    if resource_type == "schema_semantics_and_attribution":
        return ("not_applicable", "valid")
    return ("pending", "pending")
