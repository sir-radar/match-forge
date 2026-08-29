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


def _require_aware(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValueError("knowledge_cutoff must include a timezone")
