from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest
from football.work.contracts import RetryPolicy, WorkContractError, WorkRequest, WorkType

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def request(**changes: Any) -> WorkRequest:
    values: dict[str, Any] = dict(
        work_type=WorkType.NORMALIZATION,
        semantic_key="normalize:fotmob:retained-snapshot",
        input_hash="a" * 64,
        priority=0,
        available_at=NOW,
        max_attempts=3,
        retry_policy=RetryPolicy(timedelta(seconds=1), timedelta(seconds=8), 2),
    )
    return WorkRequest(**(values | changes))


def test_work_semantic_identity_is_deterministic_and_scoped_by_type() -> None:
    item = request()
    assert item.work_id == request().work_id
    assert item.work_id != request(work_type=WorkType.CANONICAL_RECONCILIATION).work_id
    assert item.work_id != request(semantic_key="normalize:fotmob:another-snapshot").work_id
    # The registry must reject reuse with different inputs rather than silently replacing work.
    assert item.work_id == request(input_hash="b" * 64).work_id


def test_dependencies_are_copied_sorted_and_distinct() -> None:
    source = [UUID(int=2), UUID(int=1)]
    item = request(dependencies=source)
    source.append(UUID(int=3))
    assert item.dependencies == (UUID(int=1), UUID(int=2))
    with pytest.raises(WorkContractError):
        request(dependencies=(UUID(int=1), UUID(int=1)))
    with pytest.raises(WorkContractError):
        request(dependencies=(item.work_id,))
    with pytest.raises(WorkContractError):
        request(parent_work_id=item.work_id)


def test_schedule_preserves_explicit_time_and_normalizes_timezone() -> None:
    local = timezone(timedelta(hours=1))
    assert request(available_at=NOW.astimezone(local)) == request()
    with pytest.raises(WorkContractError, match="timezone"):
        request(available_at=NOW.replace(tzinfo=None))
    with pytest.raises(FrozenInstanceError):
        cast(Any, request()).input_hash = "b" * 64


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("work_type", "NORMALIZATION"),
        ("semantic_key", " "),
        ("input_hash", "A" * 64),
        ("input_hash", "a" * 63),
        ("priority", True),
        ("priority", 2**31),
        ("max_attempts", 0),
        ("max_attempts", True),
        ("dependencies", ("not-a-uuid",)),
        ("parent_work_id", "not-a-uuid"),
        ("retry_policy", None),
    ],
)
def test_invalid_work_contract_inputs_are_rejected(field: str, value: Any) -> None:
    with pytest.raises(WorkContractError):
        request(**{field: value})


@pytest.mark.parametrize(
    ("base", "cap", "multiplier"),
    [
        (-1, 8, 2),
        (2, 1, 2),
        (1, 8, 0),
        (1, 8, float("inf")),
        (1, 8, float("nan")),
        (1, 8, True),
    ],
)
def test_retry_policy_rejects_invalid_or_nonfinite_values(
    base: int, cap: int, multiplier: Any
) -> None:
    with pytest.raises(WorkContractError):
        RetryPolicy(timedelta(seconds=base), timedelta(seconds=cap), multiplier)


def test_constant_and_zero_backoff_require_explicit_policy_values() -> None:
    policy = RetryPolicy(timedelta(), timedelta(), 1)
    assert request(retry_policy=policy).retry_policy == policy
    assert replace(request(), max_attempts=1).max_attempts == 1


@pytest.mark.parametrize("delay", [timedelta(seconds=-1), 0, "immediate"])
def test_lease_expiry_delay_requires_an_explicit_nonnegative_timedelta(delay: Any) -> None:
    with pytest.raises(WorkContractError, match="lease"):
        RetryPolicy(timedelta(seconds=60), timedelta(hours=1), 2, lease_expiry_delay=delay)


def test_lease_expiry_delay_defaults_to_error_backoff_and_can_be_zero() -> None:
    assert RetryPolicy(timedelta(seconds=60), timedelta(hours=1), 2).lease_expiry_delay is None
    policy = RetryPolicy(
        timedelta(seconds=60), timedelta(hours=1), 2, lease_expiry_delay=timedelta()
    )
    assert policy.lease_expiry_delay == timedelta()
