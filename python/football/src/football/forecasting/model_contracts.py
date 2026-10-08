from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

PROBABILITY_TOLERANCE = 1e-10


class ModelStatus(StrEnum):
    SUCCESS = "SUCCESS"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSEEN_TEAM = "UNSEEN_TEAM"
    MODEL_FIT_UNAVAILABLE = "MODEL_FIT_UNAVAILABLE"
    MODEL_ERROR = "MODEL_ERROR"
    INVALID_DISTRIBUTION = "INVALID_DISTRIBUTION"


class ModelRole(StrEnum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    RESEARCH = "RESEARCH"
    EXTERNAL_BENCHMARK = "EXTERNAL_BENCHMARK"


class ForecastMode(StrEnum):
    NATIVE = "NATIVE"
    COLD_START_HOME = "COLD_START_HOME"
    COLD_START_AWAY = "COLD_START_AWAY"
    COLD_START_BOTH = "COLD_START_BOTH"
    CHAMPION_FALLBACK = "CHAMPION_FALLBACK"


class ForecastFallbackReason(StrEnum):
    NONE = "NONE"
    HOME_UNSEEN = "HOME_UNSEEN"
    AWAY_UNSEEN = "AWAY_UNSEEN"
    BOTH_UNSEEN = "BOTH_UNSEEN"
    HOME_INSUFFICIENT_HISTORY = "HOME_INSUFFICIENT_HISTORY"
    AWAY_INSUFFICIENT_HISTORY = "AWAY_INSUFFICIENT_HISTORY"
    BOTH_INSUFFICIENT_HISTORY = "BOTH_INSUFFICIENT_HISTORY"
    COLD_START_UNAVAILABLE = "COLD_START_UNAVAILABLE"
    MODEL_FIT_UNAVAILABLE = "MODEL_FIT_UNAVAILABLE"
    MODEL_ERROR = "MODEL_ERROR"
    INVALID_DISTRIBUTION = "INVALID_DISTRIBUTION"


@dataclass(frozen=True, slots=True)
class ForecastLineage:
    forecast_mode: ForecastMode
    primary_model_id: str
    primary_model_artifact_sha256: str
    fallback_model_id: str | None
    fallback_model_artifact_sha256: str | None
    fallback_reason: ForecastFallbackReason
    home_artifact_state: str
    away_artifact_state: str
    home_history_state: str
    away_history_state: str
    home_promoted: bool | None
    away_promoted: bool | None
    native_component_used: bool
    cold_start_component_used: bool
    champion_fallback_used: bool
    ensemble_mode: str | None = None


class CompetitionContext(StrEnum):
    LEAGUE = "LEAGUE"
    DOMESTIC_CUP = "DOMESTIC_CUP"
    CONTINENTAL_CUP = "CONTINENTAL_CUP"
    INTERNATIONAL = "INTERNATIONAL"
    FRIENDLY = "FRIENDLY"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class HistoricalMatch:
    fixture_id: UUID
    competition_id: UUID
    competition_context: CompetitionContext
    kickoff_at: datetime
    known_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_goals: int
    away_goals: int
    home_xg: float | None = None
    away_xg: float | None = None

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "kickoff_at")
        _aware(self.known_at, "known_at")
        if self.home_team_id == self.away_team_id:
            raise ValueError("historical match teams must differ")
        for name, value in (("home_goals", self.home_goals), ("away_goals", self.away_goals)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, xg_value in (("home_xg", self.home_xg), ("away_xg", self.away_xg)):
            if xg_value is not None and (not math.isfinite(xg_value) or xg_value < 0):
                raise ValueError(f"{name} must be finite and non-negative when present")


@dataclass(frozen=True, slots=True)
class FormWindow:
    match_count: int
    goals_for: float | None
    goals_against: float | None
    xg_for: float | None
    xg_against: float | None
    goal_difference: float | None
    xg_difference: float | None
    points_per_match: float | None
    clean_sheet_rate: float | None
    failed_to_score_rate: float | None
    xg_sample_count: int
    opponent_adjusted_points: float | None


@dataclass(frozen=True, slots=True)
class RestContext:
    days_since_last_match: float | None
    matches_last_7_days: int
    matches_last_14_days: int


@dataclass(frozen=True, slots=True)
class RatingContext:
    home_rating: float
    away_rating: float
    rating_difference: float
    rating_expected_home: float


@dataclass(frozen=True, slots=True)
class H2HContext:
    competition_context: CompetitionContext
    sample_size: int
    effective_sample_size: float
    home_team_win_rate: float | None
    draw_rate: float | None
    away_team_win_rate: float | None
    goals_for_mean: float | None
    goals_against_mean: float | None
    goal_difference_mean: float | None
    xg_for_mean: float | None
    xg_against_mean: float | None
    most_recent_at: datetime | None


@dataclass(frozen=True, slots=True)
class ForecastInputSnapshot:
    fixture_id: UUID
    competition_id: UUID
    competition_context: CompetitionContext
    season_label: str
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    football_cutoff: datetime
    knowledge_cutoff: datetime
    knowledge_mode: str
    qualified_history: tuple[HistoricalMatch, ...]
    home_form_5: FormWindow
    home_form_10: FormWindow
    away_form_5: FormWindow
    away_form_10: FormWindow
    home_home_form_10: FormWindow
    away_away_form_10: FormWindow
    home_league_form_10: FormWindow
    away_league_form_10: FormWindow
    rating: RatingContext
    home_rest: RestContext
    away_rest: RestContext
    h2h: tuple[H2HContext, ...]
    availability_status: str = "UNKNOWN"
    source_references: tuple[str, ...] = ()
    missingness: tuple[str, ...] = ()
    home_promoted: bool | None = None
    away_promoted: bool | None = None
    availability: tuple[dict[str, object], ...] = ()
    predicted_lineup: dict[str, object] | None = None
    confirmed_lineup: dict[str, object] | None = None
    coach_context: dict[str, object] | None = None
    rest_context: dict[str, object] | None = None
    context_missingness: tuple[str, ...] = ()
    context_provenance: tuple[dict[str, object], ...] = ()
    travel_context: dict[str, object] | None = None
    predictive_context_families: tuple[str, ...] = ()

    @property
    def sha256(self) -> str:
        return self.predictive_input_snapshot_sha256

    @property
    def predictive_input_snapshot_sha256(self) -> str:
        payload = self.to_dict()
        active = tuple(cast(list[str], payload.pop("predictive_context_families")))
        predictive_context: dict[str, object] = {}
        for field_name in _NON_PREDICTIVE_CONTEXT_FIELDS:
            value = payload.pop(field_name)
            if field_name in _predictive_fields(active):
                predictive_context[field_name] = value
        if predictive_context:
            payload["predictive_context"] = predictive_context
            payload["predictive_context_families"] = sorted(active)
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    @property
    def context_snapshot_sha256(self) -> str:
        payload = self.to_dict()
        return hashlib.sha256(
            _canonical_json({name: payload[name] for name in _NON_PREDICTIVE_CONTEXT_FIELDS})
        ).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return _json_value(self)  # type: ignore[return-value]


_NON_PREDICTIVE_CONTEXT_FIELDS = (
    "availability",
    "predicted_lineup",
    "confirmed_lineup",
    "coach_context",
    "rest_context",
    "context_missingness",
    "context_provenance",
    "travel_context",
)


def _predictive_fields(families: tuple[str, ...]) -> frozenset[str]:
    allowed = {
        "AVAILABILITY_LINEUP": frozenset(("availability", "predicted_lineup", "confirmed_lineup")),
        "REST_CONGESTION": frozenset(("rest_context",)),
        "MANAGER": frozenset(("coach_context",)),
        "TRAVEL": frozenset(("travel_context",)),
    }
    unknown = set(families).difference(allowed)
    if unknown:
        raise ValueError("unknown predictive context families: " + ", ".join(sorted(unknown)))
    return frozenset(field for family in families for field in allowed[family])


@dataclass(frozen=True, slots=True)
class FittedModelArtifact:
    model_id: str
    model_family: str
    model_version: str
    artifact_sha256: str
    training_start: datetime
    training_cutoff: datetime
    dataset_sha256: str
    configuration: dict[str, object]
    dependency_version: str
    code_commit_sha: str
    feature_contract: str
    random_seed: int | None
    runtime_model: object = field(repr=False, compare=False)
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelForecast:
    fixture_id: UUID
    model_id: str
    model_family: str
    model_version: str
    model_artifact_sha256: str
    football_cutoff: datetime
    knowledge_cutoff: datetime
    created_at: datetime
    expected_home_goals: float
    expected_away_goals: float
    home_probability: float
    draw_probability: float
    away_probability: float
    score_labels: tuple[str, ...]
    score_matrix: tuple[tuple[float, ...], ...]
    home_goal_distribution: tuple[float, ...]
    away_goal_distribution: tuple[float, ...]
    total_goal_distribution: tuple[float, ...]
    btts_yes: float
    btts_no: float
    total_over_2_5: float
    total_under_2_5: float
    home_clean_sheet: float
    away_clean_sheet: float
    status: ModelStatus
    warnings: tuple[str, ...]
    input_snapshot_sha256: str
    component_weights: tuple[tuple[str, float], ...] = ()
    lineage: ForecastLineage | None = None

    def __post_init__(self) -> None:
        if self.status is ModelStatus.SUCCESS:
            validate_model_forecast(self)


@dataclass(frozen=True, slots=True)
class ModelAvailability:
    model_id: str
    status: ModelStatus
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelRunResult:
    forecasts: tuple[ModelForecast, ...]
    availability: tuple[ModelAvailability, ...]


class ForecastModel(Protocol):
    model_id: str
    model_family: str
    model_version: str
    role: ModelRole
    supports_unseen_teams: bool
    requires_xg: bool

    def fit(
        self, training_data: tuple[HistoricalMatch, ...], config: dict[str, object]
    ) -> FittedModelArtifact: ...

    def predict(
        self, artifact: FittedModelArtifact, fixture: ForecastInputSnapshot
    ) -> ModelForecast: ...


def validate_model_forecast(forecast: ModelForecast) -> None:
    _aware(forecast.football_cutoff, "football_cutoff")
    _aware(forecast.knowledge_cutoff, "knowledge_cutoff")
    _aware(forecast.created_at, "created_at")
    for name, value in (
        ("expected_home_goals", forecast.expected_home_goals),
        ("expected_away_goals", forecast.expected_away_goals),
    ):
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and non-negative")
    size = len(forecast.score_labels)
    if (
        size < 2
        or len(forecast.score_matrix) != size
        or any(len(row) != size for row in forecast.score_matrix)
    ):
        raise ValueError("score matrix must be square and match score labels")
    cells = tuple(value for row in forecast.score_matrix for value in row)
    _probabilities(cells, "score matrix")
    if not math.isclose(sum(cells), 1.0, abs_tol=PROBABILITY_TOLERANCE):
        raise ValueError("score matrix must sum to one")
    derived_home, derived_away, derived_total = distributions(forecast.score_matrix)
    _validate_derived_distributions(forecast, derived_home, derived_away, derived_total)
    _validate_expected_goals(forecast, derived_home, derived_away)
    derived = derive_markets(forecast.score_matrix)
    expected = {
        "home_probability": forecast.home_probability,
        "draw_probability": forecast.draw_probability,
        "away_probability": forecast.away_probability,
        "btts_yes": forecast.btts_yes,
        "btts_no": forecast.btts_no,
        "total_over_2_5": forecast.total_over_2_5,
        "total_under_2_5": forecast.total_under_2_5,
        "home_clean_sheet": forecast.home_clean_sheet,
        "away_clean_sheet": forecast.away_clean_sheet,
    }
    for name, value in expected.items():
        if not math.isclose(value, derived[name], abs_tol=PROBABILITY_TOLERANCE):
            raise ValueError(f"{name} is inconsistent with score matrix")


def _validate_derived_distributions(
    forecast: ModelForecast,
    derived_home: tuple[float, ...],
    derived_away: tuple[float, ...],
    derived_total: tuple[float, ...],
) -> None:
    for name, provided, calculated in (
        ("home_goal_distribution", forecast.home_goal_distribution, derived_home),
        ("away_goal_distribution", forecast.away_goal_distribution, derived_away),
        ("total_goal_distribution", forecast.total_goal_distribution, derived_total),
    ):
        _probabilities(provided, name)
        if not math.isclose(sum(provided), 1.0, abs_tol=PROBABILITY_TOLERANCE):
            raise ValueError(f"{name} must sum to one")
        if len(provided) != len(calculated) or any(
            not math.isclose(left, right, abs_tol=PROBABILITY_TOLERANCE)
            for left, right in zip(provided, calculated, strict=True)
        ):
            raise ValueError(f"{name} is inconsistent with score matrix")


def _validate_expected_goals(
    forecast: ModelForecast,
    derived_home: tuple[float, ...],
    derived_away: tuple[float, ...],
) -> None:
    for name, provided, calculated in (
        (
            "expected_home_goals",
            forecast.expected_home_goals,
            sum(index * value for index, value in enumerate(derived_home)),
        ),
        (
            "expected_away_goals",
            forecast.expected_away_goals,
            sum(index * value for index, value in enumerate(derived_away)),
        ),
    ):
        if not math.isclose(provided, calculated, abs_tol=PROBABILITY_TOLERANCE):
            raise ValueError(f"{name} is inconsistent with score matrix")


def derive_markets(matrix: tuple[tuple[float, ...], ...]) -> dict[str, float]:
    home = draw = away = btts = over = home_clean = away_clean = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                home += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away += probability
            btts += probability if home_goals > 0 and away_goals > 0 else 0.0
            over += probability if home_goals + away_goals >= 3 else 0.0
            home_clean += probability if away_goals == 0 else 0.0
            away_clean += probability if home_goals == 0 else 0.0
    return {
        "home_probability": home,
        "draw_probability": draw,
        "away_probability": away,
        "btts_yes": btts,
        "btts_no": 1.0 - btts,
        "total_over_2_5": over,
        "total_under_2_5": 1.0 - over,
        "home_clean_sheet": home_clean,
        "away_clean_sheet": away_clean,
    }


def distributions(
    matrix: tuple[tuple[float, ...], ...],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    size = len(matrix)
    home = tuple(sum(row) for row in matrix)
    away = tuple(sum(matrix[h][a] for h in range(size)) for a in range(size))
    total = [0.0] * (size * 2 - 1)
    for h, row in enumerate(matrix):
        for a, probability in enumerate(row):
            total[h + a] += probability
    return home, away, tuple(total)


def rust_score_atoms(forecast: ModelForecast) -> tuple[dict[str, object], ...]:
    """Project one canonical score distribution into the existing Rust atom contract."""
    atoms: list[dict[str, object]] = []
    unresolved = 0.0
    has_tail = bool(forecast.score_labels and forecast.score_labels[-1].endswith("+"))
    for home, row in enumerate(forecast.score_matrix):
        for away, probability in enumerate(row):
            if probability == 0.0:
                continue
            if has_tail and (home == len(row) - 1 or away == len(row) - 1):
                unresolved += probability
            else:
                atoms.append(
                    {
                        "kind": "EXACT_SCORE",
                        "home_goals": home,
                        "away_goals": away,
                        "probability": probability,
                    }
                )
    if unresolved:
        atoms.append(
            {
                "kind": "UNRESOLVED_TAIL",
                "home_goals": None,
                "away_goals": None,
                "probability": unresolved,
            }
        )
    return tuple(atoms)


def _probabilities(values: tuple[float, ...], name: str) -> None:
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
        raise ValueError(f"{name} probabilities must be finite in [0, 1]")


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _json_value(value: object) -> object:
    from dataclasses import fields, is_dataclass

    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value
