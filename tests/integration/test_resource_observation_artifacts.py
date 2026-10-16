from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import psycopg
import pytest
from football.contracts.observation_schema import observation_schema_sha256
from football.contracts.observations import (
    EntityReference,
    FixtureObservationV1,
    ObservationError,
    ObservationProvenance,
    ObservationTime,
    ObservationVersions,
)
from football.observations.storage import ObservationArtifactStore
from football.product.api_football import ApiFootballClient, ApiResponse
from football.product.sync import ProductSync
from football.storage.raw import ImmutableFileConflict
from psycopg.errors import RaiseException

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[object]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as database,
        database.transaction(force_rollback=True),
    ):
        yield database


def _observation(connection: psycopg.Connection[object], root: Path) -> FixtureObservationV1:
    raw = b'{"response":[{"fixture":{"id":42}}]}'
    sync = ProductSync(connection, ApiFootballClient("test"), root, root / "unused-model")
    snapshot = sync._record_response(
        "observation-contract-test", ApiResponse("/fixtures", NOW, raw, (), None)
    )
    row = connection.execute(
        "SELECT id,acquired_at FROM football.source_resources WHERE source_snapshot_id=%s",
        (snapshot,),
    ).fetchone()
    assert row is not None
    return FixtureObservationV1(
        provenance=ObservationProvenance(
            "api_football", "42", snapshot, row[0], hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=NOW, acquired_at=row[1], known_at=NOW),
        versions=ObservationVersions(
            provider_schema_version="api-football-v3",
            adapter_version="adapter-test-1",
            normalizer_version="fixtures-test-1",
            resolution_version=None,
        ),
        fixture=EntityReference("42"),
        competition=EntityReference("47"),
        home_team=EntityReference("1"),
        away_team=EntityReference("2"),
        kickoff_at=NOW + timedelta(days=1),
        status="SCHEDULED",
        kickoff_precision="EXACT",
    )


def test_publish_load_and_retry_preserve_versions_and_canonical_state(
    connection: psycopg.Connection[object],
    tmp_path: Path,
) -> None:
    item = _observation(connection, tmp_path)
    store = ObservationArtifactStore(connection, tmp_path)
    before = connection.execute(
        "SELECT (SELECT count(*) FROM football.product_fixtures),"
        "(SELECT count(*) FROM football.product_forecasts)"
    ).fetchone()
    identifier = store.publish(item)
    assert store.publish(item) == identifier
    assert store.load(identifier) == item
    assert connection.execute(
        """SELECT provider_schema_version,adapter_version,normalizer_version,
           observation_contract_version,resolution_version,schema_sha256
           FROM football.resource_observation_artifacts WHERE observation_id=%s""",
        (identifier,),
    ).fetchone() == (
        "api-football-v3",
        "adapter-test-1",
        "fixtures-test-1",
        "1",
        None,
        observation_schema_sha256(),
    )
    corrected = replace(item, time=replace(item.time, known_at=NOW + timedelta(seconds=1)))
    assert store.publish(corrected) != identifier
    assert store.load(identifier) == item
    assert (
        connection.execute(
            "SELECT (SELECT count(*) FROM football.product_fixtures),"
            "(SELECT count(*) FROM football.product_forecasts)"
        ).fetchone()
        == before
    )


@pytest.mark.parametrize("field", ["source_sha256", "source_snapshot_id", "provider"])
def test_registered_source_provenance_cannot_be_forged(
    connection: psycopg.Connection[object],
    tmp_path: Path,
    field: str,
) -> None:
    item = _observation(connection, tmp_path)
    values = {
        "source_sha256": "b" * 64,
        "source_snapshot_id": UUID(int=999999),
        "provider": "observation_test_unknown_provider",
    }
    if field == "provider":
        connection.execute(
            """INSERT INTO football.providers(id,code,name,source_type)
               VALUES (%s,%s,'Observation test alternate','http_api')""",
            (UUID(int=999998), values["provider"]),
        )
    forged = replace(item, provenance=replace(item.provenance, **{field: values[field]}))
    with pytest.raises((RaiseException, ObservationError)), connection.transaction():
        ObservationArtifactStore(connection, tmp_path).publish(forged)


def test_acquisition_clock_must_match_registered_source(
    connection: psycopg.Connection[object],
    tmp_path: Path,
) -> None:
    item = _observation(connection, tmp_path)
    forged = replace(item, time=replace(item.time, acquired_at=NOW - timedelta(seconds=1)))
    with pytest.raises(RaiseException, match="provenance"), connection.transaction():
        ObservationArtifactStore(connection, tmp_path).publish(forged)


@pytest.mark.parametrize(
    "table", ["resource_observation_artifacts", "observation_contract_schemas"]
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_registered_artifacts_and_schemas_are_immutable(
    connection: psycopg.Connection[object],
    tmp_path: Path,
    table: str,
    operation: str,
) -> None:
    ObservationArtifactStore(connection, tmp_path).publish(_observation(connection, tmp_path))
    statement = (
        f"UPDATE football.{table} SET registered_at=registered_at"
        if operation == "UPDATE"
        else f"DELETE FROM football.{table}"
    )
    with pytest.raises(RaiseException, match="immutable"), connection.transaction():
        connection.execute(statement)


def test_contract_version_cannot_change_schema_bytes(
    connection: psycopg.Connection[object],
    tmp_path: Path,
) -> None:
    item = _observation(connection, tmp_path)
    connection.execute(
        """INSERT INTO football.observation_contract_schemas (
           contract_name,observation_contract_version,schema_sha256,schema_document)
           VALUES (%s,'1',%s,'{}')""",
        (item.CONTRACT, "c" * 64),
    )
    with pytest.raises(ObservationError, match="different bytes"):
        ObservationArtifactStore(connection, tmp_path).publish(item)


def test_orphan_file_retry_converges_and_corruption_is_detected(
    connection: psycopg.Connection[object],
    tmp_path: Path,
) -> None:
    item = _observation(connection, tmp_path)
    store = ObservationArtifactStore(connection, tmp_path)
    with connection.transaction(force_rollback=True):
        identifier = store.publish(item)
    with pytest.raises(ObservationError, match="not registered"):
        store.load(identifier)
    assert store.publish(item) == identifier
    assert store.load(identifier) == item
    path = tmp_path / f"observations/v1/{item.CONTRACT}/{item.sha256}.json"
    path.write_bytes(b"corrupted")
    with pytest.raises(ObservationError, match="checksum"):
        store.load(identifier)
    with pytest.raises(ImmutableFileConflict):
        store.publish(item)
