"""Point-in-time contracts for historical context corpus qualification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from football.context.contextual_features import (
    QualifiedVenue,
    TeamMatch,
    manager_features,
    rest_congestion_features,
    travel_features,
)
from football.context.live import (
    AvailabilityObservation,
    CoachObservation,
    LineupAccuracy,
    LineupObservation,
    PredictedLineupV1,
    calculate_lineup_accuracy,
    predict_lineup,
)


class AvailabilityEvidenceTier(StrEnum):
    TIER_A_POINT_IN_TIME = "TIER_A_POINT_IN_TIME"
    TIER_B_RETROSPECTIVE = "TIER_B_RETROSPECTIVE"
    UNAVAILABLE = "UNAVAILABLE"


class PointInTimeReconstructionStatus(StrEnum):
    POINT_IN_TIME_VERIFIED = "POINT_IN_TIME_VERIFIED"
    RETROSPECTIVE_CONTEXT_ONLY = "RETROSPECTIVE_CONTEXT_ONLY"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


class VenueCoordinateSource(StrEnum):
    PROVIDER_STRUCTURED = "PROVIDER_STRUCTURED"
    MATCHFORGE_VERIFIED = "MATCHFORGE_VERIFIED"
    TRUSTED_DETERMINISTIC_MAPPING = "TRUSTED_DETERMINISTIC_MAPPING"


@dataclass(frozen=True, slots=True)
class HistoricalAvailabilityEvidence:
    observation: AvailabilityObservation
    tier: AvailabilityEvidenceTier


@dataclass(frozen=True, slots=True)
class VenueIdentityV1:
    venue_id: str
    provider_venue_ids: tuple[tuple[str, str], ...]
    canonical_name: str
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    coordinate_source: VenueCoordinateSource
    confidence: str
    timezone: str
    ambiguous: bool = False

    @property
    def qualified(self) -> bool:
        return (
            not self.ambiguous
            and self.latitude is not None
            and self.longitude is not None
            and self.confidence in {"VERIFIED", "HIGH"}
        )

    def as_qualified_venue(self) -> QualifiedVenue:
        if not self.qualified or self.latitude is None or self.longitude is None:
            raise ValueError("venue coordinates are not qualified")
        return QualifiedVenue(self.latitude, self.longitude, self.timezone, True)


@dataclass(frozen=True, slots=True)
class HistoricalTargetV1:
    fixture_id: UUID
    kickoff_at: datetime
    knowledge_cutoff: datetime
    competition: str
    season: str
    home_team_id: UUID
    away_team_id: UUID
    source_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoricalContextInputs:
    lineup_history: tuple[LineupObservation, ...]
    availability_history: tuple[HistoricalAvailabilityEvidence, ...]
    coach_history: tuple[CoachObservation, ...]
    team_matches: tuple[TeamMatch, ...]
    home_team_venue: VenueIdentityV1 | None = None
    away_team_venue: VenueIdentityV1 | None = None
    match_venue: VenueIdentityV1 | None = None
    neutral_venue: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalContextSnapshotV1:
    fixture_id: UUID
    football_cutoff: datetime
    knowledge_cutoff: datetime
    predicted_home_lineup: PredictedLineupV1 | None
    predicted_away_lineup: PredictedLineupV1 | None
    availability_observations: tuple[dict[str, object], ...]
    coach_context: dict[str, dict[str, float | None]]
    rest_context: dict[str, dict[str, float | None]]
    venue_context: dict[str, object]
    travel_context: dict[str, dict[str, float]]
    missingness: tuple[str, ...]
    provenance: tuple[str, ...]
    status: PointInTimeReconstructionStatus
    snapshot_sha256: str

    def semantic_payload(self) -> dict[str, object]:
        return {
            "contract": "HistoricalContextSnapshotV1",
            "fixture_id": str(self.fixture_id),
            "football_cutoff": self.football_cutoff.isoformat(),
            "knowledge_cutoff": self.knowledge_cutoff.isoformat(),
            "predicted_home_lineup": _json_value(self.predicted_home_lineup),
            "predicted_away_lineup": _json_value(self.predicted_away_lineup),
            "availability_observations": _json_value(self.availability_observations),
            "coach_context": self.coach_context,
            "rest_context": self.rest_context,
            "venue_context": self.venue_context,
            "travel_context": self.travel_context,
            "missingness": list(self.missingness),
            "provenance": list(self.provenance),
            "status": self.status.value,
        }

    def to_payload(self) -> dict[str, object]:
        return {**self.semantic_payload(), "snapshot_sha256": self.snapshot_sha256}


@dataclass(frozen=True, slots=True)
class ConfirmedLineupLabelV1:
    fixture_id: UUID
    home: LineupObservation
    away: LineupObservation
    source_references: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineupLabelScoreV1:
    home: LineupAccuracy | None
    away: LineupAccuracy | None


@dataclass(frozen=True, slots=True)
class TargetCandidate:
    fixture_id: UUID
    real_fixture_key: str


@dataclass(frozen=True, slots=True)
class TargetFirewallResult:
    targets: tuple[TargetCandidate, ...]
    forbidden_target_count: int
    duplicate_real_fixture_count: int
    historical_fixture_ids: tuple[UUID, ...]
    forbidden_overlap: int


def qualify_availability_evidence(
    *,
    observed_at: datetime,
    known_at: datetime,
    target_kickoff: datetime,
    retrospective: bool,
) -> AvailabilityEvidenceTier:
    """Classify evidence without treating after-the-fact acquisition as pre-match knowledge."""
    if retrospective and observed_at < target_kickoff:
        return AvailabilityEvidenceTier.TIER_B_RETROSPECTIVE
    if observed_at < target_kickoff and known_at < target_kickoff:
        return AvailabilityEvidenceTier.TIER_A_POINT_IN_TIME
    return AvailabilityEvidenceTier.UNAVAILABLE


def filter_context_targets(
    targets: tuple[TargetCandidate, ...],
    forbidden_ids: frozenset[UUID],
    *,
    historical_fixture_ids: tuple[UUID, ...] = (),
) -> TargetFirewallResult:
    """Apply the firewall to targets while retaining prior-history identifiers."""
    seen_real: set[str] = set()
    accepted: list[TargetCandidate] = []
    forbidden_count = 0
    duplicate_count = 0
    for target in targets:
        if target.fixture_id in forbidden_ids:
            forbidden_count += 1
            continue
        if target.real_fixture_key in seen_real:
            duplicate_count += 1
            continue
        seen_real.add(target.real_fixture_key)
        accepted.append(target)
    overlap = len({item.fixture_id for item in accepted} & forbidden_ids)
    return TargetFirewallResult(
        tuple(accepted),
        forbidden_count,
        duplicate_count,
        historical_fixture_ids,
        overlap,
    )


def build_phase_a_snapshot(
    target: HistoricalTargetV1,
    inputs: HistoricalContextInputs,
) -> HistoricalContextSnapshotV1:
    """Build and hash predictive context without accepting a target lineup or outcome."""
    tier_a = tuple(
        item.observation
        for item in inputs.availability_history
        if item.tier is AvailabilityEvidenceTier.TIER_A_POINT_IN_TIME
    )
    home_prediction = _predict_if_possible(target, target.home_team_id, inputs, tier_a)
    away_prediction = _predict_if_possible(target, target.away_team_id, inputs, tier_a)
    rest = {
        "home": rest_congestion_features(
            target.home_team_id,
            target.kickoff_at,
            target.knowledge_cutoff,
            inputs.team_matches,
        ),
        "away": rest_congestion_features(
            target.away_team_id,
            target.kickoff_at,
            target.knowledge_cutoff,
            inputs.team_matches,
        ),
    }
    coaches = {
        "home": manager_features(
            target.home_team_id,
            target.kickoff_at,
            target.knowledge_cutoff,
            inputs.team_matches,
            inputs.coach_history,
        ),
        "away": manager_features(
            target.away_team_id,
            target.kickoff_at,
            target.knowledge_cutoff,
            inputs.team_matches,
            inputs.coach_history,
        ),
    }
    travel = _travel_context(target, inputs)
    missingness = _missingness(home_prediction, away_prediction, coaches, travel)
    availability: tuple[dict[str, object], ...] = tuple(
        {
            "observation_id": str(item.observation.observation_id),
            "team_id": str(item.observation.team_id),
            "player_id": (
                str(item.observation.canonical_player_id)
                if item.observation.canonical_player_id
                else None
            ),
            "state": item.observation.availability_state.value,
            "tier": item.tier.value,
            "source_snapshot_id": str(item.observation.source_snapshot_id),
        }
        for item in inputs.availability_history
        if item.tier is AvailabilityEvidenceTier.TIER_A_POINT_IN_TIME
        and item.observation.observed_at < target.kickoff_at
        and item.observation.known_at <= target.knowledge_cutoff
    )
    status = _snapshot_status(
        rest,
        availability,
        inputs.availability_history,
        home_prediction,
        away_prediction,
    )
    values: dict[str, Any] = {
        "fixture_id": target.fixture_id,
        "football_cutoff": target.knowledge_cutoff,
        "knowledge_cutoff": target.knowledge_cutoff,
        "predicted_home_lineup": home_prediction,
        "predicted_away_lineup": away_prediction,
        "availability_observations": availability,
        "coach_context": coaches,
        "rest_context": rest,
        "venue_context": _venue_context(inputs),
        "travel_context": travel,
        "missingness": missingness,
        "provenance": target.source_references,
        "status": status,
    }
    provisional = HistoricalContextSnapshotV1(**values, snapshot_sha256="")
    return HistoricalContextSnapshotV1(
        **values,
        snapshot_sha256=canonical_sha256(provisional.semantic_payload()),
    )


def score_phase_b_lineup_label(
    snapshot: HistoricalContextSnapshotV1,
    label: ConfirmedLineupLabelV1,
) -> LineupLabelScoreV1:
    """Load confirmed-XI truth only after the Phase A snapshot is frozen."""
    if canonical_sha256(snapshot.semantic_payload()) != snapshot.snapshot_sha256:
        raise ValueError("historical context snapshot is not frozen")
    if label.fixture_id != snapshot.fixture_id:
        raise ValueError("confirmed lineup label fixture does not match snapshot fixture")
    home = (
        calculate_lineup_accuracy(snapshot.predicted_home_lineup, label.home)
        if snapshot.predicted_home_lineup is not None
        else None
    )
    away = (
        calculate_lineup_accuracy(snapshot.predicted_away_lineup, label.away)
        if snapshot.predicted_away_lineup is not None
        else None
    )
    return LineupLabelScoreV1(home, away)


def canonical_sha256(value: object) -> str:
    payload = json.dumps(_json_value(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _predict_if_possible(
    target: HistoricalTargetV1,
    team_id: UUID,
    inputs: HistoricalContextInputs,
    tier_a: tuple[AvailabilityObservation, ...],
) -> PredictedLineupV1 | None:
    try:
        return predict_lineup(
            team_id,
            target.kickoff_at,
            target.knowledge_cutoff,
            inputs.lineup_history,
            tier_a,
            inputs.coach_history,
        )
    except ValueError as error:
        if str(error) != "predicted lineup requires a prior confirmed lineup":
            raise
        return None


def _travel_context(
    target: HistoricalTargetV1, inputs: HistoricalContextInputs
) -> dict[str, dict[str, float]]:
    if inputs.match_venue is None or not inputs.match_venue.qualified:
        return {}
    result: dict[str, dict[str, float]] = {}
    for label, venue in (
        ("home", inputs.home_team_venue),
        ("away", inputs.away_team_venue),
    ):
        if venue is not None and venue.qualified:
            result[label] = travel_features(
                venue.as_qualified_venue(),
                inputs.match_venue.as_qualified_venue(),
                neutral_venue=inputs.neutral_venue,
                kickoff_at=target.kickoff_at,
            )
    return result


def _venue_context(inputs: HistoricalContextInputs) -> dict[str, object]:
    return {
        "home_team_venue_id": inputs.home_team_venue.venue_id if inputs.home_team_venue else None,
        "away_team_venue_id": inputs.away_team_venue.venue_id if inputs.away_team_venue else None,
        "match_venue_id": inputs.match_venue.venue_id if inputs.match_venue else None,
        "neutral_venue": inputs.neutral_venue,
    }


def _missingness(
    home_prediction: PredictedLineupV1 | None,
    away_prediction: PredictedLineupV1 | None,
    coaches: dict[str, dict[str, float | None]],
    travel: dict[str, dict[str, float]],
) -> tuple[str, ...]:
    missing: list[str] = []
    if home_prediction is None or away_prediction is None:
        missing.append("LINEUP")
    if any(values["matches_under_coach"] is None for values in coaches.values()):
        missing.append("MANAGER")
    if len(travel) != 2:
        missing.append("TRAVEL")
    return tuple(missing)


def _snapshot_status(
    rest: dict[str, dict[str, float | None]],
    availability: tuple[dict[str, object], ...],
    evidence: tuple[HistoricalAvailabilityEvidence, ...],
    home_prediction: PredictedLineupV1 | None,
    away_prediction: PredictedLineupV1 | None,
) -> PointInTimeReconstructionStatus:
    if (
        availability
        or home_prediction is not None
        or away_prediction is not None
        or any(values["days_since_last_match"] is not None for values in rest.values())
    ):
        return PointInTimeReconstructionStatus.POINT_IN_TIME_VERIFIED
    if any(item.tier is AvailabilityEvidenceTier.TIER_B_RETROSPECTIVE for item in evidence):
        return PointInTimeReconstructionStatus.RETROSPECTIVE_CONTEXT_ONLY
    return PointInTimeReconstructionStatus.INSUFFICIENT_CONTEXT


def _json_value(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    return value
