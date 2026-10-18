"""Persist scoped capability decisions; keep provider I/O outside transactions."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor, sql
from psycopg.pq import TransactionStatus

from football.contracts.decisions import DecisionRecordV1, decision_schema
from football.contracts.source import canonical_json_bytes
from football.providers.resource_capabilities import (
    AcquisitionPlan,
    CapabilityError,
    ResourceCapability,
    ResourceScope,
    acquisition_plan,
)
from football.providers.sources.contracts import ProviderPayload
from football.storage.raw import ImmutableFileStore, ImmutableWrite

_CAPABILITY_COLUMNS = tuple(item.name for item in fields(ResourceCapability))
_SCOPE_WHERE = """p.code=%s AND r.resource_type=%s
    AND r.competition_key IS NOT DISTINCT FROM %s AND r.season_key IS NOT DISTINCT FROM %s"""


@dataclass(frozen=True, slots=True)
class CapabilityPublication:
    scope: ResourceScope
    capability: ResourceCapability
    evidence_refs: tuple[str, ...]
    decision: DecisionRecordV1
    artifact: ImmutableWrite


@dataclass(frozen=True, slots=True)
class RegisteredCapability:
    decision_id: UUID
    known_at: datetime
    capability: ResourceCapability


def _decision(
    scope: ResourceScope,
    capability: ResourceCapability,
    *,
    decided_at: datetime,
    reason: str,
    evidence_refs: tuple[str, ...],
    predecessor: UUID | None,
) -> DecisionRecordV1:
    if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
        raise CapabilityError("capability source evidence references are required")
    if len(evidence_refs) != len(set(evidence_refs)):
        raise CapabilityError("capability evidence references must be unique")
    return DecisionRecordV1(
        decision_type="provider_capability",
        subject_type="provider_resource_scope",
        subject_id=str(scope.subject_id),
        decided_at=decided_at,
        disposition=capability.availability,
        reason=reason,
        predecessor=str(predecessor) if predecessor else None,
        evidence={
            "scope": scope.to_dict(),
            "capability": capability.to_dict(),
            "evidence_refs": list(evidence_refs),
        },
    )


def prepare_capability(
    root: Path,
    scope: ResourceScope,
    capability: ResourceCapability,
    *,
    decided_at: datetime,
    reason: str,
    evidence_refs: tuple[str, ...],
    predecessor: UUID | None = None,
) -> CapabilityPublication:
    refs = tuple(evidence_refs)
    decision = _decision(
        scope,
        capability,
        decided_at=decided_at,
        reason=reason,
        evidence_refs=refs,
        predecessor=predecessor,
    )
    artifact = ImmutableFileStore(root).publish(_path(decision.sha256), decision.to_bytes())
    return CapabilityPublication(scope, capability, refs, decision, artifact)


class CapabilityRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(self, publication: CapabilityPublication) -> UUID:
        _verify_publication(publication)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            _check_predecessor(cursor, publication)
            _register(cursor, publication)
        return publication.decision.decision_id

    def at(self, scope: ResourceScope, knowledge_cutoff: datetime) -> RegisteredCapability | None:
        if knowledge_cutoff.utcoffset() is None:
            raise CapabilityError("knowledge_cutoff requires a timezone")
        return self._read(scope, knowledge_cutoff)

    def _read(self, scope: ResourceScope, cutoff: datetime | None) -> RegisteredCapability | None:
        condition = " AND r.known_at<=%s" if cutoff is not None else ""
        order = (
            "r.known_at DESC,r.publication_sequence DESC"
            if cutoff is not None
            else ("r.publication_sequence DESC")
        )
        parameters = (*_scope_values(scope), cutoff) if cutoff is not None else _scope_values(scope)
        columns = sql.SQL(",").join(sql.Identifier("r", name) for name in _CAPABILITY_COLUMNS)
        row = self._connection.execute(
            sql.SQL(
                "SELECT r.decision_id,r.known_at,{} FROM football.provider_resource_capabilities r "
                "JOIN football.providers p ON p.id=r.provider_id WHERE "
                + _SCOPE_WHERE
                + condition
                + " ORDER BY "
                + order
                + " LIMIT 1"
            ).format(columns),
            parameters,
        ).fetchone()
        if row is None:
            return None
        values: dict[str, Any] = dict(zip(_CAPABILITY_COLUMNS, row[2:], strict=True))
        return RegisteredCapability(row[0], row[1], ResourceCapability(**values))

    def plan(
        self,
        scope: ResourceScope,
        *,
        adapter_version: str,
        normalizer_version: str,
        football_date: date | None = None,
    ) -> AcquisitionPlan:
        """Use the latest committed transition; clock rollback cannot revive an old permission."""
        with self._connection.transaction():
            snapshot = self._read(scope, None)
        plan = acquisition_plan(
            scope,
            snapshot.capability if snapshot else None,
            adapter_version=adapter_version,
            normalizer_version=normalizer_version,
            football_date=football_date,
        )
        return replace(plan, decision_id=snapshot.decision_id if snapshot else None)

    def acquire(
        self,
        scope: ResourceScope,
        fetch: Callable[[], ProviderPayload],
        *,
        adapter_version: str,
        normalizer_version: str,
        football_date: date | None = None,
    ) -> ProviderPayload:
        """Gate each acquisition; original clients retain their own quotas and retry controls."""
        if self._connection.info.transaction_status != TransactionStatus.IDLE:
            raise CapabilityError("provider acquisition requires an idle database connection")
        plan = self.plan(
            scope,
            adapter_version=adapter_version,
            normalizer_version=normalizer_version,
            football_date=football_date,
        )
        if not plan.allowed:
            raise CapabilityError(f"{plan.availability}: {plan.reason}")
        payload = fetch()
        if payload.provider != scope.provider:
            raise CapabilityError("acquired payload belongs to another provider")
        return payload


def _path(digest: str) -> str:
    return f"provider-capabilities/v1/{digest}.json"


def _scope_values(scope: ResourceScope) -> tuple[object, ...]:
    return (scope.provider, scope.resource_type, scope.competition, scope.season)


def _verify_publication(publication: CapabilityPublication) -> None:
    decision = publication.decision
    expected = _decision(
        publication.scope,
        publication.capability,
        decided_at=decision.decided_at,
        reason=decision.reason,
        evidence_refs=publication.evidence_refs,
        predecessor=UUID(decision.predecessor) if decision.predecessor else None,
    )
    artifact = publication.artifact
    if decision != expected or (artifact.relative_path, artifact.sha256, artifact.size_bytes) != (
        _path(decision.sha256),
        decision.sha256,
        len(decision.to_bytes()),
    ):
        raise CapabilityError("capability publication differs from its evidence")
    try:
        if artifact.path.is_symlink() or artifact.path.read_bytes() != decision.to_bytes():
            raise CapabilityError("prepared capability artifact bytes differ")
    except OSError as error:
        raise CapabilityError("prepared capability artifact bytes are unavailable") from error


def _check_predecessor(cursor: Cursor[Any], publication: CapabilityPublication) -> None:
    decision = publication.decision
    if cursor.execute(
        "SELECT 1 FROM football.provider_resource_capabilities WHERE decision_id=%s",
        (decision.decision_id,),
    ).fetchone():
        return
    row = cursor.execute(
        "SELECT r.decision_id FROM football.provider_resource_capabilities r "
        "JOIN football.providers p ON p.id=r.provider_id WHERE "
        + _SCOPE_WHERE
        + " ORDER BY r.publication_sequence DESC LIMIT 1",
        _scope_values(publication.scope),
    ).fetchone()
    if decision.predecessor != (str(row[0]) if row else None):
        raise CapabilityError("capability revision must reference the current predecessor")


def _register(cursor: Cursor[Any], publication: CapabilityPublication) -> None:
    scope, capability, decision = publication.scope, publication.capability, publication.decision
    provider = cursor.execute(
        "SELECT id FROM football.providers WHERE code=%s", (scope.provider,)
    ).fetchone()
    if provider is None:
        raise CapabilityError("capability provider is not registered")
    columns = (
        "decision_id",
        "scope_sha256",
        "provider_id",
        "resource_type",
        "competition_key",
        "season_key",
        *_CAPABILITY_COLUMNS,
        "predecessor_decision_id",
        "decided_at",
        "decision_contract_version",
        "schema_sha256",
        "artifact_path",
        "artifact_sha256",
    )
    values = (
        decision.decision_id,
        scope.sha256,
        provider[0],
        scope.resource_type,
        scope.competition,
        scope.season,
        *(getattr(capability, name) for name in _CAPABILITY_COLUMNS),
        UUID(decision.predecessor) if decision.predecessor else None,
        decision.decided_at,
        decision.contract_version,
        hashlib.sha256(canonical_json_bytes(decision_schema())).hexdigest(),
        publication.artifact.relative_path,
        publication.artifact.sha256,
    )
    column_sql = sql.SQL(",").join(map(sql.Identifier, columns))
    cursor.execute(
        sql.SQL(
            "INSERT INTO football.provider_resource_capabilities({}) VALUES ({}) "
            "ON CONFLICT (decision_id) DO NOTHING"
        ).format(column_sql, sql.SQL(",").join(sql.Placeholder() for _ in values)),
        values,
    )
    row = cursor.execute(
        sql.SQL(
            "SELECT {} FROM football.provider_resource_capabilities WHERE decision_id=%s"
        ).format(column_sql),
        (decision.decision_id,),
    ).fetchone()
    if row != values:
        raise CapabilityError("registered capability conflicts with its immutable decision")
