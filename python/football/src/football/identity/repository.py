"""Recorded provider mapping states; qualification remains with existing decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection
from psycopg.rows import class_row

from football.ingestion.resolution import ResolutionSubjectV1


@dataclass(frozen=True, slots=True)
class ProviderMapping:
    """An existing mapping claim with its exact recorded state and source."""

    history_id: int
    subject_type: ResolutionSubjectV1
    mapping_id: UUID
    canonical_id: UUID
    provider_id: UUID
    provider_entity_id: str
    provider_competition_id: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    first_seen_at: datetime
    mapping_created_at: datetime
    mapping_method: str
    mapping_confidence: float
    source_snapshot_id: UUID
    recorded_at: datetime
    known_at: datetime


class IdentityRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def admitted_identity_at(
        self,
        subject_type: Literal["team", "competition"],
        mapping_id: UUID,
        knowledge_cutoff: datetime,
    ) -> UUID | None:
        """Use R2 admission/correction history; a mapping or confidence is not approval."""
        if knowledge_cutoff.utcoffset() is None:
            raise ValueError("knowledge_cutoff must include a timezone")
        if subject_type == "team":
            row = self._connection.execute(
                "SELECT football.product_team_identity_at(%s,%s)",
                (mapping_id, knowledge_cutoff),
            ).fetchone()
            return row[0] if row else None
        if subject_type != "competition":
            raise ValueError("R2 admissions support team and competition mappings")
        row = self._connection.execute(
            """SELECT canonical_id,disposition,source_observed_at
               FROM football.product_identity_admissions
               WHERE entity_type='competition' AND mapping_id=%s AND decided_at<=%s
               ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
            (mapping_id, knowledge_cutoff),
        ).fetchone()
        if row is None or row[1] not in ("ORIGIN_ANCHOR", "CROSSWALK"):
            return None
        return row[0] if row[2] is not None and row[2] <= knowledge_cutoff else None

    def mapping_at(
        self,
        subject_type: ResolutionSubjectV1,
        provider_id: UUID,
        provider_entity_id: str,
        *,
        valid_at: datetime,
        knowledge_cutoff: datetime,
        provider_competition_id: str | None = None,
    ) -> tuple[ProviderMapping, ...]:
        """Read existing identity claims, never infer a merge or an admission.

        Initial capture does not prove earlier mapping states. Season IDs require
        their native competition scope. Native relabels and deletions retire the
        previous key prospectively; validity changes retain earlier knowledge.
        """
        _validate_scope(subject_type, provider_entity_id, provider_competition_id)
        for field, value in (("valid_at", valid_at), ("knowledge_cutoff", knowledge_cutoff)):
            if value.utcoffset() is None:
                raise ValueError(f"{field} must include a timezone")
        with self._connection.cursor(row_factory=class_row(ProviderMapping)) as cursor:
            return tuple(
                cursor.execute(
                    """WITH candidates AS (
                       SELECT DISTINCT mapping_id FROM football.provider_mapping_history
                       WHERE subject_type=%s AND provider_id=%s AND provider_entity_id=%s
                         AND provider_competition_id IS NOT DISTINCT FROM %s::text
                   ), states AS (
                       SELECT DISTINCT ON (h.mapping_id) h.*
                       FROM football.provider_mapping_history h JOIN candidates c USING(mapping_id)
                       WHERE h.subject_type=%s AND h.known_at<=%s
                       ORDER BY h.mapping_id,h.known_at DESC,h.history_id DESC
                   )
                   SELECT history_id,subject_type,mapping_id,canonical_id,provider_id,
                          provider_entity_id,provider_competition_id,valid_from,valid_to,
                          first_seen_at,mapping_created_at,mapping_method,mapping_confidence,
                          source_snapshot_id,recorded_at,known_at
                   FROM states WHERE provider_id=%s AND provider_entity_id=%s
                     AND provider_competition_id IS NOT DISTINCT FROM %s::text
                     AND operation<>'DELETE'
                     AND (valid_from IS NULL OR valid_from<=%s)
                     AND (valid_to IS NULL OR %s<valid_to)
                   ORDER BY mapping_id""",
                    (
                        subject_type,
                        provider_id,
                        provider_entity_id,
                        provider_competition_id,
                        subject_type,
                        knowledge_cutoff,
                        provider_id,
                        provider_entity_id,
                        provider_competition_id,
                        valid_at,
                        valid_at,
                    ),
                ).fetchall()
            )


def _validate_scope(subject: str, native_id: str, competition: str | None) -> None:
    if subject not in ("competition", "season", "team", "player", "match"):
        raise ValueError("identity subject has no existing provider mapping contract")
    if not native_id:
        raise ValueError("provider native identity is required")
    if subject == "season" and not competition:
        raise ValueError("season identity requires its provider competition")
    if subject != "season" and competition is not None:
        raise ValueError("provider competition scope applies only to season identities")
