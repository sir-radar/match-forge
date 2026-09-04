from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.ingestion.registration import RegisteredSource
from football.providers import (
    FootballDataUkAcquisitionEvidenceV1,
    FootballDataUkSourceResourceV1,
)
from football.providers.football_data_uk_lifecycle import (
    FootballDataUkLifecycleRegistrationError,
    FootballDataUkPostgresLifecycleRegistryV1,
)


def test_registration_creates_one_frozen_run_and_links_all_three_resources() -> None:
    evidence = _evidence()
    cursor = _ProviderCursor()
    registry = FootballDataUkPostgresLifecycleRegistryV1()

    first = registry.register(cast(Any, cursor), source=_source(), evidence=evidence)
    retry = registry.register(cast(Any, cursor), source=_source(), evidence=evidence)

    assert first.sync_run_id == _Cursor.SYNC_RUN_ID
    assert first.status == "inserted"
    assert retry.status == "verified_existing"
    assert first.acquisition_job_ids == {
        "notes.txt": _Cursor.NOTES_JOB_ID,
        "mmz4281/2526/E0.csv": _Cursor.CURRENT_JOB_ID,
        "mmz4281/1516/E0.csv": _Cursor.OVERLAP_JOB_ID,
    }
    assert first.acquired_resource_ids == {
        "notes.txt": _Cursor.NOTES_ACQUIRED_ID,
        "mmz4281/2526/E0.csv": _Cursor.CURRENT_ACQUIRED_ID,
        "mmz4281/1516/E0.csv": _Cursor.OVERLAP_ACQUIRED_ID,
    }
    assert cursor.sync_insert is not None
    assert cursor.sync_insert[1] == "football-data-uk-phase1b-frozen-sync-v1"
    assert cursor.sync_insert[2] == "succeeded"
    assert cursor.job_inserts == [
        ("schema_semantics_and_attribution", "global", "notes.txt"),
        ("historical_league_csv", "competition=E0/season=2526", "mmz4281/2526/E0.csv"),
        ("historical_league_csv", "competition=E0/season=1516", "mmz4281/1516/E0.csv"),
    ]
    assert [insert[6] for insert in cursor.resource_inserts] == [
        "acquired",
        "acquired",
        "acquired",
    ]


def test_registration_rejects_existing_job_with_different_immutable_evidence() -> None:
    with pytest.raises(FootballDataUkLifecycleRegistrationError, match="acquisition job"):
        FootballDataUkPostgresLifecycleRegistryV1().register(
            cast(Any, _ProviderCursor(conflicting_job=True)), source=_source(), evidence=_evidence()
        )


def test_registration_rejects_a_source_from_another_provider() -> None:
    with pytest.raises(FootballDataUkLifecycleRegistrationError, match="not a Football-Data"):
        FootballDataUkPostgresLifecycleRegistryV1().register(
            cast(Any, _ProviderCursor(provider_code="statsbomb_open_data")),
            source=_source(),
            evidence=_evidence(),
        )


def _source() -> RegisteredSource:
    return RegisteredSource(
        provider_id=_Cursor.PROVIDER_ID,
        snapshot_id=_Cursor.SNAPSHOT_ID,
        resource_ids={
            "notes.txt": _Cursor.NOTES_RESOURCE_ID,
            "mmz4281/2526/E0.csv": _Cursor.CURRENT_RESOURCE_ID,
            "mmz4281/1516/E0.csv": _Cursor.OVERLAP_RESOURCE_ID,
        },
    )


def _evidence() -> FootballDataUkAcquisitionEvidenceV1:
    return FootballDataUkAcquisitionEvidenceV1(
        receipts=(
            _receipt("schema_semantics_and_attribution", "notes.txt", b"notes", 0),
            _receipt("historical_league_csv", "mmz4281/2526/E0.csv", b"current", 1),
            _receipt("historical_league_csv", "mmz4281/1516/E0.csv", b"overlap", 2),
        )
    )


def _receipt(
    resource_type: str,
    source_path: str,
    payload: bytes,
    minute: int,
) -> FootballDataUkSourceResourceV1:
    observed_at = datetime(2026, 9, 4, 16, minute, tzinfo=UTC)
    return FootballDataUkSourceResourceV1.from_payload(
        resource_type=resource_type,  # type: ignore[arg-type]
        source_path=source_path,
        payload=payload,
        observed_by_matchforge_at=observed_at,
        request_started_at=observed_at,
        http_status=200,
        content_type="text/plain" if source_path == "notes.txt" else "text/csv",
    )


class _Cursor:
    PROVIDER_ID = UUID("00000000-0000-0000-0000-000000000001")
    SNAPSHOT_ID = UUID("00000000-0000-0000-0000-000000000002")
    NOTES_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000003")
    CURRENT_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000004")
    OVERLAP_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000005")
    SYNC_RUN_ID = UUID("00000000-0000-0000-0000-000000000006")
    NOTES_JOB_ID = UUID("00000000-0000-0000-0000-000000000007")
    CURRENT_JOB_ID = UUID("00000000-0000-0000-0000-000000000008")
    OVERLAP_JOB_ID = UUID("00000000-0000-0000-0000-000000000009")
    NOTES_ACQUIRED_ID = UUID("00000000-0000-0000-0000-000000000010")
    CURRENT_ACQUIRED_ID = UUID("00000000-0000-0000-0000-000000000011")
    OVERLAP_ACQUIRED_ID = UUID("00000000-0000-0000-0000-000000000012")

    def __init__(self, *, conflicting_job: bool = False) -> None:
        self.conflicting_job = conflicting_job
        self.sync_insert: tuple[object, ...] | None = None
        self.job_inserts: list[tuple[str, str, str]] = []
        self.resource_inserts: list[tuple[object, ...]] = []
        self._jobs: dict[str, tuple[object, ...]] = {}
        self._resources: dict[UUID, tuple[object, ...]] = {}
        self.rowcount = 0
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...]) -> _Cursor:
        if "INSERT INTO football.provider_sync_runs" in query:
            if self.sync_insert is None:
                self.sync_insert = params
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, provider_id, policy_version, status" in query:
            assert self.sync_insert is not None
            self._row = (self.SYNC_RUN_ID, *self.sync_insert)
        elif "INSERT INTO football.acquisition_jobs" in query:
            source_path = str(params[4])
            if source_path not in self._jobs:
                self._jobs[source_path] = params
                self.job_inserts.append((str(params[2]), str(params[3]), source_path))
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, sync_run_id, provider_id, resource_key" in query:
            source_path = str(params[3])
            stored = self._jobs[source_path]
            resource_revision = "0" * 64 if self.conflicting_job else stored[5]
            self._row = (
                _job_id(source_path),
                stored[0],
                stored[1],
                stored[2],
                stored[3],
                stored[4],
                resource_revision,
                stored[6],
                stored[7],
                stored[8],
            )
        elif "INSERT INTO football.acquired_resources" in query:
            resource_id = params[2]
            if resource_id not in self._resources:
                self._resources[cast(UUID, resource_id)] = params
                self.resource_inserts.append(params)
                self.rowcount = 1
            else:
                self.rowcount = 0
        elif "SELECT id, acquisition_job_id, source_snapshot_id, source_resource_id" in query:
            resource_id = cast(UUID, params[0])
            stored = self._resources[resource_id]
            self._row = (_acquired_id(resource_id), *stored)
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class _ProviderCursor(_Cursor):
    def __init__(
        self, *, provider_code: str = "football_data_uk", conflicting_job: bool = False
    ) -> None:
        super().__init__(conflicting_job=conflicting_job)
        self.provider_code = provider_code

    def execute(self, query: str, params: tuple[object, ...]) -> _ProviderCursor:
        if "SELECT provider.code" in query:
            self._row = (self.provider_code,)
            return self
        super().execute(query, params)
        return self


def _job_id(source_path: str) -> UUID:
    return {
        "notes.txt": _Cursor.NOTES_JOB_ID,
        "mmz4281/2526/E0.csv": _Cursor.CURRENT_JOB_ID,
        "mmz4281/1516/E0.csv": _Cursor.OVERLAP_JOB_ID,
    }[source_path]


def _acquired_id(resource_id: UUID) -> UUID:
    return {
        _Cursor.NOTES_RESOURCE_ID: _Cursor.NOTES_ACQUIRED_ID,
        _Cursor.CURRENT_RESOURCE_ID: _Cursor.CURRENT_ACQUIRED_ID,
        _Cursor.OVERLAP_RESOURCE_ID: _Cursor.OVERLAP_ACQUIRED_ID,
    }[resource_id]
