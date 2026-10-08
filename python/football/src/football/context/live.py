"""Deterministic point-in-time availability and lineup context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

AVAILABILITY_FRESHNESS = timedelta(hours=4)
COACH_PREFERENCE_WINDOW = 10


class AvailabilityType(StrEnum):
    INJURY = "INJURY"
    SUSPENSION = "SUSPENSION"
    OTHER = "OTHER"


class AvailabilityState(StrEnum):
    AVAILABLE_CONFIRMED = "AVAILABLE_CONFIRMED"
    UNAVAILABLE_INJURY = "UNAVAILABLE_INJURY"
    UNAVAILABLE_SUSPENSION = "UNAVAILABLE_SUSPENSION"
    UNAVAILABLE_OTHER = "UNAVAILABLE_OTHER"
    ASSUMED_AVAILABLE_NO_REPORTED_ISSUE = "ASSUMED_AVAILABLE_NO_REPORTED_ISSUE"
    AVAILABILITY_UNVERIFIED = "AVAILABILITY_UNVERIFIED"
    UNKNOWN = "UNKNOWN"


class LineupMode(StrEnum):
    CONFIRMED = "CONFIRMED"
    PREDICTED_REPEAT_XI = "PREDICTED_REPEAT_XI"
    UNKNOWN = "UNKNOWN"


class LineupRole(StrEnum):
    STARTER = "STARTER"
    BENCH = "BENCH"


class PredictionConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SelectionReason(StrEnum):
    REPEATED_PREVIOUS_STARTER = "REPEATED_PREVIOUS_STARTER"
    MOST_USED_EXACT_POSITION_ALTERNATIVE = "MOST_USED_EXACT_POSITION_ALTERNATIVE"
    MOST_USED_POSITION_GROUP_ALTERNATIVE = "MOST_USED_POSITION_GROUP_ALTERNATIVE"
    AVAILABILITY_UNVERIFIED_REPEAT = "AVAILABILITY_UNVERIFIED_REPEAT"


UNAVAILABLE_STATES = frozenset(
    {
        AvailabilityState.UNAVAILABLE_INJURY,
        AvailabilityState.UNAVAILABLE_SUSPENSION,
        AvailabilityState.UNAVAILABLE_OTHER,
    }
)


@dataclass(frozen=True, slots=True)
class AvailabilityObservation:
    observation_id: UUID
    fixture_id: UUID
    team_id: UUID
    canonical_player_id: UUID | None
    provider_player_id: str
    availability_type: AvailabilityType
    availability_state: AvailabilityState
    reason: str | None
    observed_at: datetime
    known_at: datetime
    provider: str
    source_snapshot_id: UUID
    source_checksum: str


@dataclass(frozen=True, slots=True)
class LineupPlayer:
    canonical_player_id: UUID
    provider_player_id: str
    role: LineupRole
    position: str
    normalized_position: str
    grid_position: str | None


@dataclass(frozen=True, slots=True)
class LineupObservation:
    lineup_observation_id: UUID
    fixture_id: UUID
    team_id: UUID
    kickoff_at: datetime
    lineup_mode: LineupMode
    formation: str | None
    coach_id: UUID | None
    provider_coach_id: str | None
    observed_at: datetime
    known_at: datetime
    provider: str
    source_snapshot_id: UUID
    source_checksum: str
    players: tuple[LineupPlayer, ...]
    supersedes_predicted_lineup_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CoachObservation:
    coach_id: UUID
    team_id: UUID
    effective_at: datetime
    known_at: datetime


@dataclass(frozen=True, slots=True)
class PredictedStarter:
    player_id: UUID
    provider_player_id: str
    position: str
    normalized_position: str
    grid_position: str | None
    availability_state: AvailabilityState
    selection_reason: SelectionReason
    replaced_player_id: UUID | None = None
    replacement_reason: AvailabilityState | None = None
    preference_score: float | None = None
    historical_start_count: int | None = None


@dataclass(frozen=True, slots=True)
class UnresolvedSlot:
    replaced_player_id: UUID
    normalized_position: str
    grid_position: str | None
    slot_status: str = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class PredictedLineupV1:
    team_id: UUID
    target_kickoff: datetime
    knowledge_cutoff: datetime
    formation: str | None
    coach_id: UUID | None
    coach_context: str
    preference_sample_size: int
    confidence: PredictionConfidence
    starters: tuple[PredictedStarter, ...]
    unresolved_slots: tuple[UnresolvedSlot, ...]
    based_on_lineup_id: UUID


@dataclass(frozen=True, slots=True)
class LineupAccuracy:
    correct_starting_players: int
    xi_precision: float
    xi_recall: float
    formation_match: bool
    replacement_player_accuracy: float | None
    exact_position_replacement_accuracy: float | None
    coach_preference_sample_size: int
    prediction_confidence: PredictionConfidence


@dataclass(frozen=True, slots=True)
class RestContextV1:
    days_since_last_match: float | None
    matches_last_3_days: int
    matches_last_7_days: int
    matches_last_14_days: int
    matches_last_30_days: int
    days_to_next_match: float | None


@dataclass(frozen=True, slots=True)
class _Candidate:
    player: LineupPlayer
    preference_score: float
    compatible_start_count: int
    most_recent_compatible_start: int
    total_starts: int
    exact: bool


def predict_lineup(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    lineup_history: tuple[LineupObservation, ...],
    availability_history: tuple[AvailabilityObservation, ...],
    coach_history: tuple[CoachObservation, ...],
) -> PredictedLineupV1:
    """Repeat the latest eligible XI and deterministically replace known absences."""
    _require_aware(target_kickoff, "target_kickoff")
    _require_aware(knowledge_cutoff, "knowledge_cutoff")
    eligible = tuple(
        sorted(
            (
                lineup
                for lineup in lineup_history
                if lineup.team_id == team_id
                and lineup.lineup_mode is LineupMode.CONFIRMED
                and lineup.kickoff_at < target_kickoff
                and lineup.known_at <= knowledge_cutoff
            ),
            key=lambda item: (item.kickoff_at, str(item.lineup_observation_id)),
            reverse=True,
        )
    )
    if not eligible:
        raise ValueError("predicted lineup requires a prior confirmed lineup")
    coach_id = _current_coach(team_id, target_kickoff, knowledge_cutoff, coach_history)
    same_coach = tuple(
        item for item in eligible if coach_id is not None and item.coach_id == coach_id
    )
    fallback = not same_coach
    preference_history = (same_coach or eligible)[:COACH_PREFERENCE_WINDOW]
    base = preference_history[0]
    availability = _latest_availability(
        team_id, target_kickoff, knowledge_cutoff, availability_history
    )
    starters = tuple(player for player in base.players if player.role is LineupRole.STARTER)
    unavailable = {
        player.canonical_player_id: availability[player.canonical_player_id]
        for player in starters
        if availability.get(player.canonical_player_id) in UNAVAILABLE_STATES
    }
    selected_ids = {player.canonical_player_id for player in starters} - set(unavailable)
    resolved: dict[int, PredictedStarter] = {}
    unresolved: list[UnresolvedSlot] = []
    unverified_count = 0
    for index, player in enumerate(starters):
        if player.canonical_player_id in unavailable:
            continue
        state = availability.get(
            player.canonical_player_id, AvailabilityState.AVAILABILITY_UNVERIFIED
        )
        if state is AvailabilityState.AVAILABILITY_UNVERIFIED:
            unverified_count += 1
        resolved[index] = PredictedStarter(
            player.canonical_player_id,
            player.provider_player_id,
            player.position,
            player.normalized_position,
            player.grid_position,
            state,
            (
                SelectionReason.AVAILABILITY_UNVERIFIED_REPEAT
                if state is AvailabilityState.AVAILABILITY_UNVERIFIED
                else SelectionReason.REPEATED_PREVIOUS_STARTER
            ),
        )
    candidate_sets = {
        index: _ranked_candidates(
            player,
            preference_history,
            availability,
            selected_ids,
        )
        for index, player in enumerate(starters)
        if player.canonical_player_id in unavailable
    }
    broad_replacement = False
    for index in sorted(candidate_sets, key=lambda value: (len(candidate_sets[value]), value)):
        missing = starters[index]
        candidate = next(
            (
                item
                for item in candidate_sets[index]
                if item.player.canonical_player_id not in selected_ids
            ),
            None,
        )
        if candidate is None:
            unresolved.append(
                UnresolvedSlot(
                    missing.canonical_player_id,
                    missing.normalized_position,
                    missing.grid_position,
                )
            )
            continue
        selected_ids.add(candidate.player.canonical_player_id)
        broad_replacement = broad_replacement or not candidate.exact
        state = availability.get(
            candidate.player.canonical_player_id,
            AvailabilityState.AVAILABILITY_UNVERIFIED,
        )
        if state is AvailabilityState.AVAILABILITY_UNVERIFIED:
            unverified_count += 1
        resolved[index] = PredictedStarter(
            candidate.player.canonical_player_id,
            candidate.player.provider_player_id,
            candidate.player.position,
            missing.normalized_position,
            missing.grid_position,
            state,
            (
                SelectionReason.MOST_USED_EXACT_POSITION_ALTERNATIVE
                if candidate.exact
                else SelectionReason.MOST_USED_POSITION_GROUP_ALTERNATIVE
            ),
            missing.canonical_player_id,
            unavailable[missing.canonical_player_id],
            candidate.preference_score,
            candidate.compatible_start_count,
        )
    confidence = _confidence(
        coach_id,
        fallback,
        len(same_coach),
        len(unresolved),
        unverified_count,
        broad_replacement,
    )
    return PredictedLineupV1(
        team_id,
        target_kickoff,
        knowledge_cutoff,
        base.formation,
        coach_id,
        "UNKNOWN" if coach_id is None else "KNOWN",
        len(preference_history),
        confidence,
        tuple(resolved[index] for index in sorted(resolved)),
        tuple(unresolved),
        base.lineup_observation_id,
    )


def calculate_lineup_accuracy(
    predicted: PredictedLineupV1, confirmed: LineupObservation
) -> LineupAccuracy:
    predicted_ids = {item.player_id for item in predicted.starters}
    confirmed_ids = {
        item.canonical_player_id for item in confirmed.players if item.role is LineupRole.STARTER
    }
    correct = len(predicted_ids & confirmed_ids)
    replacements = [item for item in predicted.starters if item.replaced_player_id is not None]
    exact = [
        item
        for item in replacements
        if item.selection_reason is SelectionReason.MOST_USED_EXACT_POSITION_ALTERNATIVE
    ]
    return LineupAccuracy(
        correct,
        correct / len(predicted_ids) if predicted_ids else 0.0,
        correct / len(confirmed_ids) if confirmed_ids else 0.0,
        predicted.formation == confirmed.formation,
        _accuracy(replacements, confirmed_ids),
        _accuracy(exact, confirmed_ids),
        predicted.preference_sample_size,
        predicted.confidence,
    )


def rest_context(
    target_kickoff: datetime,
    prior_kickoffs: tuple[datetime, ...],
    known_future_kickoffs: tuple[datetime, ...] = (),
) -> RestContextV1:
    prior = tuple(value for value in prior_kickoffs if value < target_kickoff)
    future = tuple(value for value in known_future_kickoffs if value > target_kickoff)
    last = max(prior, default=None)
    next_match = min(future, default=None)
    return RestContextV1(
        _days(target_kickoff - last) if last else None,
        _count_since(prior, target_kickoff, 3),
        _count_since(prior, target_kickoff, 7),
        _count_since(prior, target_kickoff, 14),
        _count_since(prior, target_kickoff, 30),
        _days(next_match - target_kickoff) if next_match else None,
    )


def _current_coach(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    history: tuple[CoachObservation, ...],
) -> UUID | None:
    eligible = (
        item
        for item in history
        if item.team_id == team_id
        and item.effective_at < target_kickoff
        and item.known_at <= knowledge_cutoff
    )
    latest = max(eligible, key=lambda item: (item.effective_at, str(item.coach_id)), default=None)
    return latest.coach_id if latest else None


def _latest_availability(
    team_id: UUID,
    target_kickoff: datetime,
    knowledge_cutoff: datetime,
    history: tuple[AvailabilityObservation, ...],
) -> dict[UUID, AvailabilityState]:
    latest: dict[UUID, AvailabilityObservation] = {}
    for item in history:
        if (
            item.team_id != team_id
            or item.canonical_player_id is None
            or item.observed_at >= target_kickoff
            or item.known_at > knowledge_cutoff
        ):
            continue
        previous = latest.get(item.canonical_player_id)
        if previous is None or (item.known_at, item.observed_at, str(item.observation_id)) > (
            previous.known_at,
            previous.observed_at,
            str(previous.observation_id),
        ):
            latest[item.canonical_player_id] = item
    return {
        player_id: (
            item.availability_state
            if knowledge_cutoff - item.observed_at <= AVAILABILITY_FRESHNESS
            else AvailabilityState.AVAILABILITY_UNVERIFIED
        )
        for player_id, item in latest.items()
    }


def _ranked_candidates(
    missing: LineupPlayer,
    history: tuple[LineupObservation, ...],
    availability: dict[UUID, AvailabilityState],
    selected_ids: set[UUID],
) -> tuple[_Candidate, ...]:
    players: dict[UUID, LineupPlayer] = {}
    for lineup in history:
        for player in lineup.players:
            players.setdefault(player.canonical_player_id, player)
    eligible = {
        player_id: player
        for player_id, player in players.items()
        if player_id != missing.canonical_player_id
        and player_id not in selected_ids
        and availability.get(player_id) not in UNAVAILABLE_STATES
        and (
            _position_group(player.normalized_position)
            == _position_group(missing.normalized_position)
        )
    }
    exact_ids = {
        player_id
        for player_id, player in eligible.items()
        if _same_position(player.normalized_position, missing.normalized_position)
    }
    pool = exact_ids or set(eligible)
    return tuple(
        sorted(
            (
                _score_candidate(eligible[player_id], missing, history, bool(exact_ids))
                for player_id in pool
            ),
            key=lambda item: (
                -item.preference_score,
                -item.compatible_start_count,
                item.most_recent_compatible_start,
                -item.total_starts,
                str(item.player.canonical_player_id),
            ),
        )
    )


def _score_candidate(
    candidate: LineupPlayer,
    missing: LineupPlayer,
    history: tuple[LineupObservation, ...],
    exact: bool,
) -> _Candidate:
    score = 0.0
    compatible_count = 0
    most_recent = len(history) + 1
    total_starts = 0
    for index, lineup in enumerate(history):
        weight = 0.85**index
        for player in lineup.players:
            if player.canonical_player_id != candidate.canonical_player_id:
                continue
            if player.role is LineupRole.BENCH:
                score += 0.25 * weight
            else:
                total_starts += 1
                compatible = (
                    _same_position(player.normalized_position, missing.normalized_position)
                    if exact
                    else _position_group(player.normalized_position)
                    == _position_group(missing.normalized_position)
                )
                if compatible:
                    score += weight
                    compatible_count += 1
                    most_recent = min(most_recent, index)
    return _Candidate(candidate, score, compatible_count, most_recent, total_starts, exact)


def _confidence(
    coach_id: UUID | None,
    fallback: bool,
    sample_size: int,
    unresolved: int,
    unverified: int,
    broad: bool,
) -> PredictionConfidence:
    if coach_id is None or fallback or sample_size < 2 or unresolved or unverified > 1:
        return PredictionConfidence.LOW
    if sample_size >= 5 and unverified == 0 and not broad:
        return PredictionConfidence.HIGH
    return PredictionConfidence.MEDIUM


def _position_group(position: str) -> str:
    normalized = position.upper().replace("CF", "ST")
    groups = {
        "GK": "GK",
        "CB": "DEF",
        "LB": "DEF",
        "RB": "DEF",
        "LWB": "DEF",
        "RWB": "DEF",
        "DEF": "DEF",
        "DM": "MID",
        "CM": "MID",
        "AM": "MID",
        "MID": "MID",
        "LW": "FWD",
        "RW": "FWD",
        "ST": "FWD",
        "FWD": "FWD",
    }
    return groups.get(normalized, normalized)


def _same_position(first: str, second: str) -> bool:
    return first.upper().replace("CF", "ST") == second.upper().replace("CF", "ST")


def _accuracy(predicted: list[PredictedStarter], confirmed: set[UUID]) -> float | None:
    if not predicted:
        return None
    return sum(item.player_id in confirmed for item in predicted) / len(predicted)


def _count_since(values: tuple[datetime, ...], target: datetime, days: int) -> int:
    boundary = target - timedelta(days=days)
    return sum(boundary <= value < target for value in values)


def _days(value: timedelta) -> float:
    return value.total_seconds() / 86_400


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
