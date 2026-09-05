from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Cursor

from football.contracts.dependencies import (
    DependencyEdgeV1,
    DependencyNodeV1,
    DependencyRelationshipV1,
    DerivedStateRecordV1,
    DerivedStateV1,
    EffectiveDerivedStateV1,
)

DependencyRegistrationStatusV1 = Literal["inserted", "verified_existing"]
CorrectionPropagationStatusV1 = Literal["propagated", "not_real_provider"]


class DependencyStorageError(ValueError):
    """Stored lineage does not satisfy the approved correction contract."""


@dataclass(frozen=True, slots=True)
class RegisteredDependencyEdgeV1:
    edge: DependencyEdgeV1
    status: DependencyRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class RegisteredDerivedStateEventV1:
    event: DerivedStateRecordV1
    status: DependencyRegistrationStatusV1


@dataclass(frozen=True, slots=True)
class CorrectionPropagationResultV1:
    change_set_id: UUID
    status: CorrectionPropagationStatusV1
    seed_nodes: tuple[DependencyNodeV1, ...]
    affected_nodes: tuple[DependencyNodeV1, ...]
    state_events: tuple[RegisteredDerivedStateEventV1, ...]


class PostgresDependencyStoreV1:
    """Append-only dependency and state storage for trusted correction impact."""

    def register_dependency(
        self,
        cursor: Cursor[Any],
        *,
        upstream: DependencyNodeV1,
        relationship: DependencyRelationshipV1,
        downstream: DependencyNodeV1,
        contract_version: str = "dependency-edge-v1",
    ) -> RegisteredDependencyEdgeV1:
        _reject_fixture_model_lineage(cursor, upstream, downstream)
        values = (
            upstream.kind,
            upstream.object_id,
            relationship,
            downstream.kind,
            downstream.object_id,
            contract_version,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.dependency_edges
                (upstream_kind, upstream_id, relationship, downstream_kind, downstream_id,
                 contract_version)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (upstream_kind, upstream_id, relationship, downstream_kind,
                         downstream_id, contract_version) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, upstream_kind, upstream_id, relationship, downstream_kind, downstream_id,
                   contract_version, created_at
            FROM football.dependency_edges
            WHERE upstream_kind = %s AND upstream_id = %s AND relationship = %s
              AND downstream_kind = %s AND downstream_id = %s AND contract_version = %s
            """,
            values,
        ).fetchone()
        if row is None:
            raise DependencyStorageError("dependency edge was not registered")
        edge = _edge_from_row(row)
        if (
            edge.upstream != upstream
            or edge.relationship != relationship
            or edge.downstream != downstream
            or edge.contract_version != contract_version
        ):
            raise DependencyStorageError("dependency edge conflicts with immutable lineage")
        return RegisteredDependencyEdgeV1(
            edge=edge,
            status="inserted" if inserted == 1 else "verified_existing",
        )

    def dependents(
        self, cursor: Cursor[Any], node: DependencyNodeV1
    ) -> tuple[DependencyEdgeV1, ...]:
        rows = cursor.execute(
            """
            SELECT id, upstream_kind, upstream_id, relationship, downstream_kind, downstream_id,
                   contract_version, created_at
            FROM football.dependency_edges
            WHERE upstream_kind = %s AND upstream_id = %s
            ORDER BY downstream_kind, downstream_id, relationship, contract_version
            """,
            (node.kind, node.object_id),
        )
        return tuple(_edge_from_row(row) for row in rows)

    def dependencies(
        self, cursor: Cursor[Any], node: DependencyNodeV1
    ) -> tuple[DependencyEdgeV1, ...]:
        rows = cursor.execute(
            """
            SELECT id, upstream_kind, upstream_id, relationship, downstream_kind, downstream_id,
                   contract_version, created_at
            FROM football.dependency_edges
            WHERE downstream_kind = %s AND downstream_id = %s
            ORDER BY upstream_kind, upstream_id, relationship, contract_version
            """,
            (node.kind, node.object_id),
        )
        return tuple(_edge_from_row(row) for row in rows)

    def record_derived_state(
        self,
        cursor: Cursor[Any],
        *,
        node: DependencyNodeV1,
        state: DerivedStateV1,
        reason: str,
        cause_change_set_id: UUID,
        recorded_at: datetime,
    ) -> RegisteredDerivedStateEventV1:
        values = (
            node.kind,
            node.object_id,
            state,
            reason,
            cause_change_set_id,
            recorded_at,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.derived_state_events
                (object_kind, object_id, state, reason, cause_change_set_id, recorded_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (object_kind, object_id, state, cause_change_set_id) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, object_kind, object_id, state, reason, cause_change_set_id, recorded_at
            FROM football.derived_state_events
            WHERE object_kind = %s AND object_id = %s AND state = %s
              AND cause_change_set_id = %s
            """,
            (node.kind, node.object_id, state, cause_change_set_id),
        ).fetchone()
        if row is None:
            raise DependencyStorageError("derived state event was not registered")
        event = _state_event_from_row(row)
        if event.reason != reason:
            raise DependencyStorageError("derived state event conflicts with immutable history")
        return RegisteredDerivedStateEventV1(
            event=event,
            status="inserted" if inserted == 1 else "verified_existing",
        )

    def effective_state(
        self, cursor: Cursor[Any], node: DependencyNodeV1
    ) -> EffectiveDerivedStateV1:
        row = cursor.execute(
            """
            SELECT state
            FROM football.derived_state_events
            WHERE object_kind = %s AND object_id = %s
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (node.kind, node.object_id),
        ).fetchone()
        if row is None:
            return "VALID"
        return cast(EffectiveDerivedStateV1, str(row[0]))


class SourceCorrectionPropagatorV1:
    """Append only the state events caused by a trusted real-provider change set."""

    def __init__(self, store: PostgresDependencyStoreV1 | None = None) -> None:
        self._store = store or PostgresDependencyStoreV1()

    def propagate(self, cursor: Cursor[Any], change_set_id: UUID) -> CorrectionPropagationResultV1:
        row = cursor.execute(
            """
            SELECT sync_run_id, status, publication_scope, changes, published_at
            FROM football.canonical_change_sets
            WHERE id = %s
            """,
            (change_set_id,),
        ).fetchone()
        if row is None:
            raise DependencyStorageError("canonical change set is not registered")
        sync_run_id, status, publication_scope, changes, published_at = row
        if status not in ("published", "verified_existing"):
            raise DependencyStorageError("canonical change set is not trusted")
        if publication_scope != "REAL_PROVIDER":
            return CorrectionPropagationResultV1(
                change_set_id=change_set_id,
                status="not_real_provider",
                seed_nodes=(),
                affected_nodes=(),
                state_events=(),
            )
        if not isinstance(changes, dict) or not isinstance(published_at, datetime):
            raise DependencyStorageError("canonical change set payload is invalid")
        seeds = _change_set_nodes(cursor, UUID(str(sync_run_id)), changes)
        affected = _descendants(cursor, self._store, seeds)
        events = tuple(
            self._store.record_derived_state(
                cursor,
                node=node,
                state=state,
                reason="trusted source correction affects registered dependency",
                cause_change_set_id=change_set_id,
                recorded_at=published_at,
            )
            for node in affected
            if (state := _correction_state(node)) is not None
        )
        return CorrectionPropagationResultV1(
            change_set_id=change_set_id,
            status="propagated",
            seed_nodes=seeds,
            affected_nodes=affected,
            state_events=events,
        )


def _change_set_nodes(
    cursor: Cursor[Any], sync_run_id: UUID, changes: dict[str, Any]
) -> tuple[DependencyNodeV1, ...]:
    source_resources = changes.get("source_resources")
    if not isinstance(source_resources, list) or not source_resources:
        raise DependencyStorageError("canonical change set has no source resources")
    nodes = [
        DependencyNodeV1("SOURCE_RESOURCE", _source_resource_id(cursor, sync_run_id, resource))
        for resource in source_resources
    ]
    observation_refs = tuple(changes.get("added_observation_refs", ())) + tuple(
        changes.get("superseding_observation_refs", ())
    )
    nodes.extend(_observation_node(reference) for reference in observation_refs)
    return _unique_nodes(nodes)


def _source_resource_id(cursor: Cursor[Any], sync_run_id: UUID, resource: object) -> UUID:
    if not isinstance(resource, dict):
        raise DependencyStorageError("canonical change set source resource is invalid")
    resource_ref = resource.get("resource_ref")
    checksum = resource.get("sha256")
    if not isinstance(resource_ref, str) or not isinstance(checksum, str):
        raise DependencyStorageError("canonical change set source resource is invalid")
    row = cursor.execute(
        """
        SELECT acquired.source_resource_id
        FROM football.acquired_resources AS acquired
        JOIN football.acquisition_jobs AS job ON job.id = acquired.acquisition_job_id
        JOIN football.providers AS provider ON provider.id = job.provider_id
        JOIN football.source_resources AS resource ON resource.id = acquired.source_resource_id
        WHERE job.sync_run_id = %s
          AND provider.code || '/' || resource.provider_path = %s
          AND resource.sha256 = %s
        """,
        (sync_run_id, resource_ref, checksum),
    ).fetchone()
    if row is None:
        raise DependencyStorageError("change set source resource cannot be resolved")
    return UUID(str(row[0]))


def _observation_node(reference: object) -> DependencyNodeV1:
    if not isinstance(reference, str) or not reference.startswith("match_observation:"):
        raise DependencyStorageError("canonical change set observation reference is unsupported")
    try:
        observation_id = UUID(reference.removeprefix("match_observation:"))
        return DependencyNodeV1("CANONICAL_OBSERVATION", observation_id)
    except ValueError as error:
        raise DependencyStorageError(
            "canonical change set observation reference is invalid"
        ) from error


def _descendants(
    cursor: Cursor[Any],
    store: PostgresDependencyStoreV1,
    seeds: tuple[DependencyNodeV1, ...],
) -> tuple[DependencyNodeV1, ...]:
    queue = deque(seeds)
    seen = set(seeds)
    descendants: list[DependencyNodeV1] = []
    while queue:
        node = queue.popleft()
        for edge in store.dependents(cursor, node):
            downstream = edge.downstream
            if downstream in seen:
                continue
            seen.add(downstream)
            descendants.append(downstream)
            queue.append(downstream)
    return tuple(descendants)


def _correction_state(node: DependencyNodeV1) -> DerivedStateV1 | None:
    if node.kind == "DATASET":
        return "REBUILD_REQUIRED"
    if node.kind in ("MODEL_ARTIFACT", "FORECAST", "EVALUATION"):
        return "AFFECTED_BY_SOURCE_CORRECTION"
    return None


def _unique_nodes(nodes: Iterable[DependencyNodeV1]) -> tuple[DependencyNodeV1, ...]:
    return tuple(dict.fromkeys(nodes))


def _edge_from_row(row: tuple[object, ...]) -> DependencyEdgeV1:
    return DependencyEdgeV1(
        edge_id=UUID(str(row[0])),
        upstream=DependencyNodeV1(cast(Any, str(row[1])), UUID(str(row[2]))),
        relationship=cast(Any, str(row[3])),
        downstream=DependencyNodeV1(cast(Any, str(row[4])), UUID(str(row[5]))),
        contract_version=str(row[6]),
        created_at=cast(datetime, row[7]),
    )


def _state_event_from_row(row: tuple[object, ...]) -> DerivedStateRecordV1:
    return DerivedStateRecordV1(
        state_event_id=UUID(str(row[0])),
        node=DependencyNodeV1(cast(Any, str(row[1])), UUID(str(row[2]))),
        state=cast(Any, str(row[3])),
        reason=str(row[4]),
        cause_change_set_id=UUID(str(row[5])),
        recorded_at=cast(datetime, row[6]),
    )


def _reject_fixture_model_lineage(
    cursor: Cursor[Any], upstream: DependencyNodeV1, downstream: DependencyNodeV1
) -> None:
    if downstream.kind not in ("DATASET", "MODEL_ARTIFACT", "FORECAST", "EVALUATION"):
        return
    if _is_fixture_source(cursor, upstream):
        raise DependencyStorageError("contract fixture evidence cannot feed model-eligible lineage")


def _is_fixture_source(cursor: Cursor[Any], node: DependencyNodeV1) -> bool:
    if node.kind == "SOURCE_RESOURCE":
        row = cursor.execute(
            """
            SELECT snapshot.source_kind
            FROM football.source_resources AS resource
            JOIN football.source_snapshots AS snapshot ON snapshot.id = resource.source_snapshot_id
            WHERE resource.id = %s
            """,
            (node.object_id,),
        ).fetchone()
        return row == ("CONTRACT_FIXTURE",)
    if node.kind == "CANONICAL_OBSERVATION":
        row = cursor.execute(
            """
            SELECT snapshot.source_kind
            FROM football.match_observations AS observation
            JOIN football.source_snapshots AS snapshot
              ON snapshot.id = observation.source_snapshot_id
            WHERE observation.id = %s
            """,
            (node.object_id,),
        ).fetchone()
        return row == ("CONTRACT_FIXTURE",)
    return False
