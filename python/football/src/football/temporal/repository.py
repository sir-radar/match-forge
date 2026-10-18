"""Point-in-time access to provider observations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import class_row


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    """Player representation visible during one system-knowledge interval."""

    id: uuid.UUID
    player_id: uuid.UUID
    provider_id: uuid.UUID
    full_name: str
    nickname: str | None
    known_from: datetime
    known_to: datetime | None
    source_snapshot_id: uuid.UUID


class PointInTimeRepository:
    """Supported application boundary for bitemporal observation reads."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def player_observation_at(
        self,
        player_id: uuid.UUID,
        provider_id: uuid.UUID,
        knowledge_cutoff: datetime,
    ) -> PlayerObservation | None:
        """Return observation known at cutoff using half-open interval semantics."""
        _require_aware(knowledge_cutoff)
        with self._connection.cursor(row_factory=class_row(PlayerObservation)) as cursor:
            return cursor.execute(
                """
                SELECT id, player_id, provider_id, full_name, nickname, known_from,
                       known_to, source_snapshot_id
                FROM football.player_observations
                WHERE player_id = %s
                  AND provider_id = %s
                  AND football.known_at(known_from, known_to, %s)
                ORDER BY known_from DESC
                LIMIT 1
                """,
                (player_id, provider_id, knowledge_cutoff),
            ).fetchone()

    def current_player_observation(
        self, player_id: uuid.UUID, provider_id: uuid.UUID
    ) -> PlayerObservation | None:
        """Return current projection; modelling code should prefer an explicit cutoff."""
        with self._connection.cursor(row_factory=class_row(PlayerObservation)) as cursor:
            return cursor.execute(
                """
                SELECT id, player_id, provider_id, full_name, nickname, known_from,
                       known_to, source_snapshot_id
                FROM football.current_player_observations
                WHERE player_id = %s
                  AND provider_id = %s
                ORDER BY known_from DESC
                LIMIT 1
                """,
                (player_id, provider_id),
            ).fetchone()

    def resource_observation_ids_at(
        self,
        contract_name: str,
        provider_id: uuid.UUID,
        knowledge_cutoff: datetime,
        *,
        football_cutoff: datetime | None = None,
        valid_at: datetime | None = None,
    ) -> tuple[uuid.UUID, ...]:
        """Return immutable evidence known by the cutoff, without resolving conflicts.

        Football history requires an explicit, strictly earlier event time.
        A requested validity instant requires a reported start and uses [start, end).
        Omitted football/validity filters ask only what source facts were known;
        they do not qualify those facts as model history or forecast context.
        """
        _require_aware(knowledge_cutoff)
        if football_cutoff is not None:
            _require_aware(football_cutoff, "football_cutoff")
        if valid_at is not None:
            _require_aware(valid_at, "valid_at")
        rows = self._connection.execute(
            """SELECT observation_id FROM football.resource_observation_artifacts
               WHERE contract_name=%s AND provider_id=%s AND known_at<=%s
                 AND (%s::timestamptz IS NULL OR event_time<%s)
                 AND (%s::timestamptz IS NULL OR
                      (valid_from<=%s AND (valid_to IS NULL OR %s<valid_to)))
               ORDER BY known_at,observation_id""",
            (
                contract_name,
                provider_id,
                knowledge_cutoff,
                football_cutoff,
                football_cutoff,
                valid_at,
                valid_at,
                valid_at,
            ),
        ).fetchall()
        return tuple(row[0] for row in rows)


def _require_aware(value: datetime, field: str = "knowledge_cutoff") -> None:
    if value.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
