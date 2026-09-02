from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import canonical_json_bytes

DependencyStateV1 = Literal[
    "VALID",
    "STALE",
    "SUPERSEDED",
    "AFFECTED_BY_SOURCE_CORRECTION",
    "REBUILD_REQUIRED",
]
_STATES = frozenset(
    ("VALID", "STALE", "SUPERSEDED", "AFFECTED_BY_SOURCE_CORRECTION", "REBUILD_REQUIRED")
)


class DependencyContractError(ValueError):
    """A dependency edge or graph violates its immutable lineage contract."""


@dataclass(frozen=True, slots=True)
class DependencyEdgeV1:
    """One immutable, directed lineage edge between versioned evidence nodes."""

    edge_id: str
    upstream_ref: str
    upstream_kind: str
    downstream_ref: str
    downstream_kind: str
    state: DependencyStateV1
    created_at: datetime
    source_change_set_ref: str | None = None
    revision: int = 1
    contract: str = "DependencyEdgeV1"

    def __post_init__(self) -> None:
        if self.contract != "DependencyEdgeV1":
            raise DependencyContractError("unsupported dependency edge contract")
        if any(
            not value
            for value in (
                self.edge_id,
                self.upstream_ref,
                self.upstream_kind,
                self.downstream_ref,
                self.downstream_kind,
            )
        ):
            raise DependencyContractError("dependency edge identity and node kinds are required")
        if self.upstream_ref == self.downstream_ref:
            raise DependencyContractError("dependency edge cannot point to itself")
        if self.state not in _STATES:
            raise DependencyContractError("dependency state is unsupported")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DependencyContractError("dependency edge timestamp must include a timezone")
        if self.revision <= 0:
            raise DependencyContractError("dependency edge revision must be positive")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "edge_id": self.edge_id,
            "upstream_ref": self.upstream_ref,
            "upstream_kind": self.upstream_kind,
            "downstream_ref": self.downstream_ref,
            "downstream_kind": self.downstream_kind,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "source_change_set_ref": self.source_change_set_ref,
            "revision": self.revision,
        }


@dataclass(frozen=True, slots=True)
class DependencyGraphV1:
    """An immutable collection of lineage edges with deterministic lookups."""

    edges: tuple[DependencyEdgeV1, ...]
    contract: str = "DependencyGraphV1"

    def __post_init__(self) -> None:
        if self.contract != "DependencyGraphV1":
            raise DependencyContractError("unsupported dependency graph contract")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise DependencyContractError("dependency edge IDs must be unique")

    def dependents_of(self, upstream_ref: str) -> tuple[DependencyEdgeV1, ...]:
        return tuple(edge for edge in self.edges if edge.upstream_ref == upstream_ref)

    def dependencies_of(self, downstream_ref: str) -> tuple[DependencyEdgeV1, ...]:
        return tuple(edge for edge in self.edges if edge.downstream_ref == downstream_ref)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class DerivedStateRecordV1:
    """Append-only state evidence for a derived node after upstream change."""

    record_id: str
    node_ref: str
    node_kind: str
    state: DependencyStateV1
    recorded_at: datetime
    reason: str
    source_change_set_ref: str | None = None
    prior_state: DependencyStateV1 | None = None
    contract: str = "DerivedStateRecordV1"

    def __post_init__(self) -> None:
        if self.contract != "DerivedStateRecordV1":
            raise DependencyContractError("unsupported derived state contract")
        if not all((self.record_id, self.node_ref, self.node_kind, self.reason)):
            raise DependencyContractError("derived state identity and reason are required")
        if self.state not in _STATES or (
            self.prior_state is not None and self.prior_state not in _STATES
        ):
            raise DependencyContractError("derived state is unsupported")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise DependencyContractError("derived state timestamp must include a timezone")
        if self.prior_state == self.state:
            raise DependencyContractError("derived state must record a transition")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "record_id": self.record_id,
            "node_ref": self.node_ref,
            "node_kind": self.node_kind,
            "state": self.state,
            "recorded_at": self.recorded_at.isoformat(),
            "reason": self.reason,
            "source_change_set_ref": self.source_change_set_ref,
            "prior_state": self.prior_state,
        }
