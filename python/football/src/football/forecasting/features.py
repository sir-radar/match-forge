"""Provider-neutral feature snapshots built only from already eligible inputs."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.model_contracts import ForecastInputSnapshot

FEATURE_CONTRACT_VERSION = "fixture-features-v1"
_UNSUPPORTED = (
    "league_strength",
    "home_advantage",
    "tactical_context",
    "corners_context",
    "cards_context",
    "player_context",
)
_TARGET_OUTCOMES = frozenset(
    (
        "home_score",
        "away_score",
        "home_goals",
        "away_goals",
        "result",
        "score",
        "corners",
        "shots",
        "possession",
        "post_match_statistics",
    )
)


@dataclass(frozen=True, slots=True, init=False)
class FixtureFeatureSnapshotV1:
    """Immutable export plus defensive projections for existing model interfaces.

    The feature snapshot hash binds its complete metadata. The model projection
    retains the existing predictive-input hash and approved feature semantics.
    """

    _model_input: ForecastInputSnapshot
    _canonical: bytes

    def __init__(
        self,
        model_input: ForecastInputSnapshot,
        *,
        quality: tuple[str, ...] | None = None,
        feature_contract_version: str = FEATURE_CONTRACT_VERSION,
    ) -> None:
        if feature_contract_version != FEATURE_CONTRACT_VERSION:
            raise ValueError("unsupported fixture feature contract version")
        if quality is not None and (
            not isinstance(quality, tuple)
            or any(not isinstance(code, str) or not code.strip() for code in quality)
        ):
            raise ValueError("feature quality requires explicit nonempty finding codes")
        sealed = copy.deepcopy(model_input)
        _validate_history(sealed)
        _validate_context(sealed)
        payload = _payload(sealed, quality)
        object.__setattr__(self, "_model_input", sealed)
        object.__setattr__(self, "_canonical", canonical_json_bytes(payload))

    @property
    def model_input(self) -> ForecastInputSnapshot:
        return copy.deepcopy(self._model_input)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self._canonical).hexdigest()

    @property
    def feature_contract_version(self) -> str:
        return FEATURE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._canonical))


def _validate_history(snapshot: ForecastInputSnapshot) -> None:
    _validate_identity(
        snapshot.fixture_id, snapshot.competition_id, snapshot.home_team_id, snapshot.away_team_id
    )
    for value in (snapshot.kickoff_at, snapshot.football_cutoff, snapshot.knowledge_cutoff):
        if value.utcoffset() is None:
            raise ValueError("feature cutoffs require timezones")
    if snapshot.football_cutoff > snapshot.kickoff_at or not snapshot.knowledge_mode:
        raise ValueError("feature football cutoff or knowledge mode is invalid")
    seen = {snapshot.fixture_id}
    for row in snapshot.qualified_history:
        _validate_identity(row.fixture_id, row.competition_id, row.home_team_id, row.away_team_id)
        if row.fixture_id in seen:
            raise ValueError("feature history contains the target or a duplicate fixture")
        if row.kickoff_at >= snapshot.football_cutoff or row.known_at > snapshot.knowledge_cutoff:
            raise ValueError("feature history violates football or knowledge cutoff")
        seen.add(row.fixture_id)


def _validate_identity(fixture: UUID, competition: UUID, home: UUID, away: UUID) -> None:
    if any(not isinstance(identity, UUID) for identity in (fixture, competition, home, away)):
        raise ValueError("feature identities require MatchForge UUIDs")
    if home == away:
        raise ValueError("feature fixture teams must differ")


def _validate_context_value(value: object, knowledge_cutoff: datetime) -> None:
    if isinstance(value, dict):
        if _TARGET_OUTCOMES.intersection(value):
            raise ValueError("pre-match context contains target outcome fields")
        if "known_at" in value:
            _validate_known_at(value["known_at"], knowledge_cutoff)
        for nested in value.values():
            _validate_context_value(nested, knowledge_cutoff)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _validate_context_value(nested, knowledge_cutoff)


def _validate_known_at(value: object, knowledge_cutoff: datetime) -> None:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None or value > knowledge_cutoff:
        raise ValueError("context knowledge time is missing, naive or follows the feature cutoff")


def _validate_context(snapshot: ForecastInputSnapshot) -> None:
    contexts = (
        snapshot.availability,
        snapshot.predicted_lineup,
        snapshot.confirmed_lineup,
        snapshot.coach_context,
        snapshot.travel_context,
        snapshot.rest_context,
    )
    for context in contexts:
        _validate_context_value(context, snapshot.knowledge_cutoff)
    if any(context for context in contexts) and not snapshot.context_provenance:
        raise ValueError("external feature context requires point-in-time provenance")
    for reference in snapshot.context_provenance:
        if (
            not isinstance(reference.get("source_reference"), str)
            or not reference["source_reference"]
            or "known_at" not in reference
        ):
            raise ValueError("context provenance requires source_reference and known_at")
        _validate_context_value(reference, snapshot.knowledge_cutoff)


def _payload(snapshot: ForecastInputSnapshot, quality: tuple[str, ...] | None) -> dict[str, object]:
    source = snapshot.to_dict()
    fixture_fields = (
        "fixture_id",
        "competition_id",
        "competition_context",
        "season_label",
        "kickoff_at",
        "home_team_id",
        "away_team_id",
    )
    lineup = (
        {"predicted": source["predicted_lineup"], "confirmed": source["confirmed_lineup"]}
        if snapshot.predicted_lineup is not None or snapshot.confirmed_lineup is not None
        else None
    )
    availability = (
        {"status": snapshot.availability_status, "observations": source["availability"]}
        if snapshot.availability or snapshot.availability_status != "UNKNOWN"
        else None
    )
    resources: dict[str, object] = {
        "travel": source["travel_context"],
        "manager_context": source["coach_context"],
        "lineup_context": lineup,
        "availability_context": availability,
        **{family: None for family in _UNSUPPORTED},
    }
    missingness = sorted(
        set(snapshot.missingness + snapshot.context_missingness)
        .union(family for family, value in resources.items() if value is None)
        .union(("quality",) if quality is None else ())
        .union(
            ("provenance",)
            if not snapshot.source_references and not snapshot.context_provenance
            else ()
        )
    )
    return {
        "contract": "FixtureFeatureSnapshotV1",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "fixture": {name: source[name] for name in fixture_fields},
        "football_cutoff": source["football_cutoff"],
        "knowledge_cutoff": source["knowledge_cutoff"],
        "knowledge_mode": snapshot.knowledge_mode,
        "goals_history": source["qualified_history"],
        "team_strength": {
            "home": None
            if "HOME_RATING_UNAVAILABLE" in snapshot.missingness
            else snapshot.rating.home_rating,
            "away": None
            if "AWAY_RATING_UNAVAILABLE" in snapshot.missingness
            else snapshot.rating.away_rating,
        },
        "rest": {
            "home": source["home_rest"],
            "away": source["away_rest"],
            "context": source["rest_context"],
        },
        "congestion": {
            "home_last_7_days": snapshot.home_rest.matches_last_7_days,
            "home_last_14_days": snapshot.home_rest.matches_last_14_days,
            "away_last_7_days": snapshot.away_rest.matches_last_7_days,
            "away_last_14_days": snapshot.away_rest.matches_last_14_days,
        },
        **resources,
        "missingness": missingness,
        "quality": quality,
        "provenance": {
            "source_references": source["source_references"],
            "context": source["context_provenance"],
        },
        "model_input_sha256": snapshot.sha256,
        "model_input": source,
    }
