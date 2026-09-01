from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from football.forecasting.calibration import (
    BinaryIsotonicCalibratorV1,
    BinaryPlattCalibratorV1,
    MulticlassVectorCalibratorV1,
)
from football.forecasting.contracts import MatchResultProbabilitiesV1
from football.forecasting.dataset import EvaluationMatchOutcomeV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    evaluate_match_results,
)
from football.forecasting.execution import Sprint2RawForecastV1

CalibrationStatus = Literal["AVAILABLE", "INSUFFICIENT_HISTORY", "INSUFFICIENT_EVENTS"]
CalibrationMethod = Literal["multiclass_vector", "platt", "isotonic"]
CalibrationProduct = Literal["1x2", "over_2_5", "btts_yes"]
CalibrationVariant = Literal["MODEL_RAW", "MODEL_CALIBRATED"]
_EPSILON = 1e-15
_Z_95 = 1.959963984540054


class CalibrationAnalysisError(ValueError):
    """Chronological calibration inputs or outputs are invalid."""


@dataclass(frozen=True, slots=True)
class Sprint2CalibrationPolicyV1:
    binary_platt_minimum: int = 100
    binary_platt_minimum_events: int = 20
    binary_isotonic_minimum: int = 150
    binary_isotonic_minimum_events: int = 30
    binary_isotonic_minimum_distinct: int = 20
    multiclass_minimum: int = 150
    multiclass_minimum_class_events: int = 30
    fixed_bin_count: int = 10
    sparse_bin_threshold: int = 20
    max_log_loss_regression: float = 0.005
    max_brier_regression: float = 0.002
    contract: str = "Sprint2CalibrationPolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "Sprint2CalibrationPolicyV1":
            raise CalibrationAnalysisError("unsupported calibration policy")
        integer_fields = (
            ("binary_platt_minimum", self.binary_platt_minimum),
            ("binary_platt_minimum_events", self.binary_platt_minimum_events),
            ("binary_isotonic_minimum", self.binary_isotonic_minimum),
            ("binary_isotonic_minimum_events", self.binary_isotonic_minimum_events),
            ("binary_isotonic_minimum_distinct", self.binary_isotonic_minimum_distinct),
            ("multiclass_minimum", self.multiclass_minimum),
            ("multiclass_minimum_class_events", self.multiclass_minimum_class_events),
            ("fixed_bin_count", self.fixed_bin_count),
            ("sparse_bin_threshold", self.sparse_bin_threshold),
        )
        for field_name, value in integer_fields:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise CalibrationAnalysisError(f"{field_name} must be a positive integer")
        if self.fixed_bin_count != 10:
            raise CalibrationAnalysisError("Sprint 2 calibration requires fixed deciles")
        for field_name, metric_value in (
            ("max_log_loss_regression", self.max_log_loss_regression),
            ("max_brier_regression", self.max_brier_regression),
        ):
            if not math.isfinite(metric_value) or metric_value < 0.0:
                raise CalibrationAnalysisError(f"{field_name} must be finite and non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "binary_platt_minimum": self.binary_platt_minimum,
            "binary_platt_minimum_events": self.binary_platt_minimum_events,
            "binary_isotonic_minimum": self.binary_isotonic_minimum,
            "binary_isotonic_minimum_events": self.binary_isotonic_minimum_events,
            "binary_isotonic_minimum_distinct": self.binary_isotonic_minimum_distinct,
            "multiclass_minimum": self.multiclass_minimum,
            "multiclass_minimum_class_events": self.multiclass_minimum_class_events,
            "fixed_bin_count": self.fixed_bin_count,
            "sparse_bin_threshold": self.sparse_bin_threshold,
            "max_log_loss_regression": self.max_log_loss_regression,
            "max_brier_regression": self.max_brier_regression,
        }


@dataclass(frozen=True, slots=True)
class CalibrationPredictionV1:
    match_id: UUID
    kickoff_at: datetime
    outcome_known_at: datetime
    base_model: str
    product: CalibrationProduct
    method: CalibrationMethod
    status: CalibrationStatus
    training_sample_count: int
    outcome: str
    raw_home: float | None = None
    raw_draw: float | None = None
    raw_away: float | None = None
    calibrated_home: float | None = None
    calibrated_draw: float | None = None
    calibrated_away: float | None = None
    raw_probability: float | None = None
    calibrated_probability: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "match_id": str(self.match_id),
            "kickoff_at": _utc(self.kickoff_at),
            "outcome_known_at": _utc(self.outcome_known_at),
            "base_model": self.base_model,
            "product": self.product,
            "method": self.method,
            "status": self.status,
            "training_sample_count": self.training_sample_count,
            "outcome": self.outcome,
            "raw_home": self.raw_home,
            "raw_draw": self.raw_draw,
            "raw_away": self.raw_away,
            "calibrated_home": self.calibrated_home,
            "calibrated_draw": self.calibrated_draw,
            "calibrated_away": self.calibrated_away,
            "raw_probability": self.raw_probability,
            "calibrated_probability": self.calibrated_probability,
        }


@dataclass(frozen=True, slots=True)
class CalibrationMetricV1:
    base_model: str
    product: CalibrationProduct
    method: CalibrationMethod
    sample_count: int
    raw_log_loss: float
    calibrated_log_loss: float
    raw_brier: float
    calibrated_brier: float
    raw_ece: float
    calibrated_ece: float
    accepted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "base_model": self.base_model,
            "product": self.product,
            "method": self.method,
            "sample_count": self.sample_count,
            "raw_log_loss": self.raw_log_loss,
            "calibrated_log_loss": self.calibrated_log_loss,
            "raw_brier": self.raw_brier,
            "calibrated_brier": self.calibrated_brier,
            "raw_ece": self.raw_ece,
            "calibrated_ece": self.calibrated_ece,
            "accepted": self.accepted,
        }


@dataclass(frozen=True, slots=True)
class CalibrationBinV1:
    base_model: str
    product: CalibrationProduct
    method: CalibrationMethod
    variant: CalibrationVariant
    outcome_class: str
    lower_bound: float
    upper_bound: float
    sample_count: int
    event_count: int
    mean_probability: float | None
    observed_frequency: float | None
    absolute_gap: float | None
    wilson_lower: float | None
    wilson_upper: float | None
    sparse: bool

    def to_dict(self) -> dict[str, object]:
        return {
            field: getattr(self, field)
            for field in (
                "base_model",
                "product",
                "method",
                "variant",
                "outcome_class",
                "lower_bound",
                "upper_bound",
                "sample_count",
                "event_count",
                "mean_probability",
                "observed_frequency",
                "absolute_gap",
                "wilson_lower",
                "wilson_upper",
                "sparse",
            )
        }


@dataclass(frozen=True, slots=True)
class Sprint2CalibrationAnalysisV1:
    policy: Sprint2CalibrationPolicyV1
    predictions: tuple[CalibrationPredictionV1, ...]
    metrics: tuple[CalibrationMetricV1, ...]
    bins: tuple[CalibrationBinV1, ...]
    contract: str = "Sprint2CalibrationAnalysisV1"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "policy": self.policy.to_dict(),
            "prediction_count": len(self.predictions),
            "metrics": [metric.to_dict() for metric in self.metrics],
        }


@dataclass(frozen=True, slots=True)
class _Observation:
    forecast: Sprint2RawForecastV1
    outcome: EvaluationMatchOutcomeV1


class Sprint2CalibrationAnalyzerV1:
    def __init__(self, policy: Sprint2CalibrationPolicyV1 | None = None) -> None:
        self.policy = policy or Sprint2CalibrationPolicyV1()

    def analyze(
        self,
        forecasts: tuple[Sprint2RawForecastV1, ...],
        outcomes: tuple[EvaluationMatchOutcomeV1, ...],
    ) -> Sprint2CalibrationAnalysisV1:
        aligned = _align(forecasts, outcomes)
        history: list[_Observation] = []
        predictions: list[CalibrationPredictionV1] = []
        for batch in _batches(aligned):
            cutoff = batch[0].forecast.context.kickoff_at
            eligible = tuple(item for item in history if item.outcome.outcome_known_at < cutoff)
            predictions.extend(self._batch_predictions(batch, eligible))
            history.extend(batch)
        ordered = tuple(predictions)
        return Sprint2CalibrationAnalysisV1(
            self.policy,
            ordered,
            _metrics(ordered, self.policy),
            _bins(ordered, self.policy),
        )

    def _batch_predictions(
        self, batch: tuple[_Observation, ...], history: tuple[_Observation, ...]
    ) -> tuple[CalibrationPredictionV1, ...]:
        rows: list[CalibrationPredictionV1] = []
        for base_model in ("elo", "dixon_coles"):
            rows.extend(self._multiclass_predictions(batch, history, base_model))
        for product in ("over_2_5", "btts_yes"):
            for method in ("platt", "isotonic"):
                rows.extend(self._binary_predictions(batch, history, product, method))
        return tuple(rows)

    def _multiclass_predictions(
        self,
        batch: tuple[_Observation, ...],
        history: tuple[_Observation, ...],
        base_model: str,
    ) -> tuple[CalibrationPredictionV1, ...]:
        status = _multiclass_status(history, self.policy)
        calibrator = None
        if status == "AVAILABLE":
            calibrator = MulticlassVectorCalibratorV1.fit(
                tuple(_evaluated(item, base_model) for item in history),
                calibration_cutoff=batch[0].forecast.context.kickoff_at,
            )
        rows = []
        for item in batch:
            raw = _result_probability(item.forecast, base_model)
            calibrated = calibrator.calibrate(raw) if calibrator else None
            rows.append(
                CalibrationPredictionV1(
                    match_id=item.forecast.context.match_id,
                    kickoff_at=item.forecast.context.kickoff_at,
                    outcome_known_at=item.outcome.outcome_known_at,
                    base_model=base_model,
                    product="1x2",
                    method="multiclass_vector",
                    status=status,
                    training_sample_count=len(history),
                    outcome=_match_outcome(item.outcome),
                    raw_home=raw.home,
                    raw_draw=raw.draw,
                    raw_away=raw.away,
                    calibrated_home=calibrated.home if calibrated else None,
                    calibrated_draw=calibrated.draw if calibrated else None,
                    calibrated_away=calibrated.away if calibrated else None,
                )
            )
        return tuple(rows)

    def _binary_predictions(
        self,
        batch: tuple[_Observation, ...],
        history: tuple[_Observation, ...],
        product: Literal["over_2_5", "btts_yes"],
        method: Literal["platt", "isotonic"],
    ) -> tuple[CalibrationPredictionV1, ...]:
        raw_history = tuple(_binary_probability(item.forecast, product) for item in history)
        targets = tuple(float(_binary_outcome(item.outcome, product)) for item in history)
        status = _binary_status(raw_history, targets, method, self.policy)
        calibrator: BinaryPlattCalibratorV1 | BinaryIsotonicCalibratorV1 | None = None
        if status == "AVAILABLE":
            calibrator = (
                BinaryPlattCalibratorV1.fit(raw_history, targets)
                if method == "platt"
                else BinaryIsotonicCalibratorV1.fit(raw_history, targets)
            )
        rows = []
        for item in batch:
            raw = _binary_probability(item.forecast, product)
            rows.append(
                CalibrationPredictionV1(
                    match_id=item.forecast.context.match_id,
                    kickoff_at=item.forecast.context.kickoff_at,
                    outcome_known_at=item.outcome.outcome_known_at,
                    base_model="dixon_coles",
                    product=product,
                    method=method,
                    status=status,
                    training_sample_count=len(history),
                    outcome=str(int(_binary_outcome(item.outcome, product))),
                    raw_probability=raw,
                    calibrated_probability=calibrator.calibrate(raw) if calibrator else None,
                )
            )
        return tuple(rows)


def _align(
    forecasts: tuple[Sprint2RawForecastV1, ...],
    outcomes: tuple[EvaluationMatchOutcomeV1, ...],
) -> tuple[_Observation, ...]:
    if not forecasts:
        raise CalibrationAnalysisError("calibration analysis requires raw forecasts")
    outcome_by_id = {outcome.match_id: outcome for outcome in outcomes}
    forecast_ids = {item.context.match_id for item in forecasts}
    if len(outcome_by_id) != len(outcomes) or forecast_ids != set(outcome_by_id):
        raise CalibrationAnalysisError("calibration forecasts and outcomes must align")
    aligned = tuple(_Observation(item, outcome_by_id[item.context.match_id]) for item in forecasts)
    if any(item.forecast.context.kickoff_at != item.outcome.kickoff_at for item in aligned):
        raise CalibrationAnalysisError("calibration forecast and outcome kickoffs conflict")
    return tuple(
        sorted(
            aligned,
            key=lambda item: (
                item.forecast.context.kickoff_at,
                str(item.forecast.context.match_id),
            ),
        )
    )


def _batches(aligned: tuple[_Observation, ...]) -> tuple[tuple[_Observation, ...], ...]:
    batches: list[list[_Observation]] = []
    for item in aligned:
        kickoff = item.forecast.context.kickoff_at
        if not batches or batches[-1][0].forecast.context.kickoff_at != kickoff:
            batches.append([item])
        else:
            batches[-1].append(item)
    return tuple(tuple(batch) for batch in batches)


def _multiclass_status(
    history: tuple[_Observation, ...], policy: Sprint2CalibrationPolicyV1
) -> CalibrationStatus:
    if len(history) < policy.multiclass_minimum:
        return "INSUFFICIENT_HISTORY"
    counts = {outcome: 0 for outcome in ("HOME", "DRAW", "AWAY")}
    for item in history:
        counts[_match_outcome(item.outcome)] += 1
    if min(counts.values()) < policy.multiclass_minimum_class_events:
        return "INSUFFICIENT_EVENTS"
    return "AVAILABLE"


def _binary_status(
    probabilities: tuple[float, ...],
    targets: tuple[float, ...],
    method: Literal["platt", "isotonic"],
    policy: Sprint2CalibrationPolicyV1,
) -> CalibrationStatus:
    minimum = policy.binary_platt_minimum if method == "platt" else policy.binary_isotonic_minimum
    event_minimum = (
        policy.binary_platt_minimum_events
        if method == "platt"
        else policy.binary_isotonic_minimum_events
    )
    if len(probabilities) < minimum:
        return "INSUFFICIENT_HISTORY"
    positives = sum(int(value) for value in targets)
    if min(positives, len(targets) - positives) < event_minimum:
        return "INSUFFICIENT_EVENTS"
    if method == "isotonic" and len(set(probabilities)) < policy.binary_isotonic_minimum_distinct:
        return "INSUFFICIENT_EVENTS"
    return "AVAILABLE"


def _metrics(
    predictions: tuple[CalibrationPredictionV1, ...], policy: Sprint2CalibrationPolicyV1
) -> tuple[CalibrationMetricV1, ...]:
    keys = sorted(
        {
            (row.base_model, row.product, row.method)
            for row in predictions
            if row.status == "AVAILABLE"
        }
    )
    results = []
    for key in keys:
        rows = tuple(
            row
            for row in predictions
            if row.status == "AVAILABLE" and (row.base_model, row.product, row.method) == key
        )
        raw, calibrated = (
            _multiclass_metric_values(rows)
            if rows[0].product == "1x2"
            else _binary_metric_values(rows)
        )
        results.append(
            CalibrationMetricV1(
                base_model=rows[0].base_model,
                product=rows[0].product,
                method=rows[0].method,
                sample_count=len(rows),
                raw_log_loss=raw[0],
                calibrated_log_loss=calibrated[0],
                raw_brier=raw[1],
                calibrated_brier=calibrated[1],
                raw_ece=raw[2],
                calibrated_ece=calibrated[2],
                accepted=(
                    calibrated[0] <= raw[0] + policy.max_log_loss_regression
                    and calibrated[1] <= raw[1] + policy.max_brier_regression
                    and calibrated[2] < raw[2]
                ),
            )
        )
    return tuple(results)


def _multiclass_metric_values(
    rows: tuple[CalibrationPredictionV1, ...],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    def values(variant: CalibrationVariant) -> tuple[float, float, float]:
        result = evaluate_match_results(
            tuple(
                EvaluatedMatchResultV1(
                    kickoff_at=row.kickoff_at,
                    prediction_cutoff=row.kickoff_at,
                    outcome_known_at=row.outcome_known_at,
                    probabilities=_row_probabilities(row, variant),
                    outcome=_match_outcome_text(row.outcome),
                )
                for row in rows
            )
        )
        return result.log_loss, result.brier_score, result.expected_calibration_error

    return values("MODEL_RAW"), values("MODEL_CALIBRATED")


def _binary_metric_values(
    rows: tuple[CalibrationPredictionV1, ...],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    def values(variant: CalibrationVariant) -> tuple[float, float, float]:
        samples = tuple((_row_binary_probability(row, variant), int(row.outcome)) for row in rows)
        count = len(samples)
        log_loss = (
            sum(
                -(target * math.log(max(probability, _EPSILON)))
                - ((1 - target) * math.log(max(1.0 - probability, _EPSILON)))
                for probability, target in samples
            )
            / count
        )
        brier = sum((probability - target) ** 2 for probability, target in samples) / count
        return log_loss, brier, _binary_ece(samples)

    return values("MODEL_RAW"), values("MODEL_CALIBRATED")


def _bins(
    predictions: tuple[CalibrationPredictionV1, ...], policy: Sprint2CalibrationPolicyV1
) -> tuple[CalibrationBinV1, ...]:
    keys = sorted(
        {
            (row.base_model, row.product, row.method)
            for row in predictions
            if row.status == "AVAILABLE"
        }
    )
    results: list[CalibrationBinV1] = []
    for key in keys:
        rows = tuple(
            row
            for row in predictions
            if row.status == "AVAILABLE" and (row.base_model, row.product, row.method) == key
        )
        for variant in ("MODEL_RAW", "MODEL_CALIBRATED"):
            results.extend(_group_bins(rows, variant, policy))
    return tuple(results)


def _group_bins(
    rows: tuple[CalibrationPredictionV1, ...],
    variant: CalibrationVariant,
    policy: Sprint2CalibrationPolicyV1,
) -> tuple[CalibrationBinV1, ...]:
    if rows[0].product != "1x2":
        samples = tuple((_row_binary_probability(row, variant), int(row.outcome)) for row in rows)
        return _fixed_bins(rows[0], variant, "YES", samples, policy)
    results: list[CalibrationBinV1] = []
    for outcome_class, index in (("HOME", 0), ("DRAW", 1), ("AWAY", 2)):
        samples = tuple(
            (
                _probability_tuple(_row_probabilities(row, variant))[index],
                int(row.outcome == outcome_class),
            )
            for row in rows
        )
        results.extend(_fixed_bins(rows[0], variant, outcome_class, samples, policy))
    return tuple(results)


def _fixed_bins(
    row: CalibrationPredictionV1,
    variant: CalibrationVariant,
    outcome_class: str,
    samples: tuple[tuple[float, int], ...],
    policy: Sprint2CalibrationPolicyV1,
) -> tuple[CalibrationBinV1, ...]:
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(policy.fixed_bin_count)]
    for probability, target in samples:
        grouped[min(int(probability * policy.fixed_bin_count), policy.fixed_bin_count - 1)].append(
            (probability, target)
        )
    results = []
    for index, values in enumerate(grouped):
        count = len(values)
        events = sum(target for _probability, target in values)
        mean = sum(probability for probability, _target in values) / count if count else None
        observed = events / count if count else None
        lower, upper = _wilson(events, count) if count else (None, None)
        results.append(
            CalibrationBinV1(
                base_model=row.base_model,
                product=row.product,
                method=row.method,
                variant=variant,
                outcome_class=outcome_class,
                lower_bound=index / policy.fixed_bin_count,
                upper_bound=(index + 1) / policy.fixed_bin_count,
                sample_count=count,
                event_count=events,
                mean_probability=mean,
                observed_frequency=observed,
                absolute_gap=abs(mean - observed)
                if mean is not None and observed is not None
                else None,
                wilson_lower=lower,
                wilson_upper=upper,
                sparse=count < policy.sparse_bin_threshold,
            )
        )
    return tuple(results)


def _binary_ece(samples: tuple[tuple[float, int], ...]) -> float:
    grouped: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for probability, target in samples:
        grouped[min(int(probability * 10), 9)].append((probability, target))
    return sum(
        len(values)
        / len(samples)
        * abs(
            sum(probability for probability, _target in values) / len(values)
            - sum(target for _probability, target in values) / len(values)
        )
        for values in grouped
        if values
    )


def _wilson(events: int, count: int) -> tuple[float, float]:
    observed = events / count
    denominator = 1.0 + (_Z_95**2 / count)
    center = (observed + (_Z_95**2 / (2.0 * count))) / denominator
    margin = (
        _Z_95
        * math.sqrt((observed * (1.0 - observed) / count) + (_Z_95**2 / (4.0 * count**2)))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _evaluated(item: _Observation, base_model: str) -> EvaluatedMatchResultV1:
    return EvaluatedMatchResultV1(
        kickoff_at=item.forecast.context.kickoff_at,
        prediction_cutoff=item.forecast.context.kickoff_at,
        outcome_known_at=item.outcome.outcome_known_at,
        probabilities=_result_probability(item.forecast, base_model),
        outcome=_match_outcome(item.outcome),
    )


def _result_probability(
    forecast: Sprint2RawForecastV1, base_model: str
) -> MatchResultProbabilitiesV1:
    return forecast.elo_result if base_model == "elo" else forecast.dixon_coles_result


def _binary_probability(
    forecast: Sprint2RawForecastV1, product: Literal["over_2_5", "btts_yes"]
) -> float:
    return forecast.goal.over_2_5 if product == "over_2_5" else forecast.goal.btts_yes


def _binary_outcome(
    outcome: EvaluationMatchOutcomeV1, product: Literal["over_2_5", "btts_yes"]
) -> bool:
    if product == "over_2_5":
        return outcome.home_score + outcome.away_score >= 3
    return outcome.home_score > 0 and outcome.away_score > 0


def _match_outcome(outcome: EvaluationMatchOutcomeV1) -> MatchOutcome:
    if outcome.home_score > outcome.away_score:
        return "HOME"
    if outcome.home_score < outcome.away_score:
        return "AWAY"
    return "DRAW"


def _match_outcome_text(value: str) -> MatchOutcome:
    if value not in ("HOME", "DRAW", "AWAY"):
        raise CalibrationAnalysisError("invalid stored match outcome")
    return cast(MatchOutcome, value)


def _row_probabilities(
    row: CalibrationPredictionV1, variant: CalibrationVariant
) -> MatchResultProbabilitiesV1:
    values = (
        (row.raw_home, row.raw_draw, row.raw_away)
        if variant == "MODEL_RAW"
        else (row.calibrated_home, row.calibrated_draw, row.calibrated_away)
    )
    if any(value is None for value in values):
        raise CalibrationAnalysisError("available multiclass prediction lacks probabilities")
    home, draw, away = values
    if home is None or draw is None or away is None:
        raise CalibrationAnalysisError("available multiclass prediction lacks probabilities")
    return MatchResultProbabilitiesV1(home, draw, away)


def _row_binary_probability(row: CalibrationPredictionV1, variant: CalibrationVariant) -> float:
    value = row.raw_probability if variant == "MODEL_RAW" else row.calibrated_probability
    if value is None:
        raise CalibrationAnalysisError("available binary prediction lacks probability")
    return value


def _probability_tuple(probabilities: MatchResultProbabilitiesV1) -> tuple[float, float, float]:
    return probabilities.home, probabilities.draw, probabilities.away


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
