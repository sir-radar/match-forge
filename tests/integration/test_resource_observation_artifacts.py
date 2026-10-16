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


def test_v1_and_v2_artifacts_coexist_without_schema_or_byte_changes(
    connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.contracts.observations_v2 import (
        EntityReferenceV2,
        FixtureObservationV2,
        ObservationVersionsV2,
    )

    old = _observation(connection, tmp_path)
    item = FixtureObservationV2(
        provenance=old.provenance,
        time=old.time,
        versions=ObservationVersionsV2(
            adapter_version="source-v2", normalizer_version="fixture-v2"
        ),
        fixture=EntityReferenceV2("42"),
        competition=EntityReferenceV2("47"),
        home_team=EntityReferenceV2(None, source_record_key="json:/home"),
        away_team=EntityReferenceV2(None, source_record_key="json:/away"),
        kickoff_at=old.kickoff_at,
        status="SCHEDULED",
        kickoff_precision="EXACT",
    )
    store = ObservationArtifactStore(connection, tmp_path)
    store.publish(old)
    store.publish(item)
    assert store.load(old.observation_id).to_bytes() == old.to_bytes()
    assert store.load(item.observation_id).to_bytes() == item.to_bytes()
    assert store.publish(item) == item.observation_id
    assert connection.execute(
        "SELECT observation_contract_version, schema_sha256 "
        "FROM football.resource_observation_artifacts WHERE observation_id IN (%s,%s) "
        "ORDER BY observation_contract_version",
        (old.observation_id, item.observation_id),
    ).fetchall() == [("1", observation_schema_sha256("1")), ("2", observation_schema_sha256("2"))]


def _normalization_source(connection: psycopg.Connection[object], root: Path) -> UUID:
    import json

    row = {
        "fixture": {"id": 42, "date": "2026-10-17T12:00:00Z", "status": {"short": "NS"}},
        "league": {"id": 7, "season": 2026},
        "teams": {"home": {"id": 1, "name": "Home"}, "away": {"id": 2, "name": "Away"}},
        "goals": {"home": None, "away": None},
    }
    raw = json.dumps({"response": [row]}).encode()
    sync = ProductSync(connection, ApiFootballClient("test"), root, root / "unused-model")
    snapshot = sync._record_response(
        "normalization-test", ApiResponse("/fixtures", NOW, raw, (), None)
    )
    result = connection.execute(
        "SELECT id FROM football.source_resources WHERE source_snapshot_id=%s", (snapshot,)
    ).fetchone()
    assert result is not None
    return UUID(str(result[0]))


def test_registered_resource_normalizes_reproducibly_with_durable_source_times(
    connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.providers.normalization.cli import registered_resource, report_bytes
    from football.providers.normalization.pipeline import normalize_resource

    source = _normalization_source(connection, tmp_path)
    context, raw = registered_resource(connection, tmp_path, source)
    first = normalize_resource(context, "fixtures", raw)
    assert len(first.observations) == 3 and not first.findings
    before = connection.execute(
        "SELECT (SELECT count(*) FROM football.product_fixtures), "
        "(SELECT count(*) FROM football.product_forecasts)"
    ).fetchone()
    store = ObservationArtifactStore(connection, tmp_path)
    identifiers = [store.publish(o) for o in first.observations]
    later_context, later_raw = registered_resource(connection, tmp_path, source)
    second = normalize_resource(later_context, "fixtures", later_raw)
    assert report_bytes(context, "fixtures", first) == report_bytes(
        later_context, "fixtures", second
    )
    assert [store.publish(o) for o in second.observations] == identifiers
    assert all(store.load(o.observation_id) == o for o in first.observations)
    assert (
        context.time.acquired_at
        == connection.execute(
            "SELECT acquired_at FROM football.source_resources WHERE id=%s", (source,)
        ).fetchone()[0]
    )
    assert (
        connection.execute(
            "SELECT (SELECT count(*) FROM football.product_fixtures), "
            "(SELECT count(*) FROM football.product_forecasts)"
        ).fetchone()
        == before
    )


def test_normalization_rollback_retry_converges_and_retains_reports(
    connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.providers.normalization.cli import registered_resource, report_bytes
    from football.providers.normalization.pipeline import normalize_resource

    context, raw = registered_resource(
        connection, tmp_path, _normalization_source(connection, tmp_path)
    )
    result = normalize_resource(context, "fixtures", raw)
    report = report_bytes(context, "fixtures", result)
    store = ObservationArtifactStore(connection, tmp_path)
    with connection.transaction(force_rollback=True):
        for o in result.observations:
            store.publish(o)
    assert connection.execute(
        "SELECT count(*) FROM football.resource_observation_artifacts WHERE source_resource_id=%s",
        (context.provenance.source_resource_id,),
    ).fetchone() == (0,)
    for observation in result.observations:
        store.publish(observation)
    assert report == report_bytes(context, "fixtures", normalize_resource(context, "fixtures", raw))
    assert connection.execute(
        "SELECT count(*) FROM football.resource_observation_artifacts WHERE source_resource_id=%s",
        (context.provenance.source_resource_id,),
    ).fetchone() == (3,)


def test_registered_normalization_rejects_unregistered_or_corrupt_sources(
    connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.providers.normalization.cli import registered_resource

    with pytest.raises(ValueError, match="not registered"):
        registered_resource(connection, tmp_path, UUID(int=0))
    source = _normalization_source(connection, tmp_path)
    row = connection.execute(
        "SELECT s.manifest_path FROM football.source_resources r "
        "JOIN football.source_snapshots s ON s.id=r.source_snapshot_id WHERE r.id=%s",
        (source,),
    ).fetchone()
    assert row is not None
    (tmp_path / str(row[0])).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        registered_resource(connection, tmp_path, source)


def test_legacy_openfootball_reader_uses_git_revision_without_changing_snapshot_identity(
    connection: psycopg.Connection[object], tmp_path: Path
) -> None:
    from football.providers.normalization.cli import registered_resource
    from football.storage.raw import ImmutableFileStore

    files = ImmutableFileStore(tmp_path)
    revision = "b" * 40
    native_path = "2025-26/en.1.json"
    raw = b'{"matches":[]}'
    written = files.publish(f"openfootball/{revision}/{native_path}", raw)
    manifest = files.publish(f"openfootball/{revision}/catalog.json", b"[]")
    connection.execute(
        "INSERT INTO football.providers(code,name,source_type) "
        "VALUES ('openfootball','OpenFootball','git_repository') ON CONFLICT (code) DO NOTHING"
    )
    provider = connection.execute(
        "SELECT id FROM football.providers WHERE code='openfootball'"
    ).fetchone()
    assert provider is not None
    snapshot = connection.execute(
        """INSERT INTO football.source_snapshots(
        provider_id,source_identity,source_revision,git_sha,
        acquired_at,manifest_path,manifest_sha256,status)
        VALUES (%s,'legacy-normalization-regression',%s,%s,%s,%s,%s,'validated') RETURNING id""",
        (provider[0], revision, revision, NOW, manifest.relative_path, manifest.sha256),
    ).fetchone()
    assert snapshot is not None
    resource = connection.execute(
        """INSERT INTO football.source_resources(source_snapshot_id,provider_path,sha256,size_bytes,
        media_type,parse_status,validation_status,acquired_at)
        VALUES (%s,%s,%s,%s,'application/json','parsed','valid',%s) RETURNING id""",
        (snapshot[0], native_path, written.sha256, len(raw), NOW),
    ).fetchone()
    assert resource is not None
    context, loaded = registered_resource(connection, tmp_path, resource[0])
    assert loaded == raw
    assert context.provenance.source_snapshot_id == snapshot[0]
    assert str(snapshot[0]) != revision
