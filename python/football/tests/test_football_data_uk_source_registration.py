from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.providers import (
    FootballDataUkAcquisitionEvidenceV1,
    FootballDataUkSourceResourceV1,
)
from football.providers.football_data_uk_registration import (
    FootballDataUkPostgresSourceRegistryV1,
    FootballDataUkSourceRegistrationError,
)


def test_registration_binds_the_exact_frozen_receipt_bundle_to_postgres_lineage() -> None:
    evidence = _evidence()
    cursor = _Cursor()

    registered = FootballDataUkPostgresSourceRegistryV1().register(cast(Any, cursor), evidence)

    assert registered.provider_id == _Cursor.PROVIDER_ID
    assert registered.snapshot_id == _Cursor.SNAPSHOT_ID
    assert registered.resource_ids == {
        "notes.txt": _Cursor.NOTES_ID,
        "mmz4281/2526/E0.csv": _Cursor.CURRENT_ID,
        "mmz4281/1516/E0.csv": _Cursor.OVERLAP_ID,
    }
    assert cursor.provider_insert == (
        "football_data_uk",
        "Football-Data.co.uk",
        "file_download",
    )
    assert cursor.snapshot_insert == (
        _Cursor.PROVIDER_ID,
        "football_data_uk/phase1b/frozen-resource-bundle",
        evidence.sha256,
        "https://www.football-data.co.uk",
        datetime(2026, 9, 4, 16, 2, tzinfo=UTC),
        "manifests/provider=football_data_uk/"
        f"acquisition_sha256={evidence.sha256}/acquisition-evidence-v1.json",
        evidence.sha256,
    )
    assert cursor.resource_inserts == [
        (_Cursor.NOTES_ID, "notes.txt", "not_applicable", "valid"),
        (_Cursor.CURRENT_ID, "mmz4281/2526/E0.csv", "pending", "pending"),
        (_Cursor.OVERLAP_ID, "mmz4281/1516/E0.csv", "pending", "pending"),
    ]


def test_registration_rejects_conflicting_provider_metadata() -> None:
    cursor = _Cursor(provider_metadata=("Other provider", "manual"))

    with pytest.raises(FootballDataUkSourceRegistrationError, match="provider metadata"):
        FootballDataUkPostgresSourceRegistryV1().register(cast(Any, cursor), _evidence())


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
    NOTES_ID = UUID("00000000-0000-0000-0000-000000000003")
    CURRENT_ID = UUID("00000000-0000-0000-0000-000000000004")
    OVERLAP_ID = UUID("00000000-0000-0000-0000-000000000005")

    def __init__(
        self,
        *,
        provider_metadata: tuple[str, str] = ("Football-Data.co.uk", "file_download"),
    ) -> None:
        self.provider_metadata = provider_metadata
        self.provider_insert: tuple[object, ...] | None = None
        self.snapshot_insert: tuple[object, ...] | None = None
        self.resource_inserts: list[tuple[UUID, str, str, str]] = []
        self._resource_details: dict[str, tuple[object, ...]] = {}
        self._row: tuple[object, ...] | None = None

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> _Cursor:
        if "INSERT INTO football.providers" in query:
            assert params is not None
            self.provider_insert = params
        elif "SELECT id, name, source_type" in query:
            self._row = (self.PROVIDER_ID, *self.provider_metadata)
        elif "INSERT INTO football.source_snapshots" in query:
            assert params is not None
            self.snapshot_insert = params
        elif "SELECT id, repository, acquired_at, manifest_path, manifest_sha256" in query:
            assert self.snapshot_insert is not None
            self._row = (self.SNAPSHOT_ID, *self.snapshot_insert[3:])
        elif "INSERT INTO football.source_resources" in query:
            assert params is not None
            source_path = str(params[1])
            resource_id = {
                "notes.txt": self.NOTES_ID,
                "mmz4281/2526/E0.csv": self.CURRENT_ID,
                "mmz4281/1516/E0.csv": self.OVERLAP_ID,
            }[source_path]
            self.resource_inserts.append((resource_id, source_path, str(params[5]), str(params[6])))
            self._resource_details[source_path] = params[2:]
        elif "SELECT id, sha256, size_bytes, media_type, parse_status" in query:
            assert params is not None
            source_path = str(params[1])
            resource_id, _, parse_status, validation_status = next(
                resource for resource in self.resource_inserts if resource[1] == source_path
            )
            self._row = (resource_id, *self._resource_details[source_path])
        else:
            raise AssertionError(f"unexpected query: {query}")
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row
