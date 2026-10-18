from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest
from football.storage.locks import LockClass, LockOrderError, LockRequest, ordered_locks


def test_locks_use_one_class_order_and_stable_key_order() -> None:
    requests = (
        LockRequest(LockClass.PUBLICATION, "publication:one"),
        LockRequest(LockClass.MODEL, "model:one"),
        LockRequest(LockClass.FEATURE, "feature:one"),
        LockRequest(LockClass.WORK, "work:two"),
        LockRequest(LockClass.FIXTURE, "fixture:two"),
        LockRequest(LockClass.COMPETITION, "competition:one"),
        LockRequest(LockClass.FIXTURE, "fixture:one"),
    )
    result = ordered_locks(requests)
    assert [(item.lock_class, item.key) for item in result] == [
        (LockClass.COMPETITION, "competition:one"),
        (LockClass.FIXTURE, "fixture:one"),
        (LockClass.FIXTURE, "fixture:two"),
        (LockClass.WORK, "work:two"),
        (LockClass.FEATURE, "feature:one"),
        (LockClass.MODEL, "model:one"),
        (LockClass.PUBLICATION, "publication:one"),
    ]
    assert ordered_locks(tuple(reversed(requests))) == result


def test_repeated_lock_requests_are_idempotent_and_cannot_mix_hash_conventions() -> None:
    item = LockRequest(LockClass.IDENTITY, "product_fixture_crosswalk", legacy_hash=True)
    assert ordered_locks((item, item)) == (item,)
    with pytest.raises(LockOrderError):
        ordered_locks((item, LockRequest(LockClass.IDENTITY, item.key)))
    with pytest.raises(FrozenInstanceError):
        cast(Any, item).key = "changed"


@pytest.mark.parametrize(
    ("kind", "key"), [(1, "fixture:one"), (LockClass.FIXTURE, ""), (LockClass.FIXTURE, " ")]
)
def test_lock_requests_require_explicit_class_and_nonblank_key(kind: Any, key: str) -> None:
    with pytest.raises(LockOrderError):
        LockRequest(kind, key)
