import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.storage.locks import LockClass, LockOrderError, LockRequest, acquire_locks
from psycopg import Connection


@pytest.fixture
def locks() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        yield connection


def test_reverse_class_and_key_requests_fail_before_blocking(locks: Connection[Any]) -> None:
    acquire_locks(locks, (LockRequest(LockClass.FIXTURE, "fixture:b"),))
    for item in (
        LockRequest(LockClass.COMPETITION, "competition:a"),
        LockRequest(LockClass.FIXTURE, "fixture:a"),
    ):
        with pytest.raises(LockOrderError), locks.transaction():
            acquire_locks(locks, (item,))


def test_held_lower_class_can_be_reentered_but_new_lower_class_cannot(
    locks: Connection[Any],
) -> None:
    original = LockRequest(LockClass.IDENTITY, "identity:a")
    acquire_locks(locks, (original, LockRequest(LockClass.WORK, "work:a")))
    acquire_locks(locks, (original,))
    with pytest.raises(LockOrderError), locks.transaction():
        acquire_locks(locks, (LockRequest(LockClass.IDENTITY, "identity:b"),))


@pytest.mark.parametrize("legacy", [False, True])
def test_existing_advisory_hash_namespaces_are_preserved(
    locks: Connection[Any], legacy: bool
) -> None:
    key = f"test-lock:{uuid4()}"
    acquire_locks(locks, (LockRequest(LockClass.IDENTITY, key, legacy_hash=legacy),))
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as other,
        other.transaction(force_rollback=True),
    ):
        expression = "hashtext(%s)::bigint" if legacy else "hashtextextended(%s,0)"
        assert other.execute(
            "SELECT pg_try_advisory_xact_lock(" + expression + ")", (key,)
        ).fetchone() == (False,)


def test_hash_convention_cannot_change_after_acquisition(locks: Connection[Any]) -> None:
    acquire_locks(locks, (LockRequest(LockClass.IDENTITY, "identity:a"),))
    with pytest.raises(LockOrderError), locks.transaction():
        acquire_locks(locks, (LockRequest(LockClass.IDENTITY, "identity:a", legacy_hash=True),))


def test_savepoint_rollback_restores_lock_order_and_releases_locks(locks: Connection[Any]) -> None:
    acquire_locks(locks, (LockRequest(LockClass.IDENTITY, "identity:a"),))
    key = f"work:{uuid4()}"
    with pytest.raises(RuntimeError, match="rollback scope"), locks.transaction():
        acquire_locks(locks, (LockRequest(LockClass.WORK, key),))
        raise RuntimeError("rollback scope")
    acquire_locks(locks, (LockRequest(LockClass.COMPETITION, "competition:a"),))
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as other,
        other.transaction(force_rollback=True),
    ):
        assert other.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))", (key,)
        ).fetchone() == (True,)


def test_lock_order_does_not_leak_across_committed_transactions() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection:
        with connection.transaction():
            acquire_locks(connection, (LockRequest(LockClass.WORK, "work:a"),))
        with connection.transaction():
            acquire_locks(connection, (LockRequest(LockClass.IDENTITY, "identity:a"),))


def test_autocommit_cannot_silently_release_locks_before_publication() -> None:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection,
        pytest.raises(LockOrderError, match="remains open"),
    ):
        acquire_locks(connection, (LockRequest(LockClass.WORK, "work:a"),))


@pytest.mark.parametrize("kind", list(LockClass))
def test_sql_and_python_share_all_lock_classes(locks: Connection[Any], kind: LockClass) -> None:
    acquire_locks(locks, (LockRequest(kind, f"kind:{kind.name}"),))


def publication_claim(connection: Connection[Any]) -> Any:
    from datetime import UTC, datetime, timedelta

    from football.work.contracts import RetryPolicy, WorkClaim, WorkRequest, WorkType
    from football.work.storage import WorkRegistry

    item = WorkRequest(
        work_type=WorkType.CANONICAL_RECONCILIATION,
        semantic_key=f"lock-test:{uuid4()}",
        input_hash="a" * 64,
        priority=0,
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        max_attempts=1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
    )
    WorkRegistry(connection).enqueue(item)
    row = connection.execute("""SELECT work_id,work_type,semantic_key,input_hash,lease_owner,
        lease_token,generation,lease_until,attempt_count FROM football.claim_work(
        'lock-test',interval '1 minute',ARRAY['CANONICAL_RECONCILIATION'])""").fetchone()
    assert row is not None
    return WorkClaim(row[0], WorkType(row[1]), *row[2:])


def test_work_publication_rejects_late_identity_lock_and_rolls_back(locks: Connection[Any]) -> None:
    from football.work.storage import WorkRegistry

    claim = publication_claim(locks)
    locks.execute("CREATE TEMP TABLE lock_effects(value integer)")
    with (
        pytest.raises(LockOrderError),
        WorkRegistry(locks).publication(claim, result_hash="b" * 64) as publisher,
    ):
        publisher.execute("INSERT INTO lock_effects VALUES (1)")
        acquire_locks(publisher, (LockRequest(LockClass.IDENTITY, "identity:late"),))
    assert locks.execute("SELECT count(*) FROM lock_effects").fetchone() == (0,)
    assert locks.execute(
        "SELECT state FROM football.work_items WHERE work_id=%s", (claim.work_id,)
    ).fetchone() == ("RUNNING",)


def test_lock_order_error_is_not_misreported_as_lost_work_lease(locks: Connection[Any]) -> None:
    from football.work.storage import WorkRegistry

    claim = publication_claim(locks)
    acquire_locks(locks, (LockRequest(LockClass.WORK, "work:z"),))
    with (
        pytest.raises(LockOrderError),
        WorkRegistry(locks).publication(claim, result_hash="b" * 64),
    ):
        pytest.fail("reversed work lock order was accepted")


def product_fixture(connection: Connection[Any]) -> Any:
    row = connection.execute("""
        WITH c AS (INSERT INTO football.competitions DEFAULT VALUES RETURNING id),
        h AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
        a AS (INSERT INTO football.teams DEFAULT VALUES RETURNING id),
        s AS (INSERT INTO football.seasons(competition_id) SELECT id FROM c RETURNING id),
        m AS (INSERT INTO football.matches(competition_id,season_id)
              SELECT c.id,s.id FROM c,s RETURNING id)
        SELECT c.id,h.id,a.id,m.id FROM c,h,a,m""").fetchone()
    competition, home, away, fixture = row
    connection.execute(
        """INSERT INTO football.product_competitions(
        competition_id,name,country,continent,competition_type,season_label,
        availability_status,source_roles,updated_at) VALUES (
        %s,'Lock scope','England','Europe','LEAGUE','2026',
        'NOT_ENOUGH_HISTORY','{}',clock_timestamp())""",
        (competition,),
    )
    connection.execute(
        """INSERT INTO football.product_teams(team_id,name,updated_at)
        VALUES (%s,'Home',clock_timestamp()),(%s,'Away',clock_timestamp())""",
        (home, away),
    )
    connection.execute(
        """INSERT INTO football.product_fixtures(fixture_id,competition_id,
        home_team_id,away_team_id,kickoff_at,status,forecast_availability,updated_at)
        VALUES (%s,%s,%s,%s,clock_timestamp()+interval '1 day','SCHEDULED',
        'NOT_ENOUGH_HISTORY',clock_timestamp())""",
        (fixture, competition, home, away),
    )
    return competition, fixture


def test_fixture_scope_locks_its_competition_before_work_publication(
    locks: Connection[Any],
) -> None:
    from football.storage.locks import lock_fixtures
    from football.work.storage import WorkRegistry

    _, fixture = product_fixture(locks)
    assert lock_fixtures(locks, (fixture,))
    claim = publication_claim(locks)
    with WorkRegistry(locks).publication(claim, result_hash="b" * 64) as publisher:
        assert lock_fixtures(publisher, (fixture,))
        publisher.execute(
            "UPDATE football.product_fixtures SET venue='Scoped' WHERE fixture_id=%s", (fixture,)
        )
    assert locks.execute(
        "SELECT venue FROM football.product_fixtures WHERE fixture_id=%s", (fixture,)
    ).fetchone() == ("Scoped",)


def test_fixture_scope_cannot_be_acquired_after_work_row(locks: Connection[Any]) -> None:
    from football.storage.locks import lock_fixtures
    from football.work.storage import WorkRegistry

    _, fixture = product_fixture(locks)
    claim = publication_claim(locks)
    with (
        pytest.raises(LockOrderError),
        WorkRegistry(locks).publication(claim, result_hash="b" * 64) as publisher,
    ):
        lock_fixtures(publisher, (fixture,))


@contextmanager
def committed_product_fixture() -> Iterator[tuple[Connection[Any], Any, Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as owner:
        competition, fixture = product_fixture(owner)
        season, home, away = owner.execute(
            """SELECT m.season_id,f.home_team_id,f.away_team_id
            FROM football.product_fixtures f JOIN football.matches m ON m.id=f.fixture_id
            WHERE f.fixture_id=%s""",
            (fixture,),
        ).fetchone()
        try:
            yield owner, competition, fixture
        finally:
            with owner.transaction():
                owner.execute(
                    "DELETE FROM football.product_forecast_refresh_work WHERE fixture_id=%s",
                    (fixture,),
                )
                owner.execute(
                    "DELETE FROM football.product_fixtures WHERE fixture_id=%s", (fixture,)
                )
                owner.execute("DELETE FROM football.matches WHERE id=%s", (fixture,))
                owner.execute(
                    "DELETE FROM football.product_teams WHERE team_id=ANY(%s)", ([home, away],)
                )
                owner.execute("DELETE FROM football.teams WHERE id=ANY(%s)", ([home, away],))
                owner.execute(
                    "DELETE FROM football.product_competitions WHERE competition_id=%s",
                    (competition,),
                )
                owner.execute("DELETE FROM football.seasons WHERE id=%s", (season,))
                owner.execute("DELETE FROM football.competitions WHERE id=%s", (competition,))


@pytest.mark.parametrize("busy_kind", ["row", "advisory"])
def test_busy_scope_defers_without_leaving_partial_locks(busy_kind: str) -> None:
    from football.storage.locks import lock_fixtures

    with committed_product_fixture() as (owner, competition, fixture), owner.transaction():
        if busy_kind == "row":
            owner.execute(
                "SELECT 1 FROM football.product_competitions WHERE competition_id=%s FOR UPDATE",
                (competition,),
            )
        else:
            acquire_locks(
                owner, (LockRequest(LockClass.COMPETITION, f"competition:{competition}"),)
            )
        with (
            psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as candidate,
            candidate.transaction(),
        ):
            candidate.execute("SET LOCAL statement_timeout='2s'")
            assert lock_fixtures(candidate, (fixture,), wait=False) is False
            acquire_locks(candidate, (LockRequest(LockClass.SOURCE, f"source:{uuid4()}"),))
            if busy_kind == "row":
                assert owner.execute(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"competition:{competition}",),
                ).fetchone() == (True,)


def test_operational_mutation_waits_for_identity_before_locking_fixture(tmp_path: Path) -> None:
    from football.product.operational_provider_sync import OperationalProviderSync
    from football.providers.pitchapi import PitchApiFixture
    from football.storage.locks import lock_fixtures

    with (
        committed_product_fixture() as (owner, _, fixture),
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as worker,
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as observer,
    ):
        kickoff, now = owner.execute(
            "SELECT kickoff_at,clock_timestamp() "
            "FROM football.product_fixtures WHERE fixture_id=%s",
            (fixture,),
        ).fetchone()
        row = PitchApiFixture(
            provider_match_id="lock-test",
            provider_competition_id="scope",
            provider_home_team_id="home",
            provider_away_team_id="away",
            home_team_name="Home",
            away_team_name="Away",
            kickoff_at=kickoff,
            status="LIVE",
            provider_status="LIVE",
            home_score=None,
            away_score=None,
            minute=None,
            added_time=None,
            period=None,
            source_updated_at=now,
            observed_at=now,
        )
        sync = OperationalProviderSync(worker, tmp_path, provider_code="fotmob")
        worker.execute("SET statement_timeout='5s'")

        def update() -> int:
            with worker.transaction():
                return sync._update_canonical_fixture(row, fixture, uuid4())

        with ThreadPoolExecutor(max_workers=1) as executor:
            with owner.transaction():
                acquire_locks(
                    owner, (LockRequest(LockClass.IDENTITY, "product-identity-admission"),)
                )
                result = executor.submit(update)
                deadline = monotonic() + 3
                blocked = False
                while monotonic() < deadline:
                    blockers = observer.execute(
                        "SELECT pg_blocking_pids(%s)", (worker.info.backend_pid,)
                    ).fetchone()[0]
                    if owner.info.backend_pid in blockers:
                        blocked = True
                        break
                    if result.done():
                        break
                    sleep(0.01)
                assert blocked, "worker did not reach the controlled identity wait"
                row_available = True
                try:
                    with observer.transaction(force_rollback=True):
                        observer.execute(
                            "SELECT 1 FROM football.product_fixtures "
                            "WHERE fixture_id=%s FOR UPDATE NOWAIT",
                            (fixture,),
                        )
                except psycopg.errors.LockNotAvailable:
                    row_available = False
                if row_available:
                    assert lock_fixtures(owner, (fixture,))
                    owner.execute(
                        "UPDATE football.product_fixtures SET venue='Identity owner' "
                        "WHERE fixture_id=%s",
                        (fixture,),
                    )
            assert result.result(timeout=5) == 1
        assert row_available, "fixture was locked while waiting for identity coordination"


def test_immutable_parent_work_can_be_referenced_during_publication() -> None:
    from dataclasses import replace
    from datetime import UTC, datetime, timedelta

    from football.work.contracts import RetryPolicy, WorkRequest, WorkType
    from football.work.storage import WorkRegistry

    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as owner,
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as other,
    ):
        registry = WorkRegistry(owner)
        submitter = WorkRegistry(other)
        parent = WorkRequest(
            work_type=WorkType.EXPERIMENT_EXECUTION,
            semantic_key=f"parent:{uuid4()}",
            input_hash="a" * 64,
            priority=0,
            available_at=datetime(2026, 1, 1, tzinfo=UTC),
            max_attempts=1,
            retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        )
        child = replace(
            parent,
            semantic_key=f"child:{uuid4()}",
            input_hash="b" * 64,
            parent_work_id=parent.work_id,
            dependencies=(parent.work_id,),
        )
        registry.enqueue(parent)
        try:
            claim = registry.claim("parent", timedelta(minutes=1), (WorkType.EXPERIMENT_EXECUTION,))
            assert claim and claim.work_id == parent.work_id
            other.execute("SET lock_timeout='200ms'")
            with registry.publication(claim, result_hash="c" * 64):
                assert submitter.enqueue(child) == child.work_id
                assert (
                    submitter.claim("child", timedelta(minutes=1), (WorkType.EXPERIMENT_EXECUTION,))
                    is None
                )
            claimed = submitter.claim(
                "child", timedelta(minutes=1), (WorkType.EXPERIMENT_EXECUTION,)
            )
            assert claimed and claimed.work_id == child.work_id
        finally:
            if registry.state(child.work_id) is not None:
                registry.cancel(child.work_id)
            registry.cancel(parent.work_id)


def test_bulk_fixture_ingestion_waits_for_identity_before_team_updates(tmp_path: Path) -> None:
    from football.product.api_football import ApiFootballClient, ApiResponse
    from football.product.domain import MODEL_ARTIFACT_PATH, stable_id
    from football.product.sync import ProductSync

    with (
        committed_product_fixture() as (owner, competition, fixture),
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as worker,
        psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as observer,
    ):
        home, away, kickoff, now = owner.execute(
            "SELECT home_team_id,away_team_id,kickoff_at,clock_timestamp() "
            "FROM football.product_fixtures WHERE fixture_id=%s",
            (fixture,),
        ).fetchone()
        sync = ProductSync(worker, ApiFootballClient("stored-only"), tmp_path, MODEL_ARTIFACT_PATH)
        snapshot = sync._record_response(
            f"lock-test:{uuid4()}", ApiResponse("/fixtures", now, b"{}", (), None)
        )
        native_competition, native_match, native_home, native_away = [
            str(uuid4().int) for _ in range(4)
        ]
        provider = stable_id("provider", "api_football")
        with owner.transaction():
            owner.execute(
                """INSERT INTO football.competition_provider_mappings
                (competition_id,provider_id,provider_competition_id,first_seen_at,last_seen_at,
                 mapping_method,mapping_confidence,source_snapshot_id)
                VALUES (%s,%s,%s,%s,%s,'deterministic',1,%s)""",
                (competition, provider, native_competition, now, now, snapshot),
            )
            owner.execute(
                """INSERT INTO football.match_provider_mappings
                (match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,
                 mapping_method,mapping_confidence,source_snapshot_id)
                VALUES (%s,%s,%s,%s,%s,'deterministic',1,%s)""",
                (fixture, provider, native_match, now, now, snapshot),
            )
            owner.execute(
                """INSERT INTO football.product_team_aliases
                (provider_code,provider_team_id,normalized_name,team_id)
                VALUES ('api_football',%s,'home',%s),('api_football',%s,'away',%s)""",
                (native_home, home, native_away, away),
            )
        row = {
            "fixture": {
                "id": int(native_match),
                "date": kickoff.isoformat(),
                "status": {"short": "LIVE"},
                "venue": {},
            },
            "league": {"id": int(native_competition), "season": 2026, "country": "England"},
            "teams": {
                "home": {"id": int(native_home), "name": "Home"},
                "away": {"id": int(native_away), "name": "Away"},
            },
            "goals": {"home": None, "away": None},
        }
        worker.execute("SET statement_timeout='5s'")

        def update() -> int:
            with worker.transaction(force_rollback=True):
                return len(sync._store_fixtures([row], snapshot, now))

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                with owner.transaction():
                    acquire_locks(
                        owner, (LockRequest(LockClass.IDENTITY, "product-identity-admission"),)
                    )
                    result = executor.submit(update)
                    deadline = monotonic() + 3
                    blocked = False
                    while monotonic() < deadline:
                        blockers = observer.execute(
                            "SELECT pg_blocking_pids(%s)", (worker.info.backend_pid,)
                        ).fetchone()[0]
                        if owner.info.backend_pid in blockers:
                            blocked = True
                            break
                        if result.done():
                            break
                        sleep(0.01)
                    assert blocked, "bulk writer did not reach the controlled identity wait"
                    available = True
                    try:
                        with observer.transaction(force_rollback=True):
                            observer.execute(
                                "SELECT 1 FROM football.product_teams "
                                "WHERE team_id=%s FOR UPDATE NOWAIT",
                                (home,),
                            )
                    except psycopg.errors.LockNotAvailable:
                        available = False
                    if available:
                        owner.execute(
                            "UPDATE football.product_teams SET name='Identity owner' "
                            "WHERE team_id=%s",
                            (home,),
                        )
                assert result.result(timeout=5) == 1
            assert available, "team row was locked while waiting for identity coordination"
        finally:
            with owner.transaction():
                owner.execute(
                    "DELETE FROM football.product_team_aliases "
                    "WHERE provider_code='api_football' AND provider_team_id=ANY(%s)",
                    ([native_home, native_away],),
                )
                owner.execute(
                    "DELETE FROM football.match_provider_mappings "
                    "WHERE provider_id=%s AND provider_match_id=%s",
                    (provider, native_match),
                )
                owner.execute(
                    "DELETE FROM football.competition_provider_mappings "
                    "WHERE provider_id=%s AND provider_competition_id=%s",
                    (provider, native_competition),
                )


@pytest.mark.parametrize("operation", ["reconciliation", "correction"])
def test_legacy_identity_mutations_reject_coordination_after_work(
    locks: Connection[Any], operation: str
) -> None:
    from football.product.fixture_reconciliation import reconcile_product_fixtures
    from football.product.identity_correction import revoke_team_correction

    acquire_locks(locks, (LockRequest(LockClass.WORK, f"work:{uuid4()}"),))
    with pytest.raises(LockOrderError), locks.transaction():
        if operation == "reconciliation":
            reconcile_product_fixtures(locks)
        else:
            revoke_team_correction(locks, uuid4(), "test lock order")


def test_sql_history_qualification_rejects_identity_after_work(locks: Connection[Any]) -> None:
    acquire_locks(locks, (LockRequest(LockClass.WORK, f"work:{uuid4()}"),))
    with pytest.raises(psycopg.Error) as failure, locks.transaction():
        locks.execute("SELECT football.record_product_history_decisions(ARRAY[]::uuid[])")
    assert failure.value.sqlstate == "MFL01"


def test_sql_identity_admission_rejects_identity_after_work(
    locks: Connection[Any], tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    from football.product.historical_backfill import HistoricalBackfillStore

    from tests.integration.historical_source_fixture import test_snapshot as source_snapshot

    provider = f"lock_test_{uuid4().hex}"
    snapshot = source_snapshot(
        HistoricalBackfillStore(locks, provider, "Lock test", "test-v1"),
        tmp_path,
        source_identity="lock-order",
        source_revision="test-v1",
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        manifest_path="raw/lock-order.json",
    )
    acquire_locks(locks, (LockRequest(LockClass.WORK, f"work:{uuid4()}"),))
    with pytest.raises(psycopg.Error) as failure, locks.transaction():
        locks.execute(
            """INSERT INTO football.product_identity_admissions
            (entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
             disposition,reason,source_snapshot_id,evidence,evidence_sha256)
            VALUES ('team',%s,%s,%s,'unresolved','UNRESOLVED','lock order',%s,'{}',%s)""",
            (uuid4(), uuid4(), provider, snapshot, "a" * 64),
        )
    assert failure.value.sqlstate == "MFL01"


@pytest.mark.parametrize("entrypoint", ["publisher", "registry"])
def test_fitted_artifact_writers_reject_coordination_after_forecast_publication(
    locks: Connection[Any], tmp_path: Path, entrypoint: str
) -> None:
    from datetime import UTC, datetime

    from football.forecasting.artifacts import (
        ModelArtifactPublisher,
        PortableModelArtifactStore,
        PostgresModelArtifactRegistry,
    )
    from football.forecasting.contracts import ModelFitSpecV1, PointInTimeScopeV1

    from tests.integration.test_canonical_storage import _source_lineage

    _, snapshot, _ = _source_lineage(locks, uuid4().hex)
    dataset = uuid4()
    now = datetime(2026, 1, 1, tzinfo=UTC)
    locks.execute(
        """INSERT INTO football.dataset_versions
        (id,source_snapshot_id,dataset_name,layer,identity_hash,schema_version,
         schema_sha256,normalizer_version,manifest_path,manifest_sha256,status,published_at)
        VALUES (%s,%s,'events','normalized',%s,'v1',%s,'test-v1',%s,%s,'published',%s)""",
        (dataset, snapshot, dataset.hex * 2, "a" * 64, f"manifests/{dataset}.json", "b" * 64, now),
    )
    spec = ModelFitSpecV1(
        model_family="DIXON_COLES_GOALS",
        algorithm_version="dixon-coles-v1",
        config_sha256="c" * 64,
        scope=PointInTimeScopeV1(
            dataset_version_id=dataset,
            source_snapshot_id=snapshot,
            feature_set_version="sprint2-features-v1",
            football_cutoff=now,
            knowledge_cutoff=now,
            knowledge_mode="bitemporal",
            quality_policy_sha256="d" * 64,
            target_set_sha256="e" * 64,
        ),
        code_commit_sha="f" * 40,
        dependency_lock_sha256="1" * 64,
    )
    state = {"contract": "DixonColesModelStateV1", "home_advantage": 0.2}
    artifact = None
    if entrypoint == "registry":
        artifact = PortableModelArtifactStore(tmp_path).publish(
            model_artifact_id=uuid4(),
            fit_spec=spec,
            state=state,
            created_at=now,
        )
    acquire_locks(locks, (LockRequest(LockClass.PUBLICATION, "publication:forecast"),))
    with pytest.raises(LockOrderError), locks.transaction():
        if entrypoint == "publisher":
            ModelArtifactPublisher(locks, tmp_path).publish(
                model_artifact_id=uuid4(),
                fit_spec=spec,
                state=state,
                created_at=now,
            )
        else:
            assert artifact is not None
            PostgresModelArtifactRegistry(locks).register(artifact, spec)


def test_scientific_batch_runner_requires_independent_publication_transactions(
    locks: Connection[Any], tmp_path: Path
) -> None:
    from datetime import UTC, datetime

    from football.forecasting.dataset import PointInTimeMatchDatasetProvider
    from football.forecasting.evidence import Sprint2EvidenceProvenanceV1
    from football.forecasting.execution import Sprint2ExecutionError, Sprint2ExecutionPolicyV1
    from football.forecasting.gate import Sprint2GateService

    from tests.integration.test_canonical_storage import _competition_rules

    service = Sprint2GateService(
        locks,
        tmp_path,
        data_root=tmp_path,
        provenance=Sprint2EvidenceProvenanceV1("a" * 40, "b" * 64),
    )
    with pytest.raises(Sprint2ExecutionError, match="autocommit"):
        service._runner(
            PointInTimeMatchDatasetProvider(locks),
            Sprint2ExecutionPolicyV1(),
            datetime(2026, 1, 1, tzinfo=UTC),
            _competition_rules(),
        )
