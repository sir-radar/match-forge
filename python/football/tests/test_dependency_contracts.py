from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from football.contracts import (
    DependencyContractError,
    DependencyEdgeV1,
    DependencyGraphV1,
    DependencyNodeV1,
    DerivedStateRecordV1,
)


def test_dependency_graph_exposes_immutable_lineage_queries() -> None:
    source = _node("SOURCE_RESOURCE", 1)
    observation = _node("CANONICAL_OBSERVATION", 2)
    dataset = _node("DATASET", 3)
    first = _edge(source, observation, "DERIVED_FROM", 11)
    second = _edge(observation, dataset, "INPUT_TO", 12)
    graph = DependencyGraphV1((first, second))

    assert graph.dependents_of(observation) == (second,)
    assert graph.dependencies_of(dataset) == (second,)
    assert len(first.sha256) == 64
    assert graph.to_dict()["contract"] == "DependencyGraphV1"


def test_dependency_edge_rejects_self_edges_and_unknown_relationships() -> None:
    with pytest.raises(DependencyContractError, match="point to itself"):
        _edge(_node("DATASET", 1), _node("DATASET", 1), "INPUT_TO", 2)
    with pytest.raises(DependencyContractError, match="relationship"):
        _edge(_node("DATASET", 1), _node("MODEL_ARTIFACT", 2), "UNKNOWN", 3)


def test_dependency_graph_rejects_duplicate_edge_ids() -> None:
    edge = _edge(_node("SOURCE_RESOURCE", 1), _node("DATASET", 2), "INPUT_TO", 1)
    with pytest.raises(DependencyContractError, match="IDs must be unique"):
        DependencyGraphV1((edge, edge))


def test_derived_state_is_append_only_specific_correction_evidence() -> None:
    record = DerivedStateRecordV1(
        state_event_id=_uuid(1),
        node=_node("DATASET", 2),
        state="REBUILD_REQUIRED",
        reason="trusted source correction affects a dataset input",
        cause_change_set_id=_uuid(3),
        recorded_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
    )

    assert record.to_dict()["state"] == "REBUILD_REQUIRED"
    assert len(record.sha256) == 64
    with pytest.raises(DependencyContractError, match="source objects"):
        DerivedStateRecordV1(
            state_event_id=_uuid(4),
            node=_node("SOURCE_RESOURCE", 5),
            state="REBUILD_REQUIRED",
            reason="invalid",
            cause_change_set_id=_uuid(3),
            recorded_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
        )


def test_dependency_migration_is_additive_and_enforces_frozen_state_rules() -> None:
    migration = (
        Path(__file__).resolve().parents[3]
        / "infrastructure/migrations/202609020900_source_correction_dependencies.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE football.dependency_edges" in migration
    assert "CREATE TABLE football.derived_state_events" in migration
    assert "REBUILD_REQUIRED" in migration
    assert "AFFECTED_BY_SOURCE_CORRECTION" in migration
    assert "SUPERSEDED" in migration
    assert "dependency lineage is append-only" in migration
    assert "trusted real-provider change set" in migration
    assert "DROP TABLE" not in migration


def _node(kind: str, value: int) -> DependencyNodeV1:
    return DependencyNodeV1(kind=kind, object_id=_uuid(value))  # type: ignore[arg-type]


def _edge(
    upstream: DependencyNodeV1,
    downstream: DependencyNodeV1,
    relationship: str,
    edge_id: int,
) -> DependencyEdgeV1:
    return DependencyEdgeV1(
        edge_id=_uuid(edge_id),
        upstream=upstream,
        relationship=relationship,  # type: ignore[arg-type]
        downstream=downstream,
        created_at=datetime(2026, 9, 2, 12, tzinfo=UTC),
    )


def _uuid(value: int) -> UUID:
    return UUID(int=value)
