import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkContractError,
    WorkRequest,
    WorkState,
    WorkType,
)
from football.work.storage import WorkConflict, WorkLeaseLost, WorkRegistry
from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row


@pytest.fixture
def work_db() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"], row_factory=dict_row) as connection,
        connection.transaction(force_rollback=True),
    ):
        yield connection


def request(**changes: Any) -> WorkRequest:
    values: dict[str, Any] = dict(
        work_type=WorkType.NORMALIZATION,
        semantic_key=f"test:{uuid4()}",
        input_hash="a" * 64,
        priority=0,
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        max_attempts=3,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
    )
    return WorkRequest(**(values | changes))


def enqueue(connection: Connection[Any], **changes: Any) -> dict[str, Any]:
    item = request(**changes)
    policy = item.retry_policy
    row = connection.execute(
        "SELECT * FROM football.enqueue_work(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            item.work_id,
            item.work_type.value,
            item.semantic_key,
            item.input_hash,
            item.priority,
            item.available_at,
            item.max_attempts,
            policy.base_delay.total_seconds(),
            policy.max_delay.total_seconds(),
            policy.multiplier,
            list(item.dependencies),
            item.parent_work_id,
        ),
    ).fetchone()
    assert row is not None
    return row


def claim(
    connection: Connection[Any], *, owner: str = "worker", lease: timedelta = timedelta(minutes=1)
) -> dict[str, Any] | None:
    return connection.execute(
        "SELECT * FROM football.claim_work(%s,%s,%s)",
        (owner, lease, [WorkType.NORMALIZATION.value]),
    ).fetchone()


def ownership(item: dict[str, Any]) -> tuple[Any, ...]:
    return (item["work_id"], item["lease_owner"], item["lease_token"], item["generation"])


def finish(connection: Connection[Any], item: dict[str, Any]) -> dict[str, Any]:
    result = connection.execute(
        "SELECT * FROM football.finish_work(%s,%s,%s,%s,%s)", (*ownership(item), "b" * 64)
    ).fetchone()
    assert result is not None
    return result


def expire(connection: Connection[Any], item: dict[str, Any]) -> None:
    connection.execute(
        "SELECT pg_sleep(GREATEST(0,extract(epoch "
        "FROM (%s::timestamptz-clock_timestamp())))+0.005)",
        (item["lease_until"],),
    )


def test_enqueue_is_idempotent_but_cannot_replace_semantic_inputs(work_db: Connection[Any]) -> None:
    first = enqueue(work_db, semantic_key="same")
    again = enqueue(work_db, semantic_key="same")
    assert first == again
    with pytest.raises(psycopg.errors.UniqueViolation), work_db.transaction():
        enqueue(work_db, semantic_key="same", input_hash="c" * 64)
    assert work_db.execute("SELECT count(*) AS n FROM football.work_items").fetchone()["n"] == 1


def test_claim_fences_ownership_and_terminal_success_cannot_resurrect(
    work_db: Connection[Any],
) -> None:
    item = enqueue(work_db)
    leased = claim(work_db)
    assert leased and leased["work_id"] == item["work_id"]
    assert (
        leased["state"] == "RUNNING" and leased["attempt_count"] == 1 and leased["generation"] == 1
    )
    assert claim(work_db) is None
    done = finish(work_db, leased)
    assert done["state"] == "SUCCEEDED" and done["result_hash"] == "b" * 64
    assert done["lease_token"] is None and done["finished_at"] is not None
    assert claim(work_db) is None
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        finish(work_db, leased)


def test_claim_priority_and_future_schedule_are_respected(work_db: Connection[Any]) -> None:
    enqueue(work_db, priority=99, available_at=datetime(2100, 1, 1, tzinfo=UTC))
    low = enqueue(work_db, priority=-1)
    high = enqueue(work_db, priority=5)
    assert claim(work_db)["work_id"] == high["work_id"]
    assert claim(work_db)["work_id"] == low["work_id"]
    assert claim(work_db) is None


def test_expired_worker_is_replaced_with_new_fencing_epoch(work_db: Connection[Any]) -> None:
    enqueue(work_db)
    old = claim(work_db, lease=timedelta(milliseconds=5))
    assert old is not None
    expire(work_db, old)
    current = claim(work_db, owner="replacement")
    assert current and current["work_id"] == old["work_id"]
    assert (
        current["generation"] > old["generation"] and current["lease_token"] != old["lease_token"]
    )
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        finish(work_db, old)
    assert finish(work_db, current)["state"] == "SUCCEEDED"


def test_heartbeat_requires_unexpired_exact_ownership(work_db: Connection[Any]) -> None:
    enqueue(work_db)
    leased = claim(work_db)
    renewed = work_db.execute(
        "SELECT * FROM football.heartbeat_work(%s,%s,%s,%s,%s)",
        (*ownership(leased), timedelta(minutes=2)),
    ).fetchone()
    assert renewed["lease_until"] > leased["lease_until"]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        work_db.execute(
            "SELECT * FROM football.heartbeat_work(%s,%s,%s,%s,%s)",
            (
                leased["work_id"],
                "wrong",
                leased["lease_token"],
                leased["generation"],
                timedelta(minutes=2),
            ),
        )


def test_crashed_last_attempt_fails_instead_of_reclaiming_forever(work_db: Connection[Any]) -> None:
    item = enqueue(work_db, max_attempts=1)
    leased = claim(work_db, lease=timedelta(milliseconds=5))
    expire(work_db, leased)
    assert claim(work_db) is None
    state = work_db.execute(
        "SELECT state,last_error_code,lease_token FROM football.work_items WHERE work_id=%s",
        (item["work_id"],),
    ).fetchone()
    assert state == dict(state="FAILED", last_error_code="LEASE_EXPIRED", lease_token=None)


def test_cancellation_revokes_publication_before_completion(work_db: Connection[Any]) -> None:
    item = enqueue(work_db)
    leased = claim(work_db)
    cancelled = work_db.execute(
        "SELECT * FROM football.cancel_work(%s)", (item["work_id"],)
    ).fetchone()
    assert cancelled["state"] == "CANCELLED" and cancelled["lease_token"] is None
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        finish(work_db, leased)
    assert claim(work_db) is None


@pytest.mark.parametrize(
    ("classification", "state"),
    [
        ("NON_RETRYABLE", "FAILED"),
        ("BLOCKED_EXTERNAL", "BLOCKED"),
        ("CANCELLED", "CANCELLED"),
        ("RETRYABLE", "RETRY_WAIT"),
    ],
)
def test_common_retry_classification(
    work_db: Connection[Any], classification: str, state: str
) -> None:
    enqueue(work_db)
    leased = claim(work_db)
    result = work_db.execute(
        "SELECT * FROM football.fail_work(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (*ownership(leased), classification, "TEST_FAILURE", "Explicit test failure", None, None),
    ).fetchone()
    assert result["state"] == state and result["lease_token"] is None


def test_retry_after_and_provider_cooldown_bound_next_attempt(work_db: Connection[Any]) -> None:
    enqueue(work_db, retry_policy=RetryPolicy(timedelta(seconds=2), timedelta(seconds=8), 2))
    leased = claim(work_db)
    now = work_db.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
    cooldown = now + timedelta(minutes=3)
    result = work_db.execute(
        "SELECT * FROM football.fail_work(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            *ownership(leased),
            "RETRYABLE",
            "RATE_LIMIT",
            "Cooldown",
            now + timedelta(minutes=2),
            cooldown,
        ),
    ).fetchone()
    assert result["available_at"] >= cooldown and claim(work_db) is None


def test_dependency_waits_for_success_and_is_sealed_with_semantic_inputs(
    work_db: Connection[Any],
) -> None:
    parent = enqueue(work_db)
    child = enqueue(
        work_db, priority=100, dependencies=(parent["work_id"],), parent_work_id=parent["work_id"]
    )
    leased = claim(work_db)
    assert leased["work_id"] == parent["work_id"]
    assert claim(work_db) is None
    finish(work_db, leased)
    assert claim(work_db)["work_id"] == child["work_id"]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        work_db.execute(
            "INSERT INTO football.work_dependencies(work_id,dependency_work_id) VALUES (%s,%s)",
            (parent["work_id"], child["work_id"]),
        )


def test_missing_dependency_rejects_entire_enqueue(work_db: Connection[Any]) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation), work_db.transaction():
        enqueue(work_db, dependencies=(uuid4(),))
    assert work_db.execute("SELECT count(*) AS n FROM football.work_items").fetchone()["n"] == 0


def test_enqueue_rolls_back_with_triggering_domain_transaction(work_db: Connection[Any]) -> None:
    with work_db.transaction(force_rollback=True):
        item = enqueue(work_db)
        assert item["state"] == "PENDING"
    assert work_db.execute("SELECT count(*) AS n FROM football.work_items").fetchone()["n"] == 0


@pytest.fixture
def worker() -> Iterator[tuple[Connection[Any], WorkRegistry, list[UUID]]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection:
        registry = WorkRegistry(connection)
        identities: list[UUID] = []
        connection.execute("CREATE TEMP TABLE work_results(work_id uuid PRIMARY KEY,value integer)")
        try:
            yield connection, registry, identities
        finally:
            for identity in identities:
                registry.cancel(identity)


def worker_request(registry: WorkRegistry, identities: list[UUID], **changes: Any) -> UUID:
    identity = registry.enqueue(request(work_type=WorkType.READ_MODEL_PROJECTION, **changes))
    identities.append(identity)
    return identity


def worker_claim(registry: WorkRegistry, *, lease: timedelta = timedelta(minutes=1)) -> Any:
    item = registry.claim("worker", lease, (WorkType.READ_MODEL_PROJECTION,))
    assert item is not None
    return item


def test_worker_claim_and_heartbeat_finish_their_transactions_before_external_work(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    identity = worker_request(registry, identities)
    assert connection.info.transaction_status == TransactionStatus.IDLE
    leased = worker_claim(registry)
    assert (
        leased.work_id == identity and connection.info.transaction_status == TransactionStatus.IDLE
    )
    renewed = registry.heartbeat(leased, timedelta(minutes=2))
    assert renewed.lease_until > leased.lease_until
    assert connection.info.transaction_status == TransactionStatus.IDLE
    with registry.publication(renewed, result_hash="b" * 64) as publisher:
        publisher.execute("INSERT INTO work_results VALUES (%s,1)", (identity,))
    assert registry.state(identity) == WorkState.SUCCEEDED
    assert connection.info.transaction_status == TransactionStatus.IDLE
    assert connection.execute(
        "SELECT value FROM work_results WHERE work_id=%s", (identity,)
    ).fetchone() == (1,)


def test_publication_exception_rolls_back_domain_results_and_completion(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    identity = worker_request(registry, identities)
    leased = worker_claim(registry)
    with (
        pytest.raises(RuntimeError, match="publication failed"),
        registry.publication(leased, result_hash="b" * 64) as publisher,
    ):
        publisher.execute("INSERT INTO work_results VALUES (%s,1)", (identity,))
        raise RuntimeError("publication failed")
    assert connection.execute("SELECT count(*) FROM work_results").fetchone() == (0,)
    assert registry.state(identity) == WorkState.RUNNING
    assert (
        registry.fail(
            leased,
            RetryClassification.RETRYABLE,
            error_code="TEST_FAILURE",
            error_message="Publication rolled back",
        )
        == WorkState.RETRY_WAIT
    )


def test_lease_expiry_during_publication_rolls_back_earlier_domain_writes(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    identity = worker_request(registry, identities)
    leased = worker_claim(registry, lease=timedelta(milliseconds=100))
    with (
        pytest.raises(WorkLeaseLost),
        registry.publication(leased, result_hash="b" * 64) as publisher,
    ):
        publisher.execute("INSERT INTO work_results VALUES (%s,1)", (identity,))
        publisher.execute(
            "SELECT pg_sleep(GREATEST(0,extract(epoch "
            "FROM (%s::timestamptz-clock_timestamp())))+0.005)",
            (leased.lease_until,),
        )
    assert connection.execute("SELECT count(*) FROM work_results").fetchone() == (0,)
    replacement = worker_claim(registry)
    assert replacement.generation > leased.generation


def test_cancelled_worker_cannot_enter_publication(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    identity = worker_request(registry, identities)
    leased = worker_claim(registry)
    assert registry.cancel(identity) == WorkState.CANCELLED
    with pytest.raises(WorkLeaseLost), registry.publication(leased, result_hash="b" * 64):
        pytest.fail("cancelled work received publication rights")
    assert connection.execute("SELECT count(*) FROM work_results").fetchone() == (0,)


def test_work_control_rejects_an_outer_transaction_but_enqueue_joins_it(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    with connection.transaction(force_rollback=True):
        identity = registry.enqueue(request(work_type=WorkType.READ_MODEL_PROJECTION))
        with pytest.raises(WorkContractError, match="idle connection"):
            registry.claim("worker", timedelta(minutes=1), (WorkType.READ_MODEL_PROJECTION,))
    assert registry.state(identity) is None


def test_python_adapter_reports_semantic_conflicts(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    _, registry, identities = worker
    item = request(work_type=WorkType.READ_MODEL_PROJECTION)
    identities.append(registry.enqueue(item))
    from dataclasses import replace

    with pytest.raises(WorkConflict):
        registry.enqueue(replace(item, input_hash="b" * 64))


def test_claim_skips_a_pending_row_locked_by_another_connection(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]],
) -> None:
    connection, registry, identities = worker
    first = worker_request(registry, identities, priority=10)
    second = worker_request(registry, identities, priority=0)
    with connection.transaction():
        connection.execute(
            "SELECT 1 FROM football.work_items WHERE work_id=%s FOR UPDATE", (first,)
        )
        with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as other:
            other.execute("SET statement_timeout='2s'")
            claimed = worker_claim(WorkRegistry(other))
            assert claimed.work_id == second
    assert worker_claim(registry).work_id == first


@pytest.mark.parametrize(("attempt", "expected"), [(1, 1), (2, 2), (4, 8), (2**31 - 1, 8)])
def test_shared_exponential_backoff_caps_without_overflow(
    work_db: Connection[Any], attempt: int, expected: int
) -> None:
    assert (
        work_db.execute(
            "SELECT football.work_retry_seconds(1,8,2,%s) AS delay", (attempt,)
        ).fetchone()["delay"]
        == expected
    )


def test_retry_budget_exhaustion_is_terminal(work_db: Connection[Any]) -> None:
    enqueue(work_db, max_attempts=1)
    leased = claim(work_db)
    result = work_db.execute(
        "SELECT * FROM football.fail_work(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (*ownership(leased), "RETRYABLE", "TEST_FAILURE", "Budget exhausted", None, None),
    ).fetchone()
    assert result["state"] == "FAILED" and claim(work_db) is None


def test_external_block_requires_explicit_release(work_db: Connection[Any]) -> None:
    item = enqueue(work_db)
    leased = claim(work_db)
    work_db.execute(
        "SELECT * FROM football.fail_work(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            *ownership(leased),
            "BLOCKED_EXTERNAL",
            "AUTHORIZATION_REQUIRED",
            "Wait for authorization",
            None,
            None,
        ),
    )
    assert claim(work_db) is None
    released = work_db.execute(
        "SELECT * FROM football.release_blocked_work(%s,clock_timestamp())", (item["work_id"],)
    ).fetchone()
    assert released["state"] == "PENDING"
    assert claim(work_db)["work_id"] == item["work_id"]


def test_expired_heartbeat_cannot_resurrect_publication_rights(work_db: Connection[Any]) -> None:
    enqueue(work_db)
    leased = claim(work_db, lease=timedelta(milliseconds=5))
    expire(work_db, leased)
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        work_db.execute(
            "SELECT * FROM football.heartbeat_work(%s,%s,%s,%s,%s)",
            (*ownership(leased), timedelta(minutes=1)),
        )


def test_dependency_seal_is_checked_before_commit(work_db: Connection[Any]) -> None:
    enqueue(work_db)
    work_db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    with pytest.raises(psycopg.errors.CheckViolation), work_db.transaction():
        work_db.execute(
            """INSERT INTO football.work_items(work_id,work_type,semantic_key,
            input_hash,priority,available_at,max_attempts,retry_base_seconds,retry_cap_seconds,
            retry_multiplier) VALUES (%s,'NORMALIZATION',%s,%s,0,clock_timestamp(),1,0,0,1)""",
            (uuid4(), f"unsealed:{uuid4()}", "a" * 64),
        )


def test_enqueue_seals_dependencies_when_caller_uses_immediate_constraints(
    work_db: Connection[Any],
) -> None:
    work_db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    item = enqueue(work_db)
    work_db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    assert item["dependencies_sealed"]


@pytest.mark.parametrize("previous", list(WorkState))
@pytest.mark.parametrize("following", list(WorkState))
def test_shared_state_machine_rejects_undefined_transitions(
    work_db: Connection[Any], previous: WorkState, following: WorkState
) -> None:
    allowed = {
        WorkState.PENDING: {WorkState.RUNNING, WorkState.FAILED, WorkState.CANCELLED},
        WorkState.RETRY_WAIT: {WorkState.RUNNING, WorkState.FAILED, WorkState.CANCELLED},
        WorkState.RUNNING: {
            WorkState.RETRY_WAIT,
            WorkState.SUCCEEDED,
            WorkState.FAILED,
            WorkState.CANCELLED,
            WorkState.BLOCKED,
        },
        WorkState.BLOCKED: {WorkState.PENDING, WorkState.FAILED, WorkState.CANCELLED},
    }
    expected = previous == following or following in allowed.get(previous, set())
    assert (
        work_db.execute(
            "SELECT football.work_transition_allowed(%s,%s) AS allowed",
            (previous.value, following.value),
        ).fetchone()["allowed"]
        == expected
    )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE football.work_items SET input_hash=repeat('b',64)",
        "UPDATE football.work_items SET dependencies_sealed=false",
        "DELETE FROM football.work_items",
        "TRUNCATE football.work_items CASCADE",
        "TRUNCATE football.work_dependencies",
    ],
)
def test_work_identity_and_dependency_history_cannot_be_erased(
    work_db: Connection[Any], statement: str
) -> None:
    enqueue(work_db)
    work_db.execute("SET CONSTRAINTS ALL IMMEDIATE")
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        work_db.execute(statement)


def test_terminal_outcome_cannot_be_reopened_by_direct_update(work_db: Connection[Any]) -> None:
    enqueue(work_db)
    finish(work_db, claim(work_db))
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState), work_db.transaction():
        work_db.execute(
            "UPDATE football.work_items SET state='PENDING',finished_at=NULL,result_hash=NULL"
        )


def test_retry_with_changed_dependencies_is_not_a_new_semantic_request(
    work_db: Connection[Any],
) -> None:
    parent = enqueue(work_db)
    enqueue(work_db, semantic_key="child", dependencies=(parent["work_id"],))
    with pytest.raises(psycopg.errors.UniqueViolation), work_db.transaction():
        enqueue(work_db, semantic_key="child", dependencies=())


@pytest.mark.parametrize("kind", list(WorkType))
def test_every_supported_work_type_uses_the_shared_queue(
    work_db: Connection[Any], kind: WorkType
) -> None:
    item = enqueue(work_db, work_type=kind)
    assert (
        item["work_type"] == kind.value
        and item["state"] == "PENDING"
        and item["dependencies_sealed"]
    )


def test_duplicate_enqueue_cannot_silently_replace_priority(work_db: Connection[Any]) -> None:
    enqueue(work_db, semantic_key="same-priority", priority=0)
    with pytest.raises(psycopg.errors.UniqueViolation), work_db.transaction():
        enqueue(work_db, semantic_key="same-priority", priority=10)


def test_release_does_not_bypass_exhausted_attempt_budget(work_db: Connection[Any]) -> None:
    item = enqueue(work_db, max_attempts=1)
    leased = claim(work_db)
    work_db.execute(
        "SELECT * FROM football.fail_work(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (*ownership(leased), "BLOCKED_EXTERNAL", "AUTHORIZATION_REQUIRED", "Blocked", None, None),
    )
    result = work_db.execute(
        "SELECT * FROM football.release_blocked_work(%s,clock_timestamp())", (item["work_id"],)
    ).fetchone()
    assert result["state"] == "FAILED" and claim(work_db) is None


@pytest.mark.parametrize("complete", [True, False])
def test_domain_publication_completion_and_downstream_enqueue_are_atomic(
    worker: tuple[Connection[Any], WorkRegistry, list[UUID]], complete: bool
) -> None:
    from contextlib import nullcontext

    connection, registry, identities = worker
    parent = worker_request(registry, identities)
    leased = worker_claim(registry)
    child = request(work_type=WorkType.FEATURE_BUILD, dependencies=(parent,), parent_work_id=parent)
    outcome = nullcontext() if complete else pytest.raises(RuntimeError, match="abort publication")
    with outcome, registry.publication(leased, result_hash="b" * 64) as publisher:
        publisher.execute("INSERT INTO work_results VALUES (%s,1)", (parent,))
        assert registry.enqueue(child) == child.work_id
        if not complete:
            raise RuntimeError("abort publication")
    if complete:
        identities.append(child.work_id)
        assert registry.state(parent) == WorkState.SUCCEEDED
        assert registry.state(child.work_id) == WorkState.PENDING
        claimed = registry.claim("feature-worker", timedelta(minutes=1), (WorkType.FEATURE_BUILD,))
        assert claimed and claimed.work_id == child.work_id
        assert connection.execute("SELECT count(*) FROM work_results").fetchone() == (1,)
    else:
        assert registry.state(parent) == WorkState.RUNNING
        assert registry.state(child.work_id) is None
        assert connection.execute("SELECT count(*) FROM work_results").fetchone() == (0,)


def test_exhausted_crash_cleanup_does_not_hide_other_runnable_work(
    work_db: Connection[Any],
) -> None:
    exhausted = enqueue(work_db, priority=100, max_attempts=1)
    leased = claim(work_db, lease=timedelta(milliseconds=5))
    ready = enqueue(work_db, priority=0)
    expire(work_db, leased)
    picked = claim(work_db)
    assert picked is not None and picked["work_id"] == ready["work_id"]
    assert (
        work_db.execute(
            "SELECT state FROM football.work_items WHERE work_id=%s", (exhausted["work_id"],)
        ).fetchone()["state"]
        == "FAILED"
    )


@pytest.mark.parametrize("duration", ["infinity", "-infinity", "0 seconds"])
def test_sql_claim_rejects_unbounded_or_nonpositive_leases(
    work_db: Connection[Any], duration: str
) -> None:
    enqueue(work_db)
    with pytest.raises(psycopg.errors.InvalidParameterValue), work_db.transaction():
        work_db.execute(
            "SELECT * FROM football.claim_work(%s,%s::interval,%s)",
            ("worker", duration, [WorkType.NORMALIZATION.value]),
        )
