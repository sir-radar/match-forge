"""Point-in-time builders for governed contextual feature families."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from football.context.live import (
    UNAVAILABLE_STATES,
    AvailabilityObservation,
    AvailabilityState,
    CoachObservation,
    LineupMode,
    LineupObservation,
    LineupRole,
    predict_lineup,
)


@dataclass(frozen=True, slots=True)
class TeamMatch:
    fixture_id: UUID
    team_id: UUID
    kickoff_at: datetime
    known_at: datetime
    coach_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QualifiedVenue:
    latitude: float
    longitude: float
    timezone: str
    qualified: bool

    def __post_init__(self) -> None:
        if not -90.0 <= self.latitude <= 90.0 or not -180.0 <= self.longitude <= 180.0:
            raise ValueError("venue coordinates are outside valid bounds")
        ZoneInfo(self.timezone)


def availability_lineup_features(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    lineup_history: tuple[LineupObservation, ...],
    availability_history: tuple[AvailabilityObservation, ...],
    coach_history: tuple[CoachObservation, ...],
) -> dict[str, float | str | None]:
    """Build team-level lineup features without target-outcome access."""
    eligible_previous = tuple(
        sorted(
            (
                row
                for row in lineup_history
                if row.team_id == team_id
                and row.lineup_mode is LineupMode.CONFIRMED
                and row.kickoff_at < target_kickoff
                and row.known_at <= knowledge_cutoff
            ),
            key=lambda row: (row.kickoff_at, str(row.lineup_observation_id)),
            reverse=True,
        )
    )
    confirmed = max(
        (
            row
            for row in lineup_history
            if row.team_id == team_id
            and row.lineup_mode is LineupMode.CONFIRMED
            and row.fixture_id == _target_fixture_id(lineup_history, team_id, target_kickoff)
            and row.kickoff_at == target_kickoff
            and row.known_at <= knowledge_cutoff
        ),
        key=lambda row: (row.known_at, str(row.lineup_observation_id)),
        default=None,
    )
    latest_availability = _availability_at(
        team_id, target_kickoff, knowledge_cutoff, availability_history
    )
    previous_ids = _starter_ids(eligible_previous[0]) if eligible_previous else set()
    unavailable_previous = previous_ids & set(latest_availability)
    current_coach = _current_coach_at(team_id, target_kickoff, knowledge_cutoff, coach_history)
    preference_history = tuple(
        row
        for row in eligible_previous
        if current_coach is not None and row.coach_id == current_coach
    )[:10]
    preferred_ids, preference_scores = _preferred_starters(preference_history)
    result: dict[str, float | str | None] = {
        "unavailable_previous_starters_count": float(len(unavailable_previous)),
        "injured_previous_starters_count": float(
            sum(
                latest_availability[player] is AvailabilityState.UNAVAILABLE_INJURY
                for player in unavailable_previous
            )
        ),
        "suspended_previous_starters_count": float(
            sum(
                latest_availability[player] is AvailabilityState.UNAVAILABLE_SUSPENSION
                for player in unavailable_previous
            )
        ),
        "unavailable_preferred_starters_count": (
            float(len(preferred_ids & set(latest_availability))) if preference_history else None
        ),
        "predicted_xi_continuity": None,
        "confirmed_xi_continuity": None,
        "formation_changed": None,
        "coach_preference_replacement_gap": None,
        "replacement_count": None,
        "unresolved_lineup_slots": None,
        "lineup_mode": LineupMode.UNKNOWN.value,
        "prediction_confidence": None,
    }
    if confirmed is not None:
        result.update(
            {
                "confirmed_xi_continuity": _continuity(confirmed, eligible_previous),
                "formation_changed": _formation_changed(confirmed, eligible_previous),
                "lineup_mode": LineupMode.CONFIRMED.value,
                "replacement_count": float(
                    len(previous_ids - _starter_ids(confirmed)) if eligible_previous else 0
                ),
                "unresolved_lineup_slots": 0.0,
            }
        )
        return result
    if not eligible_previous:
        return result
    predicted = predict_lineup(
        team_id,
        target_kickoff,
        knowledge_cutoff,
        lineup_history,
        availability_history,
        coach_history,
    )
    predicted_ids = {row.player_id for row in predicted.starters}
    replacement_gaps = tuple(
        preference_scores.get(row.replaced_player_id, 0.0)
        - preference_scores.get(row.player_id, 0.0)
        for row in predicted.starters
        if row.replaced_player_id is not None
    )
    result.update(
        {
            "predicted_xi_continuity": len(predicted_ids & previous_ids) / 11.0,
            "formation_changed": float(predicted.formation != eligible_previous[0].formation),
            "coach_preference_replacement_gap": (
                sum(replacement_gaps) / len(replacement_gaps) if replacement_gaps else 0.0
            ),
            "replacement_count": float(
                sum(row.replaced_player_id is not None for row in predicted.starters)
            ),
            "unresolved_lineup_slots": float(len(predicted.unresolved_slots)),
            "lineup_mode": LineupMode.PREDICTED_REPEAT_XI.value,
            "prediction_confidence": predicted.confidence.value,
        }
    )
    return result


def rest_congestion_features(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    matches: tuple[TeamMatch, ...],
) -> dict[str, float | None]:
    eligible = tuple(
        row.kickoff_at
        for row in matches
        if row.team_id == team_id
        and row.kickoff_at < target_kickoff
        and row.known_at <= knowledge_cutoff
    )
    latest = max(eligible, default=None)
    return {
        "days_since_last_match": (
            (target_kickoff - latest).total_seconds() / 86_400.0 if latest else None
        ),
        "matches_last_3_days": float(_recent_count(eligible, target_kickoff, 3)),
        "matches_last_7_days": float(_recent_count(eligible, target_kickoff, 7)),
        "matches_last_14_days": float(_recent_count(eligible, target_kickoff, 14)),
        "matches_last_30_days": float(_recent_count(eligible, target_kickoff, 30)),
    }


def manager_features(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    matches: tuple[TeamMatch, ...],
    coaches: tuple[CoachObservation, ...],
) -> dict[str, float | None]:
    current = max(
        (
            row
            for row in coaches
            if row.team_id == team_id
            and row.effective_at < target_kickoff
            and row.known_at <= knowledge_cutoff
        ),
        key=lambda row: (row.effective_at, str(row.coach_id)),
        default=None,
    )
    if current is None:
        return {
            "coach_tenure_days": None,
            "matches_under_coach": None,
            "coach_changed_recently": None,
        }
    match_count = sum(
        row.team_id == team_id
        and row.coach_id == current.coach_id
        and current.effective_at <= row.kickoff_at < target_kickoff
        and row.known_at <= knowledge_cutoff
        for row in matches
    )
    return {
        "coach_tenure_days": (target_kickoff - current.effective_at).total_seconds() / 86_400.0,
        "matches_under_coach": float(match_count),
        "coach_changed_recently": float(match_count < 5),
    }


def travel_features(
    team_venue: QualifiedVenue | None,
    match_venue: QualifiedVenue | None,
    *,
    neutral_venue: bool,
    kickoff_at: datetime | None = None,
) -> dict[str, float]:
    if (
        team_venue is None
        or match_venue is None
        or not team_venue.qualified
        or not match_venue.qualified
    ):
        raise ValueError("travel features require qualified venue coordinates")
    when = kickoff_at or datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))
    team_offset = when.astimezone(ZoneInfo(team_venue.timezone)).utcoffset()
    match_offset = when.astimezone(ZoneInfo(match_venue.timezone)).utcoffset()
    if team_offset is None or match_offset is None:
        raise ValueError("venue timezone offset unavailable")
    return {
        "travel_distance_km": _haversine_km(team_venue, match_venue),
        "timezone_delta_hours": abs((match_offset - team_offset).total_seconds()) / 3600.0,
        "neutral_venue": float(neutral_venue),
    }


def _target_fixture_id(
    history: tuple[LineupObservation, ...], team_id: UUID, target_kickoff: datetime
) -> UUID | None:
    identifiers = {
        row.fixture_id
        for row in history
        if row.team_id == team_id and row.kickoff_at == target_kickoff
    }
    if len(identifiers) > 1:
        raise ValueError("target lineup history contains multiple fixtures at kickoff")
    return next(iter(identifiers), None)


def _availability_at(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    history: tuple[AvailabilityObservation, ...],
) -> dict[UUID, AvailabilityState]:
    latest: dict[UUID, AvailabilityObservation] = {}
    for row in history:
        if (
            row.team_id != team_id
            or row.canonical_player_id is None
            or row.observed_at >= target_kickoff
            or row.known_at > knowledge_cutoff
            or row.availability_state not in UNAVAILABLE_STATES
        ):
            continue
        prior = latest.get(row.canonical_player_id)
        if prior is None or (row.known_at, row.observed_at, str(row.observation_id)) > (
            prior.known_at,
            prior.observed_at,
            str(prior.observation_id),
        ):
            latest[row.canonical_player_id] = row
    return {player: row.availability_state for player, row in latest.items()}


def _current_coach_at(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    history: tuple[CoachObservation, ...],
) -> UUID | None:
    current = max(
        (
            row
            for row in history
            if row.team_id == team_id
            and row.effective_at < target_kickoff
            and row.known_at <= knowledge_cutoff
        ),
        key=lambda row: (row.effective_at, str(row.coach_id)),
        default=None,
    )
    return current.coach_id if current else None


def _preferred_starters(
    history: tuple[LineupObservation, ...],
) -> tuple[set[UUID], dict[UUID, float]]:
    if not history:
        return set(), {}
    scores: dict[UUID, float] = {}
    positions: dict[UUID, str] = {}
    for index, lineup in enumerate(history):
        weight = 0.85**index
        for player in lineup.players:
            if player.role is not LineupRole.STARTER:
                continue
            scores[player.canonical_player_id] = (
                scores.get(player.canonical_player_id, 0.0) + weight
            )
            positions.setdefault(player.canonical_player_id, player.normalized_position)
    selected: set[UUID] = set()
    for slot in (player for player in history[0].players if player.role is LineupRole.STARTER):
        candidate = min(
            (
                player_id
                for player_id, position in positions.items()
                if position == slot.normalized_position and player_id not in selected
            ),
            key=lambda player_id: (-scores[player_id], str(player_id)),
            default=None,
        )
        if candidate is not None:
            selected.add(candidate)
    return selected, scores


def _starter_ids(lineup: LineupObservation) -> set[UUID]:
    return {row.canonical_player_id for row in lineup.players if row.role is LineupRole.STARTER}


def _continuity(
    current: LineupObservation, previous: tuple[LineupObservation, ...]
) -> float | None:
    if not previous:
        return None
    return len(_starter_ids(current) & _starter_ids(previous[0])) / 11.0


def _formation_changed(
    current: LineupObservation, previous: tuple[LineupObservation, ...]
) -> float | None:
    if not previous or current.formation is None or previous[0].formation is None:
        return None
    return float(current.formation != previous[0].formation)


def _recent_count(values: tuple[datetime, ...], cutoff: datetime, days: int) -> int:
    lower = cutoff - timedelta(days=days)
    return sum(lower <= value < cutoff for value in values)


def _haversine_km(first: QualifiedVenue, second: QualifiedVenue) -> float:
    first_lat, second_lat = math.radians(first.latitude), math.radians(second.latitude)
    delta_lat = second_lat - first_lat
    delta_lon = math.radians(second.longitude - first.longitude)
    value = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(first_lat) * math.cos(second_lat) * math.sin(delta_lon / 2.0) ** 2
    )
    return 6_371.0088 * 2.0 * math.asin(math.sqrt(value))
