"""Resource-scoped authority evidence, independent from football identity admission."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor, sql

from football.contracts.decisions import DecisionRecordV1, decision_schema
from football.contracts.source import canonical_json_bytes
from football.providers.resource_capabilities import ResourceScope
from football.storage.raw import ImmutableFileStore, ImmutableWrite


class AuthorityError(ValueError):
    """A resource authority assignment lacks consistent scope, time or evidence."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ResourceAuthority:
    authority_id: UUID
    scope: ResourceScope
    effective_from: datetime
    effective_to: datetime | None
    authority_tier: str
    qualification_state: str

    def __post_init__(self) -> None:
        if not isinstance(self.authority_id, UUID):
            raise AuthorityError("authority_id must be an assignment UUID")
        if not isinstance(self.effective_from, datetime):
            raise AuthorityError("authority requires an explicit effective start")
        for name in ("effective_from", "effective_to"):
            value = getattr(self, name)
            if value is not None:
                _aware(value)
                object.__setattr__(self, name, value.astimezone(UTC))
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise AuthorityError("authority effective interval must be nonempty")
        if not self.authority_tier.strip() or not self.qualification_state.strip():
            raise AuthorityError("explicit authority tier and qualification state are required")

    def to_dict(self) -> dict[str, object]:
        return {
            "authority_id": str(self.authority_id),
            "scope": self.scope.to_dict(),
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat() if self.effective_to else None,
            "authority_tier": self.authority_tier,
            "qualification_state": self.qualification_state,
        }


@dataclass(frozen=True, slots=True)
class AuthorityPublication:
    authority: ResourceAuthority
    evidence_refs: tuple[str, ...]
    decision: DecisionRecordV1
    artifact: ImmutableWrite


@dataclass(frozen=True, slots=True)
class RegisteredAuthority:
    decision_id: UUID
    known_at: datetime
    authority: ResourceAuthority


def _decision(
    authority: ResourceAuthority,
    *,
    decided_at: datetime,
    reason: str,
    evidence_refs: tuple[str, ...],
    predecessor: UUID | None,
) -> DecisionRecordV1:
    if not evidence_refs or any(not ref.strip() for ref in evidence_refs):
        raise AuthorityError("authority qualification evidence references are required")
    if len(evidence_refs) != len(set(evidence_refs)):
        raise AuthorityError("authority evidence references must be unique")
    return DecisionRecordV1(
        decision_type="provider_authority",
        subject_type="provider_resource_authority",
        subject_id=str(authority.authority_id),
        decided_at=decided_at,
        effective_at=authority.effective_from,
        disposition=authority.qualification_state,
        reason=reason,
        predecessor=str(predecessor) if predecessor else None,
        evidence={"authority": authority.to_dict(), "evidence_refs": list(evidence_refs)},
    )


def prepare_authority(
    root: Path,
    authority: ResourceAuthority,
    *,
    decided_at: datetime,
    reason: str,
    evidence_refs: tuple[str, ...],
    predecessor: UUID | None = None,
) -> AuthorityPublication:
    refs = tuple(evidence_refs)
    decision = _decision(
        authority, decided_at=decided_at, reason=reason, evidence_refs=refs, predecessor=predecessor
    )
    artifact = ImmutableFileStore(root).publish(_path(decision.sha256), decision.to_bytes())
    return AuthorityPublication(authority, refs, decision, artifact)


class AuthorityRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(self, publication: AuthorityPublication) -> UUID:
        _verify(publication)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            _check_predecessor(cursor, publication)
            _register(cursor, publication)
        return publication.decision.decision_id

    def at(
        self, scope: ResourceScope, *, effective_at: datetime, knowledge_cutoff: datetime
    ) -> tuple[RegisteredAuthority, ...]:
        """Return all applicable claims; never infer qualification or a universal tier order."""
        _aware(effective_at)
        _aware(knowledge_cutoff)
        rows = self._connection.execute(
            """
            WITH states AS (
                SELECT DISTINCT ON (a.authority_id)
                    a.authority_id,a.effective_from,a.effective_to,a.authority_tier,
                    a.qualification_state,a.decision_id,a.known_at
                FROM football.provider_resource_authority a
                JOIN football.providers p ON p.id=a.provider_id
                WHERE p.code=%s AND a.resource_type=%s
                  AND a.competition_key IS NOT DISTINCT FROM %s
                  AND a.season_key IS NOT DISTINCT FROM %s AND a.known_at<=%s
                ORDER BY a.authority_id,a.known_at DESC,a.publication_sequence DESC
            )
            SELECT * FROM states WHERE effective_from<=%s
                AND (effective_to IS NULL OR %s<effective_to) ORDER BY authority_id
            """,
            (
                scope.provider,
                scope.resource_type,
                scope.competition,
                scope.season,
                knowledge_cutoff,
                effective_at,
                effective_at,
            ),
        ).fetchall()
        return tuple(
            RegisteredAuthority(
                row[5],
                row[6],
                ResourceAuthority(
                    authority_id=row[0],
                    scope=scope,
                    effective_from=row[1],
                    effective_to=row[2],
                    authority_tier=row[3],
                    qualification_state=row[4],
                ),
            )
            for row in rows
        )


def _aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise AuthorityError("authority time requires a timezone")


def _path(digest: str) -> str:
    return f"provider-authority/v1/{digest}.json"


def _verify(publication: AuthorityPublication) -> None:
    decision, artifact = publication.decision, publication.artifact
    expected = _decision(
        publication.authority,
        decided_at=decision.decided_at,
        reason=decision.reason,
        evidence_refs=publication.evidence_refs,
        predecessor=UUID(decision.predecessor) if decision.predecessor else None,
    )
    if expected != decision or (artifact.relative_path, artifact.sha256, artifact.size_bytes) != (
        _path(decision.sha256),
        decision.sha256,
        len(decision.to_bytes()),
    ):
        raise AuthorityError("authority publication differs from its evidence")
    try:
        if artifact.path.is_symlink() or artifact.path.read_bytes() != decision.to_bytes():
            raise AuthorityError("authority artifact bytes differ")
    except OSError as error:
        raise AuthorityError("authority artifact bytes are unavailable") from error


def _check_predecessor(cursor: Cursor[Any], publication: AuthorityPublication) -> None:
    decision = publication.decision
    if cursor.execute(
        "SELECT 1 FROM football.provider_resource_authority WHERE decision_id=%s",
        (decision.decision_id,),
    ).fetchone():
        return
    row = cursor.execute(
        "SELECT decision_id FROM football.provider_resource_authority "
        "WHERE authority_id=%s ORDER BY publication_sequence DESC LIMIT 1",
        (publication.authority.authority_id,),
    ).fetchone()
    if decision.predecessor != (str(row[0]) if row else None):
        raise AuthorityError("authority revision must reference the current predecessor")


def _register(cursor: Cursor[Any], publication: AuthorityPublication) -> None:
    authority, decision, artifact = (
        publication.authority,
        publication.decision,
        publication.artifact,
    )
    scope = authority.scope
    provider = cursor.execute(
        "SELECT id FROM football.providers WHERE code=%s", (scope.provider,)
    ).fetchone()
    if provider is None:
        raise AuthorityError("authority provider is not registered")
    columns = (
        "decision_id",
        "authority_id",
        "scope_sha256",
        "provider_id",
        "resource_type",
        "competition_key",
        "season_key",
        "effective_from",
        "effective_to",
        "authority_tier",
        "qualification_state",
        "predecessor_decision_id",
        "decided_at",
        "decision_contract_version",
        "schema_sha256",
        "artifact_path",
        "artifact_sha256",
    )
    values = (
        decision.decision_id,
        authority.authority_id,
        scope.sha256,
        provider[0],
        scope.resource_type,
        scope.competition,
        scope.season,
        authority.effective_from,
        authority.effective_to,
        authority.authority_tier,
        authority.qualification_state,
        UUID(decision.predecessor) if decision.predecessor else None,
        decision.decided_at,
        decision.contract_version,
        hashlib.sha256(canonical_json_bytes(decision_schema())).hexdigest(),
        artifact.relative_path,
        artifact.sha256,
    )
    column_sql = sql.SQL(",").join(map(sql.Identifier, columns))
    cursor.execute(
        sql.SQL(
            "INSERT INTO football.provider_resource_authority({}) VALUES ({}) "
            "ON CONFLICT (decision_id) DO NOTHING"
        ).format(column_sql, sql.SQL(",").join(sql.Placeholder() for _ in values)),
        values,
    )
    row = cursor.execute(
        sql.SQL("SELECT {} FROM football.provider_resource_authority WHERE decision_id=%s").format(
            column_sql
        ),
        (decision.decision_id,),
    ).fetchone()
    if row != values:
        raise AuthorityError("registered authority conflicts with its immutable decision")
