from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

from football.canonical_resources.storage import _register_evidence


class _CountingDecision:
    def __init__(self) -> None:
        self.calls = 0

    @property
    def decision_id(self) -> UUID:
        self.calls += 1
        return UUID(int=900)


class _EvidenceCursor:
    def __init__(self) -> None:
        self.inserted: list[tuple[object, ...]] = []
        self.selected: list[tuple[object, ...]] = []

    def execute(self, query: str, values: tuple[object, ...]) -> _EvidenceCursor:
        if query.lstrip().startswith("INSERT INTO football.canonical_resolution_evidence"):
            self.inserted.append(values)
        else:
            self.selected = [tuple(row[1:]) for row in self.inserted]
        return self

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.selected


def test_canonical_evidence_registration_hashes_large_decision_once() -> None:
    decision = _CountingDecision()
    candidates = tuple(
        SimpleNamespace(
            observation=SimpleNamespace(
                observation_id=UUID(int=identity),
                sha256=f"{identity:064x}",
            ),
            value_sha256=f"{identity + 100:064x}",
        )
        for identity in range(1, 5)
    )
    resolution = SimpleNamespace(
        decision=decision,
        candidates=candidates,
        supporting=(),
        conflicting=(),
    )
    cursor = _EvidenceCursor()

    _register_evidence(cast(Any, cursor), cast(Any, resolution))

    assert decision.calls == 1
    assert len(cursor.inserted) == len(candidates)
