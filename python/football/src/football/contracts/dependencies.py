from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import canonical_json_bytes

DependencyObjectKindV1 = Literal[
    "SOURCE_RESOURCE",
    "CANONICAL_OBSERVATION",
    "DATASET",
    "MODEL_ARTIFACT",
    "FORECAST",
    "EVALUATION",
]
DependencyRelationshipV1 = Literal[
    "INPUT_TO",
    "DERIVED_FROM",
    "BUILT_FROM",
    "FITTED_FROM",
    "FORECAST_WITH",
    "EVALUATED_WITH",
]
DerivedStateV1 = Literal[
    "REBUILD_REQUIRED",
    "AFFECTED_BY_SOURCE_CORRECTION",
    "SUPERSEDED",
]
EffectiveDerivedStateV1 = Literal[
    "VALID",
    "REBUILD_REQUIRED",
    "AFFECTED_BY_SOURCE_CORRECTION",
    "SUPERSEDED",
]

_OBJECT_KINDS = frozenset(
    (
        "SOURCE_RESOURCE",
        "CANONICAL_OBSERVATION",
        "DATASET",
        "MODEL_ARTIFACT",
        "FORECAST",
        "EVALUATION",
    )
)
_RELATIONSHIPS = frozenset(
    (
        "INPUT_TO",
        "DERIVED_FROM",
        "BUILT_FROM",
        "FITTED_FROM",
        "FORECAST_WITH",
        "EVALUATED_WITH",
    )
)
_DERIVED_STATES = frozenset(("REBUILD_REQUIRED", "AFFECTED_BY_SOURCE_CORRECTION", "SUPERSEDED"))


class DependencyContractError(ValueError):
    """A dependency edge or state event violates its immutable contract."""


@dataclass(frozen=True, slots=True)
class DependencyNodeV1:
    kind: DependencyObjectKindV1
    object_id: UUID

    def __post_init__(self) -> None:
        if self.kind not in _OBJECT_KINDS:
            raise DependencyContractError("dependency object kind is unsupported")


@dataclass(frozen=True, slots=True)
class DependencyEdgeV1:
    """One immutable directed edge between durable MatchForge objects."""

    edge_id: UUID
    upstream: DependencyNodeV1
    relationship: DependencyRelationshipV1
    downstream: DependencyNodeV1
    created_at: datetime
    contract_version: str = "dependency-edge-v1"
    contract: str = "DependencyEdgeV1"

    def __post_init__(self) -> None:
        if self.contract != "DependencyEdgeV1":
            raise DependencyContractError("unsupported dependency edge contract")
        if self.relationship not in _RELATIONSHIPS:
            raise DependencyContractError("dependency relationship is unsupported")
        if self.upstream == self.downstream:
            raise DependencyContractError("dependency edge cannot point to itself")
        if not self.contract_version:
            raise DependencyContractError("dependency edge contract version is required")
        _aware(self.created_at, "dependency edge timestamp")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "edge_id": str(self.edge_id),
            "upstream_kind": self.upstream.kind,
            "upstream_id": str(self.upstream.object_id),
            "relationship": self.relationship,
            "downstream_kind": self.downstream.kind,
            "downstream_id": str(self.downstream.object_id),
            "contract_version": self.contract_version,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DependencyGraphV1:
    """A deterministic in-memory view of immutable dependency edges."""

    edges: tuple[DependencyEdgeV1, ...]
    contract: str = "DependencyGraphV1"

    def __post_init__(self) -> None:
        if self.contract != "DependencyGraphV1":
            raise DependencyContractError("unsupported dependency graph contract")
        edge_ids = [edge.edge_id for edge in self.edges]
        if len(edge_ids) != len(set(edge_ids)):
            raise DependencyContractError("dependency edge IDs must be unique")

    def dependents_of(self, node: DependencyNodeV1) -> tuple[DependencyEdgeV1, ...]:
        return tuple(edge for edge in self.edges if edge.upstream == node)

    def dependencies_of(self, node: DependencyNodeV1) -> tuple[DependencyEdgeV1, ...]:
        return tuple(edge for edge in self.edges if edge.downstream == node)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(frozen=True, slots=True)
class DerivedStateRecordV1:
    """Append-only state evidence caused by one trusted change set."""

    state_event_id: UUID
    node: DependencyNodeV1
    state: DerivedStateV1
    reason: str
    cause_change_set_id: UUID
    recorded_at: datetime
    contract: str = "DerivedStateRecordV1"

    def __post_init__(self) -> None:
        if self.contract != "DerivedStateRecordV1":
            raise DependencyContractError("unsupported derived state contract")
        if self.node.kind in ("SOURCE_RESOURCE", "CANONICAL_OBSERVATION"):
            raise DependencyContractError("source objects cannot have derived state events")
        if self.state not in _DERIVED_STATES:
            raise DependencyContractError("derived state is unsupported")
        if not self.reason:
            raise DependencyContractError("derived state reason is required")
        _aware(self.recorded_at, "derived state timestamp")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "state_event_id": str(self.state_event_id),
            "object_kind": self.node.kind,
            "object_id": str(self.node.object_id),
            "state": self.state,
            "reason": self.reason,
            "cause_change_set_id": str(self.cause_change_set_id),
            "recorded_at": self.recorded_at.isoformat(),
        }


def _aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DependencyContractError(f"{label} must include a timezone")
