"""API-Football fixture context parsing and append-only persistence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.context.live import (
    AvailabilityObservation,
    AvailabilityState,
    AvailabilityType,
    CoachObservation,
    LineupMode,
    LineupObservation,
    LineupPlayer,
    LineupRole,
    predict_lineup,
)
from football.product.api_football import ApiResponse
from football.product.domain import sha256_json, stable_id

PROVIDER = "api_football"


@dataclass(frozen=True, slots=True)
class ProviderAvailability:
    provider_team_id: str
    provider_player_id: str
    availability_type: AvailabilityType
    availability_state: AvailabilityState
    reason: str | None


@dataclass(frozen=True, slots=True)
class ProviderLineupPlayer:
    provider_player_id: str
    role: LineupRole
    position: str
    normalized_position: str
    grid_position: str | None


@dataclass(frozen=True, slots=True)
class ProviderLineup:
    provider_team_id: str
    formation: str | None
    provider_coach_id: str | None
    players: tuple[ProviderLineupPlayer, ...]


def parse_availability(rows: Sequence[Mapping[str, Any]]) -> tuple[ProviderAvailability, ...]:
    items: list[ProviderAvailability] = []
    for row in rows:
        team = _mapping(row, "team")
        player = _mapping(row, "player")
        raw_type = str(row.get("type") or "").casefold()
        reason = str(row.get("reason") or row.get("type") or "") or None
        if "susp" in raw_type or (reason and "susp" in reason.casefold()):
            kind = AvailabilityType.SUSPENSION
            state = AvailabilityState.UNAVAILABLE_SUSPENSION
        elif "injur" in raw_type or raw_type == "missing fixture":
            kind = AvailabilityType.INJURY
            state = AvailabilityState.UNAVAILABLE_INJURY
        else:
            kind = AvailabilityType.OTHER
            state = AvailabilityState.UNAVAILABLE_OTHER
        items.append(
            ProviderAvailability(
                str(_integer(team, "id")),
                str(_integer(player, "id")),
                kind,
                state,
                reason,
            )
        )
    return tuple(items)


def parse_lineups(rows: Sequence[Mapping[str, Any]]) -> tuple[ProviderLineup, ...]:
    items: list[ProviderLineup] = []
    for row in rows:
        team = _mapping(row, "team")
        coach = row.get("coach")
        provider_coach_id = None
        if isinstance(coach, Mapping) and coach.get("id") is not None:
            provider_coach_id = str(coach["id"])
        players: list[ProviderLineupPlayer] = []
        for key, role in (("startXI", LineupRole.STARTER), ("substitutes", LineupRole.BENCH)):
            values = row.get(key, [])
            if not isinstance(values, list):
                raise ValueError(f"provider field {key} must be a list")
            for wrapped in cast(list[Mapping[str, Any]], values):
                player = _mapping(wrapped, "player")
                position = str(player.get("pos") or "UNKNOWN")
                players.append(
                    ProviderLineupPlayer(
                        str(_integer(player, "id")),
                        role,
                        position,
                        normalize_position(position),
                        str(player["grid"]) if player.get("grid") is not None else None,
                    )
                )
        items.append(
            ProviderLineup(
                str(_integer(team, "id")),
                str(row["formation"]) if row.get("formation") else None,
                provider_coach_id,
                tuple(players),
            )
        )
    return tuple(items)


class ContextObservationStore:
    def __init__(self, connection: Connection[Any]) -> None:
        self.connection = connection

    def persist_availability(
        self,
        fixture_id: UUID,
        response: ApiResponse,
        source_snapshot_id: UUID,
    ) -> int:
        checksum = hashlib.sha256(response.raw).hexdigest()
        count = 0
        for item in parse_availability(response.rows):
            team_id = self._team_id(item.provider_team_id)
            if team_id is None:
                continue
            player_id = self._player_id(item.provider_player_id, response.fetched_at)
            semantic = (
                fixture_id,
                team_id,
                item.provider_player_id,
                item.availability_type.value,
                item.availability_state.value,
                checksum,
            )
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.product_availability_observations (
                        observation_id, fixture_id, team_id, canonical_player_id,
                        provider_player_id, availability_type, availability_state,
                        reason, observed_at, known_at, provider, source_snapshot_id,
                        source_checksum
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'api_football', %s, %s)
                    ON CONFLICT (
                        fixture_id, team_id, provider_player_id, availability_type,
                        availability_state, source_checksum
                    ) DO NOTHING
                    """,
                    (
                        stable_id("availability-observation", *semantic),
                        fixture_id,
                        team_id,
                        player_id,
                        item.provider_player_id,
                        item.availability_type.value,
                        item.availability_state.value,
                        item.reason,
                        response.fetched_at,
                        response.fetched_at,
                        source_snapshot_id,
                        checksum,
                    ),
                )
                count += cursor.rowcount
        count += self._persist_no_reported_issue(fixture_id, response, source_snapshot_id, checksum)
        return count

    def persist_lineups(
        self,
        fixture_id: UUID,
        kickoff_at: datetime,
        response: ApiResponse,
        source_snapshot_id: UUID,
    ) -> int:
        checksum = hashlib.sha256(response.raw).hexdigest()
        count = 0
        for lineup in parse_lineups(response.rows):
            team_id = self._team_id(lineup.provider_team_id)
            if team_id is None:
                continue
            coach_id = (
                stable_id("coach", PROVIDER, lineup.provider_coach_id)
                if lineup.provider_coach_id
                else None
            )
            lineup_id = stable_id("lineup-observation", fixture_id, team_id, "CONFIRMED", checksum)
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT lineup_observation_id
                    FROM football.product_lineup_observations
                    WHERE fixture_id = %s AND team_id = %s
                      AND lineup_mode = 'PREDICTED_REPEAT_XI'
                      AND known_at <= %s
                    ORDER BY known_at DESC LIMIT 1
                    """,
                    (fixture_id, team_id, response.fetched_at),
                )
                predicted = cursor.fetchone()
                cursor.execute(
                    """
                    INSERT INTO football.product_lineup_observations (
                        lineup_observation_id, fixture_id, team_id, kickoff_at,
                        lineup_mode, formation, coach_id, provider_coach_id,
                        supersedes_predicted_lineup_id, observed_at, known_at,
                        provider, source_snapshot_id, source_checksum
                    ) VALUES (%s, %s, %s, %s, 'CONFIRMED', %s, %s, %s, %s,
                        %s, %s, 'api_football', %s, %s)
                    ON CONFLICT (fixture_id, team_id, lineup_mode, source_checksum)
                    DO NOTHING
                    """,
                    (
                        lineup_id,
                        fixture_id,
                        team_id,
                        kickoff_at,
                        lineup.formation,
                        coach_id,
                        lineup.provider_coach_id,
                        predicted[0] if predicted else None,
                        response.fetched_at,
                        response.fetched_at,
                        source_snapshot_id,
                        checksum,
                    ),
                )
                inserted = cursor.rowcount
                count += inserted
                if inserted and coach_id is not None:
                    cursor.execute(
                        """
                        INSERT INTO football.product_coach_observations (
                            coach_observation_id, team_id, coach_id, provider_coach_id,
                            effective_at, observed_at, known_at, provider,
                            source_snapshot_id, source_checksum
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s,
                            'api_football', %s, %s)
                        ON CONFLICT (team_id, coach_id, effective_at, source_checksum)
                        DO NOTHING
                        """,
                        (
                            stable_id("coach-observation", team_id, coach_id, kickoff_at, checksum),
                            team_id,
                            coach_id,
                            lineup.provider_coach_id,
                            kickoff_at,
                            response.fetched_at,
                            response.fetched_at,
                            source_snapshot_id,
                            checksum,
                        ),
                    )
                if inserted:
                    self._persist_lineup_players(cursor, lineup_id, lineup, response.fetched_at)
                    if predicted:
                        self._persist_lineup_accuracy(
                            cursor, predicted[0], lineup_id, response.fetched_at
                        )
        return count

    def _persist_lineup_accuracy(
        self, cursor: Any, predicted_id: UUID, confirmed_id: UUID, calculated_at: datetime
    ) -> None:
        cursor.execute(
            """
            WITH predicted AS (
                SELECT canonical_player_id, selection_reason, replaced_player_id
                FROM football.product_lineup_players
                WHERE lineup_observation_id = %s AND role = 'STARTER'
                  AND canonical_player_id IS NOT NULL
            ), confirmed AS (
                SELECT canonical_player_id
                FROM football.product_lineup_players
                WHERE lineup_observation_id = %s AND role = 'STARTER'
                  AND canonical_player_id IS NOT NULL
            )
            SELECT
                (SELECT count(*) FROM predicted JOIN confirmed USING (canonical_player_id)),
                (SELECT count(*) FROM predicted),
                (SELECT count(*) FROM confirmed),
                (SELECT count(*) FROM predicted WHERE replaced_player_id IS NOT NULL),
                (SELECT count(*) FROM predicted JOIN confirmed USING (canonical_player_id)
                  WHERE predicted.replaced_player_id IS NOT NULL),
                (SELECT count(*) FROM predicted
                  WHERE selection_reason = 'MOST_USED_EXACT_POSITION_ALTERNATIVE'),
                (SELECT count(*) FROM predicted JOIN confirmed USING (canonical_player_id)
                  WHERE predicted.selection_reason = 'MOST_USED_EXACT_POSITION_ALTERNATIVE')
            """,
            (predicted_id, confirmed_id),
        )
        (
            correct,
            predicted_count,
            confirmed_count,
            replacements,
            correct_replacements,
            exact,
            correct_exact,
        ) = cursor.fetchone()
        cursor.execute(
            """
            SELECT predicted.formation = confirmed.formation,
                   predicted.preference_sample_size, predicted.prediction_confidence
            FROM football.product_lineup_observations predicted
            JOIN football.product_lineup_observations confirmed
              ON confirmed.lineup_observation_id = %s
            WHERE predicted.lineup_observation_id = %s
            """,
            (confirmed_id, predicted_id),
        )
        formation_match, sample_size, confidence = cursor.fetchone()
        cursor.execute(
            """
            INSERT INTO football.product_lineup_accuracy (
                predicted_lineup_id, confirmed_lineup_id, correct_starting_players,
                xi_precision, xi_recall, formation_match, replacement_player_accuracy,
                exact_position_replacement_accuracy, coach_preference_sample_size,
                prediction_confidence, calculated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                predicted_id,
                confirmed_id,
                correct,
                correct / predicted_count if predicted_count else 0.0,
                correct / confirmed_count if confirmed_count else 0.0,
                formation_match,
                correct_replacements / replacements if replacements else None,
                correct_exact / exact if exact else None,
                sample_size,
                confidence,
                calculated_at,
            ),
        )

    def persist_predicted_lineups(
        self,
        fixtures: Sequence[tuple[UUID, datetime, UUID, UUID]],
        knowledge_cutoff: datetime,
    ) -> int:
        count = 0
        for fixture_id, kickoff_at, home_id, away_id in fixtures:
            for team_id in (home_id, away_id):
                if self._confirmed_target_lineup_exists(
                    fixture_id, team_id, kickoff_at, knowledge_cutoff
                ):
                    continue
                history = self._lineup_history(team_id, kickoff_at, knowledge_cutoff)
                if not history:
                    continue
                availability = self._availability_history(
                    fixture_id, team_id, kickoff_at, knowledge_cutoff
                )
                coaches = self._coach_history(team_id, kickoff_at, knowledge_cutoff)
                prediction = predict_lineup(
                    team_id,
                    kickoff_at,
                    knowledge_cutoff,
                    history,
                    availability,
                    coaches,
                )
                payload = {
                    "team_id": str(team_id),
                    "kickoff_at": kickoff_at.isoformat(),
                    "knowledge_cutoff": knowledge_cutoff.isoformat(),
                    "based_on_lineup_id": str(prediction.based_on_lineup_id),
                    "formation": prediction.formation,
                    "coach_id": str(prediction.coach_id) if prediction.coach_id else None,
                    "confidence": prediction.confidence.value,
                    "starters": [
                        {
                            "player_id": str(item.player_id),
                            "position": item.normalized_position,
                            "selection_reason": item.selection_reason.value,
                            "replaced_player_id": (
                                str(item.replaced_player_id) if item.replaced_player_id else None
                            ),
                        }
                        for item in prediction.starters
                    ],
                    "unresolved": [
                        {
                            "replaced_player_id": str(item.replaced_player_id),
                            "position": item.normalized_position,
                        }
                        for item in prediction.unresolved_slots
                    ],
                }
                checksum = sha256_json(payload)
                lineup_id = stable_id(
                    "lineup-observation", fixture_id, team_id, "PREDICTED_REPEAT_XI", checksum
                )
                base = next(
                    item
                    for item in history
                    if item.lineup_observation_id == prediction.based_on_lineup_id
                )
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO football.product_lineup_observations (
                            lineup_observation_id, fixture_id, team_id, kickoff_at,
                            lineup_mode, formation, coach_id, prediction_confidence,
                            coach_context, preference_sample_size, based_on_lineup_id,
                            observed_at, known_at, provider, source_snapshot_id,
                            source_checksum
                        ) VALUES (%s, %s, %s, %s, 'PREDICTED_REPEAT_XI', %s, %s,
                            %s, %s, %s, %s, %s, %s, 'matchforge', %s, %s)
                        ON CONFLICT (fixture_id, team_id, lineup_mode, source_checksum)
                        DO NOTHING
                        """,
                        (
                            lineup_id,
                            fixture_id,
                            team_id,
                            kickoff_at,
                            prediction.formation,
                            prediction.coach_id,
                            prediction.confidence.value,
                            prediction.coach_context,
                            prediction.preference_sample_size,
                            prediction.based_on_lineup_id,
                            knowledge_cutoff,
                            knowledge_cutoff,
                            base.source_snapshot_id,
                            checksum,
                        ),
                    )
                    inserted = cursor.rowcount
                    count += inserted
                    if inserted:
                        self._persist_predicted_players(cursor, lineup_id, prediction)
        return count

    def _confirmed_target_lineup_exists(
        self,
        fixture_id: UUID,
        team_id: UUID,
        kickoff_at: datetime,
        knowledge_cutoff: datetime,
    ) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM football.product_lineup_observations
                    WHERE fixture_id = %s AND team_id = %s
                      AND lineup_mode = 'CONFIRMED'
                      AND observed_at < %s AND known_at <= %s
                )
                """,
                (fixture_id, team_id, kickoff_at, knowledge_cutoff),
            )
            row = cursor.fetchone()
        return bool(row and row[0])

    def persist_context_snapshots(
        self,
        fixtures: Sequence[tuple[UUID, datetime, UUID, UUID]],
        knowledge_cutoff: datetime,
    ) -> int:
        count = 0
        for fixture_id, kickoff_at, home_id, away_id in fixtures:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT observation_id::text, team_id::text, provider_player_id,
                           availability_type, availability_state, reason,
                           observed_at, known_at, provider, source_snapshot_id::text,
                           source_checksum
                    FROM football.product_availability_observations
                    WHERE fixture_id = %s AND observed_at < %s AND known_at <= %s
                    ORDER BY team_id, provider_player_id, known_at, observation_id
                    """,
                    (fixture_id, kickoff_at, knowledge_cutoff),
                )
                availability = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT lineup_observation_id::text, team_id::text, lineup_mode,
                           formation, coach_id::text, prediction_confidence,
                           source_snapshot_id::text, source_checksum
                    FROM football.product_lineup_observations
                    WHERE fixture_id = %s AND observed_at < %s AND known_at <= %s
                    ORDER BY team_id, lineup_mode, known_at, lineup_observation_id
                    """,
                    (fixture_id, kickoff_at, knowledge_cutoff),
                )
                lineups = cursor.fetchall()
                cursor.execute(
                    """
                    SELECT history.fixture_id::text, history.kickoff_at
                    FROM football.product_team_match_history history
                    JOIN football.source_snapshots snapshot
                      ON snapshot.id = history.source_snapshot_id
                    WHERE (home_team_id IN (%s, %s) OR away_team_id IN (%s, %s))
                      AND ((source_kickoff_precision = 'EXACT' AND kickoff_at < %s)
                        OR (source_kickoff_precision = 'DATE_ONLY'
                            AND kickoff_at::date < %s::date))
                      AND snapshot.acquired_at <= %s
                    ORDER BY kickoff_at, fixture_id
                    """,
                    (
                        home_id,
                        away_id,
                        home_id,
                        away_id,
                        kickoff_at,
                        kickoff_at,
                        knowledge_cutoff,
                    ),
                )
                history = cursor.fetchall()
            information_ids = [row[0] for row in availability] + [row[0] for row in lineups]
            payload = {
                "availability": [
                    {
                        "observation_id": row[0],
                        "team_id": row[1],
                        "provider_player_id": row[2],
                        "availability_type": row[3],
                        "availability_state": row[4],
                        "reason": row[5],
                        "observed_at": row[6].isoformat(),
                        "known_at": row[7].isoformat(),
                        "provider": row[8],
                        "source_snapshot_id": row[9],
                        "source_checksum": row[10],
                    }
                    for row in availability
                ],
                "lineups": [
                    {
                        "lineup_observation_id": row[0],
                        "team_id": row[1],
                        "lineup_mode": row[2],
                        "formation": row[3],
                        "coach_id": row[4],
                        "prediction_confidence": row[5],
                        "source_snapshot_id": row[6],
                        "source_checksum": row[7],
                    }
                    for row in lineups
                ],
                "coach_context": [row[4] for row in lineups if row[4]],
                "rest_context": {
                    "eligible_history": [
                        {"fixture_id": row[0], "kickoff_at": row[1].isoformat()} for row in history
                    ]
                },
                "context_missingness": [
                    name
                    for name, missing in (
                        ("AVAILABILITY_UNVERIFIED", not availability),
                        ("LINEUP_UNAVAILABLE", not lineups),
                    )
                    if missing
                ],
                "context_provenance": sorted(
                    {row[9] for row in availability} | {row[6] for row in lineups}
                ),
            }
            checksum = sha256_json(payload)
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.product_context_snapshots (
                        context_snapshot_id, fixture_id, football_cutoff,
                        knowledge_cutoff, context_snapshot, context_snapshot_sha256,
                        source_information_ids, created_at
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s)
                    ON CONFLICT (fixture_id, context_snapshot_sha256) DO NOTHING
                    """,
                    (
                        stable_id("context-snapshot", fixture_id, checksum),
                        fixture_id,
                        kickoff_at,
                        knowledge_cutoff,
                        json.dumps(payload),
                        checksum,
                        json.dumps(information_ids),
                        knowledge_cutoff,
                    ),
                )
                count += cursor.rowcount
        return count

    def _persist_predicted_players(self, cursor: Any, lineup_id: UUID, prediction: Any) -> None:
        for slot, player in enumerate(prediction.starters):
            cursor.execute(
                """
                INSERT INTO football.product_lineup_players (
                    lineup_observation_id, canonical_player_id, provider_player_id,
                    role, position, normalized_position, grid_position, slot_order,
                    availability_state, selection_reason, replaced_player_id,
                    replacement_reason, preference_score, historical_start_count
                ) VALUES (%s, %s, %s, 'STARTER', %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s)
                """,
                (
                    lineup_id,
                    player.player_id,
                    player.provider_player_id,
                    player.position,
                    player.normalized_position,
                    player.grid_position,
                    slot,
                    player.availability_state.value,
                    player.selection_reason.value,
                    player.replaced_player_id,
                    player.replacement_reason.value if player.replacement_reason else None,
                    player.preference_score,
                    player.historical_start_count,
                ),
            )
        offset = len(prediction.starters)
        for index, slot in enumerate(prediction.unresolved_slots):
            cursor.execute(
                """
                INSERT INTO football.product_lineup_players (
                    lineup_observation_id, provider_player_id, role, position,
                    normalized_position, grid_position, slot_order,
                    availability_state, replaced_player_id, slot_status
                ) VALUES (%s, %s, 'STARTER', %s, %s, %s, %s, 'UNKNOWN', %s, 'UNRESOLVED')
                """,
                (
                    lineup_id,
                    f"unresolved:{slot.replaced_player_id}",
                    slot.normalized_position,
                    slot.normalized_position,
                    slot.grid_position,
                    offset + index,
                    slot.replaced_player_id,
                ),
            )

    def _lineup_history(
        self, team_id: UUID, kickoff_at: datetime, knowledge_cutoff: datetime
    ) -> tuple[LineupObservation, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT lineup_observation_id, fixture_id, team_id, kickoff_at,
                       lineup_mode, formation, coach_id, provider_coach_id,
                       observed_at, known_at, provider, source_snapshot_id,
                       source_checksum, supersedes_predicted_lineup_id
                FROM football.product_lineup_observations
                WHERE team_id = %s AND lineup_mode = 'CONFIRMED'
                  AND kickoff_at < %s AND known_at <= %s
                ORDER BY kickoff_at DESC, known_at DESC LIMIT 30
                """,
                (team_id, kickoff_at, knowledge_cutoff),
            )
            rows = cursor.fetchall()
        items: list[LineupObservation] = []
        for row in rows:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT canonical_player_id, provider_player_id, role, position,
                           normalized_position, grid_position
                    FROM football.product_lineup_players
                    WHERE lineup_observation_id = %s AND canonical_player_id IS NOT NULL
                    ORDER BY slot_order
                    """,
                    (row[0],),
                )
                players = tuple(
                    LineupPlayer(
                        canonical_player_id=player[0],
                        provider_player_id=player[1],
                        role=LineupRole(player[2]),
                        position=player[3],
                        normalized_position=player[4],
                        grid_position=player[5],
                    )
                    for player in cursor.fetchall()
                )
            items.append(
                LineupObservation(
                    lineup_observation_id=row[0],
                    fixture_id=row[1],
                    team_id=row[2],
                    kickoff_at=row[3],
                    lineup_mode=LineupMode(row[4]),
                    formation=row[5],
                    coach_id=row[6],
                    provider_coach_id=row[7],
                    observed_at=row[8],
                    known_at=row[9],
                    provider=row[10],
                    source_snapshot_id=row[11],
                    source_checksum=row[12],
                    players=players,
                    supersedes_predicted_lineup_id=row[13],
                )
            )
        return tuple(items)

    def _availability_history(
        self,
        fixture_id: UUID,
        team_id: UUID,
        kickoff_at: datetime,
        knowledge_cutoff: datetime,
    ) -> tuple[AvailabilityObservation, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT observation_id, fixture_id, team_id, canonical_player_id,
                       provider_player_id, availability_type, availability_state,
                       reason, observed_at, known_at, provider, source_snapshot_id,
                       source_checksum
                FROM football.product_availability_observations
                WHERE fixture_id = %s AND team_id = %s
                  AND observed_at < %s AND known_at <= %s
                ORDER BY known_at, observation_id
                """,
                (fixture_id, team_id, kickoff_at, knowledge_cutoff),
            )
            return tuple(
                AvailabilityObservation(
                    observation_id=row[0],
                    fixture_id=row[1],
                    team_id=row[2],
                    canonical_player_id=row[3],
                    provider_player_id=row[4],
                    availability_type=AvailabilityType(row[5]),
                    availability_state=AvailabilityState(row[6]),
                    reason=row[7],
                    observed_at=row[8],
                    known_at=row[9],
                    provider=row[10],
                    source_snapshot_id=row[11],
                    source_checksum=row[12],
                )
                for row in cursor.fetchall()
            )

    def _coach_history(
        self, team_id: UUID, kickoff_at: datetime, knowledge_cutoff: datetime
    ) -> tuple[CoachObservation, ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT coach_id, team_id, effective_at, known_at
                FROM football.product_coach_observations
                WHERE team_id = %s AND effective_at < %s AND known_at <= %s
                ORDER BY effective_at, coach_id
                """,
                (team_id, kickoff_at, knowledge_cutoff),
            )
            return tuple(CoachObservation(*row) for row in cursor.fetchall())

    def _persist_lineup_players(
        self, cursor: Any, lineup_id: UUID, lineup: ProviderLineup, observed_at: datetime
    ) -> None:
        for slot, player in enumerate(lineup.players):
            cursor.execute(
                """
                INSERT INTO football.product_lineup_players (
                    lineup_observation_id, canonical_player_id, provider_player_id,
                    role, position, normalized_position, grid_position, slot_order,
                    availability_state
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'AVAILABLE_CONFIRMED')
                ON CONFLICT DO NOTHING
                """,
                (
                    lineup_id,
                    self._player_id(player.provider_player_id, observed_at),
                    player.provider_player_id,
                    player.role.value,
                    player.position,
                    player.normalized_position,
                    player.grid_position,
                    slot,
                ),
            )

    def _persist_no_reported_issue(
        self,
        fixture_id: UUID,
        response: ApiResponse,
        source_snapshot_id: UUID,
        checksum: str,
    ) -> int:
        reported = {item.provider_player_id for item in parse_availability(response.rows)}
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT ON (lineup.team_id, player.provider_player_id)
                       lineup.team_id, player.canonical_player_id, player.provider_player_id
                FROM football.product_fixtures fixture
                JOIN football.product_lineup_observations lineup
                  ON lineup.team_id IN (fixture.home_team_id, fixture.away_team_id)
                 AND lineup.lineup_mode = 'CONFIRMED'
                 AND lineup.kickoff_at < fixture.kickoff_at
                 AND lineup.known_at <= %s
                JOIN football.product_lineup_players player
                  ON player.lineup_observation_id = lineup.lineup_observation_id
                 AND player.role = 'STARTER'
                WHERE fixture.fixture_id = %s
                ORDER BY lineup.team_id, player.provider_player_id,
                         lineup.kickoff_at DESC, lineup.known_at DESC
                """,
                (response.fetched_at, fixture_id),
            )
            players = cursor.fetchall()
        count = 0
        for team_id, player_id, provider_player_id in players:
            if provider_player_id in reported:
                continue
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.product_availability_observations (
                        observation_id, fixture_id, team_id, canonical_player_id,
                        provider_player_id, availability_type, availability_state,
                        observed_at, known_at, provider, source_snapshot_id, source_checksum
                    ) VALUES (%s, %s, %s, %s, %s, 'OTHER',
                        'ASSUMED_AVAILABLE_NO_REPORTED_ISSUE', %s, %s,
                        'api_football', %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        stable_id(
                            "availability-observation",
                            fixture_id,
                            team_id,
                            provider_player_id,
                            "NO_REPORTED_ISSUE",
                            checksum,
                        ),
                        fixture_id,
                        team_id,
                        player_id,
                        provider_player_id,
                        response.fetched_at,
                        response.fetched_at,
                        source_snapshot_id,
                        checksum,
                    ),
                )
                count += cursor.rowcount
        return count

    def _team_id(self, provider_team_id: str) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = 'api_football' AND provider_team_id = %s
                """,
                (provider_team_id,),
            )
            row = cursor.fetchone()
        return row[0] if row else None

    def _player_id(self, provider_player_id: str, observed_at: datetime) -> UUID | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT mapping.player_id
                FROM football.player_provider_mappings mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'api_football'
                  AND mapping.provider_player_id = %s
                  AND (mapping.valid_from IS NULL OR mapping.valid_from <= %s)
                  AND (mapping.valid_to IS NULL OR mapping.valid_to > %s)
                ORDER BY mapping.last_seen_at DESC LIMIT 1
                """,
                (provider_player_id, observed_at, observed_at),
            )
            row = cursor.fetchone()
        return row[0] if row else None


def normalize_position(value: str) -> str:
    normalized = value.strip().upper().replace("CF", "ST")
    aliases = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
    return aliases.get(normalized, normalized or "UNKNOWN")


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    found = value.get(key)
    if not isinstance(found, Mapping):
        raise ValueError(f"provider field {key} must be an object")
    return cast(Mapping[str, Any], found)


def _integer(value: Mapping[str, Any], key: str) -> int:
    found = value.get(key)
    if isinstance(found, bool) or not isinstance(found, int):
        raise ValueError(f"provider field {key} must be an integer")
    return found
