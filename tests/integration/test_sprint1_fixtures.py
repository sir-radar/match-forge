from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.datasets import StatsBombEventDatasetPublisher
from football.ingestion import CanonicalIngestionError, SourceAcquirer, StatsBombCanonicalIngestor
from football.validation import QualityPolicy, StatsBombDatasetValidator
from psycopg import Connection

from tests.support.sprint1_fixtures import FixtureProvider, Sprint1Fixture, load_sprint1_fixture

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = PROJECT_ROOT / "schemas/quality/statsbomb-quality-policy-v1.json"


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


@pytest.mark.parametrize("fixture_name", ("valid", "quality"))
def test_fixture_round_trip_is_reproducible_and_lineage_complete(
    connection: Connection[Any], tmp_path: Path, fixture_name: str
) -> None:
    fixture = load_sprint1_fixture(fixture_name)
    provider = FixtureProvider(fixture)
    acquirer = SourceAcquirer(tmp_path, clock=lambda: fixture.acquired_at)

    acquisition = acquirer.acquire(provider, fixture.source_resources)
    assert acquisition.statuses == {
        resource.path: "acquired" for resource in fixture.source_resources
    }
    assert provider.fetches == [resource.path for resource in fixture.source_resources]
    for resource in acquisition.manifest.resources:
        assert (tmp_path / resource.raw_path).read_bytes() == fixture.payload(
            next(item for item in fixture.source_resources if item.path == resource.path)
        )

    canonical = StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    assert {
        "competitions": canonical.competitions_seen,
        "seasons": canonical.seasons_seen,
        "teams": canonical.teams_seen,
        "players": canonical.players_seen,
        "matches": canonical.matches_seen,
        "lineup_players": canonical.lineup_players_seen,
        "position_stints": canonical.position_stints_seen,
        "cards": canonical.cards_seen,
        "events": canonical.events_seen,
    } == fixture.expected.canonical

    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    assert dataset.status == "published"
    assert sum(file.row_count for file in dataset.files) == fixture.expected.dataset_rows

    validation_times = iter(
        fixture.acquired_at + timedelta(hours=offset) for offset in (1, 2, 3, 4)
    )
    validator = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(POLICY_PATH),
        clock=lambda: next(validation_times),
    )
    validation = validator.validate(dataset.dataset_version_id)
    assert validation.status == fixture.expected.outcome
    assert validation.registration_status == "registered"
    assert Counter(finding.rule_code for finding in validation.findings) == Counter(
        fixture.expected.finding_counts
    )

    _assert_lineage(connection, fixture, canonical.source_snapshot_id, dataset.dataset_version_id)

    repeated_acquisition = acquirer.acquire(FixtureProvider(fixture), fixture.source_resources)
    repeated_canonical = StatsBombCanonicalIngestor(connection, tmp_path).ingest(
        repeated_acquisition
    )
    repeated_dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(
        repeated_acquisition
    )
    repeated_validation = validator.validate(repeated_dataset.dataset_version_id)

    assert set(repeated_acquisition.statuses.values()) == {"verified_existing"}
    assert repeated_canonical.source_snapshot_id == canonical.source_snapshot_id
    assert repeated_dataset.dataset_version_id == dataset.dataset_version_id
    assert repeated_dataset.status == "verified_published"
    assert {file.status for file in repeated_dataset.files} == {"verified_published"}
    assert repeated_validation.validation_run_id == validation.validation_run_id
    assert repeated_validation.registration_status == "verified_registered"
    _assert_lineage(connection, fixture, canonical.source_snapshot_id, dataset.dataset_version_id)


def test_malformed_fixture_fails_before_database_registration(
    connection: Connection[Any], tmp_path: Path
) -> None:
    fixture = load_sprint1_fixture("malformed-events")
    acquisition = SourceAcquirer(tmp_path, clock=lambda: fixture.acquired_at).acquire(
        FixtureProvider(fixture), fixture.source_resources
    )

    assert fixture.expected.error_message is not None
    with pytest.raises(CanonicalIngestionError, match=fixture.expected.error_message):
        StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    with connection.cursor() as cursor:
        snapshot_count = cursor.execute(
            "SELECT count(*) FROM football.source_snapshots WHERE source_revision = %s",
            (fixture.snapshot.source_git_sha,),
        ).fetchone()
    assert snapshot_count == (0,)
    assert acquisition.manifest_path.is_file()
    assert not (tmp_path / "normalized").exists()
    assert not (tmp_path / "manifests/datasets").exists()


def _assert_lineage(
    connection: Connection[Any],
    fixture: Sprint1Fixture,
    source_snapshot_id: UUID,
    dataset_version_id: UUID,
) -> None:
    with connection.cursor() as cursor:
        lineage = cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM football.source_resources
                 WHERE source_snapshot_id = %s AND parse_status = 'parsed'),
                (SELECT count(*) FROM football.dataset_inputs
                 WHERE dataset_version_id = %s AND source_snapshot_id = %s),
                (SELECT count(*) FROM football.dataset_files
                 WHERE dataset_version_id = %s),
                (SELECT count(*) FROM football.dataset_versions
                 WHERE id = %s AND source_snapshot_id = %s)
            """,
            (
                source_snapshot_id,
                dataset_version_id,
                source_snapshot_id,
                dataset_version_id,
                dataset_version_id,
                source_snapshot_id,
            ),
        ).fetchone()
    assert lineage == (len(fixture.resources), len(fixture.resources), 1, 1)
