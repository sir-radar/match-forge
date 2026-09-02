from datetime import UTC, datetime

import pytest
from football.contracts import DependencyContractError, DependencyEdgeV1, DependencyGraphV1


def test_dependency_graph_exposes_immutable_lineage_queries() -> None:
    source = _edge("source-1", "canonical-1", "source_resource", "canonical_observation")
    derived = _edge("canonical-1", "dataset-1", "canonical_observation", "curated_dataset")
    graph = DependencyGraphV1((source, derived))

    assert graph.dependents_of("canonical-1") == (derived,)
    assert graph.dependencies_of("dataset-1") == (derived,)
    assert len(source.sha256) == 64
    assert graph.to_dict()["contract"] == "DependencyGraphV1"


def test_dependency_edge_rejects_self_edges_and_invalid_revisions() -> None:
    with pytest.raises(DependencyContractError, match="point to itself"):
        _edge("same", "same", "source", "dataset")
    with pytest.raises(DependencyContractError, match="revision"):
        _edge("edge-1", "source-1", "source", "dataset", revision=0)


def test_dependency_graph_rejects_duplicate_edge_ids() -> None:
    edge = _edge("edge-1", "source-1", "source", "dataset")
    with pytest.raises(DependencyContractError, match="IDs must be unique"):
        DependencyGraphV1((edge, edge))


def _edge(
    upstream_ref: str,
    downstream_ref: str,
    upstream_kind: str,
    downstream_kind: str,
    **overrides: object,
) -> DependencyEdgeV1:
    values: dict[str, object] = {
        "edge_id": f"{upstream_ref}->{downstream_ref}",
        "upstream_ref": upstream_ref,
        "upstream_kind": upstream_kind,
        "downstream_ref": downstream_ref,
        "downstream_kind": downstream_kind,
        "state": "VALID",
        "created_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
    }
    values.update(overrides)
    return DependencyEdgeV1(**values)  # type: ignore[arg-type]
