from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Cursor
from psycopg.types.json import Jsonb

from football.ingestion.resolution import ResolutionDecisionV1

ResolutionDecisionRegistrationStatusV1 = Literal["inserted", "verified_existing"]


class ResolutionDecisionStorageError(ValueError):
    """A persisted resolution decision conflicts with its immutable contract."""


@dataclass(frozen=True, slots=True)
class RegisteredResolutionDecisionV1:
    decision_id: UUID
    decision_key: str
    status: ResolutionDecisionRegistrationStatusV1


class PostgresResolutionDecisionStoreV1:
    """Persist semantic resolution decisions idempotently and without mutation."""

    def register(
        self,
        cursor: Cursor[Any],
        *,
        provider_id: UUID,
        decision: ResolutionDecisionV1,
    ) -> RegisteredResolutionDecisionV1:
        selected_canonical_id = _uuid_or_none(
            decision.selected_canonical_id, "selected canonical ID"
        )
        supersedes_decision_id = _uuid_or_none(
            decision.supersedes_decision_id, "superseded decision ID"
        )
        candidate_canonical_ids = _canonical_ids(decision)
        values = (
            decision.sha256,
            decision.subject_type,
            provider_id,
            decision.provider_entity_id,
            Jsonb(list(decision.evidence_refs)),
            Jsonb(candidate_canonical_ids),
            decision.rule_version,
            decision.confidence,
            decision.status,
            selected_canonical_id,
            decision.actor,
            decision.reason,
            decision.created_at,
            supersedes_decision_id,
        )
        inserted = cursor.execute(
            """
            INSERT INTO football.resolution_decisions
                (decision_key, subject_type, provider_id, provider_entity_id, evidence_refs,
                 candidate_canonical_ids, rule_version, confidence, status,
                 selected_canonical_id, actor, reason, created_at, supersedes_decision_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (decision_key) DO NOTHING
            """,
            values,
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, subject_type, provider_id, provider_entity_id, evidence_refs,
                   candidate_canonical_ids, rule_version, confidence, status,
                   selected_canonical_id, actor, reason, created_at, supersedes_decision_id
            FROM football.resolution_decisions
            WHERE decision_key = %s
            """,
            (decision.sha256,),
        ).fetchone()
        expected = (
            values[1:4]
            + (
                list(decision.evidence_refs),
                candidate_canonical_ids,
            )
            + values[6:]
        )
        if row is None or row[1:] != expected:
            raise ResolutionDecisionStorageError(
                "resolution decision key conflicts with immutable decision evidence"
            )
        status: ResolutionDecisionRegistrationStatusV1 = (
            "inserted" if inserted == 1 else "verified_existing"
        )
        return RegisteredResolutionDecisionV1(
            decision_id=UUID(str(row[0])), decision_key=decision.sha256, status=status
        )


def _canonical_ids(decision: ResolutionDecisionV1) -> list[str]:
    return [
        str(_uuid_or_none(candidate, "candidate canonical ID"))
        for candidate in decision.candidate_canonical_ids
    ]


def _uuid_or_none(value: str | None, label: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise ResolutionDecisionStorageError(f"{label} must be a UUID") from error
