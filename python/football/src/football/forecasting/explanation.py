from __future__ import annotations

import math
from dataclasses import dataclass

from football.forecasting.model_contracts import (
    CompetitionContext,
    ForecastInputSnapshot,
    ModelForecast,
)


@dataclass(frozen=True, slots=True)
class ModelAgreement:
    available_models: int
    home_lean: int
    draw_lean: int
    away_lean: int
    agreement: str
    probability_spread: float


@dataclass(frozen=True, slots=True)
class ForecastExplanation:
    summary: str
    confidence: str
    model_agreement: ModelAgreement
    drivers: tuple[str, ...]
    counter_signals: tuple[str, ...]
    context: tuple[str, ...]
    data_quality: tuple[str, ...]


def build_forecast_explanation(
    official: ModelForecast,
    model_forecasts: tuple[ModelForecast, ...],
    snapshot: ForecastInputSnapshot,
) -> ForecastExplanation:
    agreement = model_agreement(model_forecasts)
    probabilities = (
        official.home_probability,
        official.draw_probability,
        official.away_probability,
    )
    confidence = uncertainty_classification(official, agreement, snapshot)
    favourite_index = max(range(3), key=probabilities.__getitem__)
    labels = ("Home", "Draw", "Away")
    drivers, counter, context = _reason_codes(snapshot, agreement)
    top = probabilities[favourite_index]
    summary = (
        f"{labels[favourite_index]} is most likely at {top:.0%}; "
        f"confidence is {confidence.lower()}. {agreement.available_models} model(s) "
        f"were available with {agreement.agreement.lower()} agreement."
    )
    return ForecastExplanation(
        summary=summary,
        confidence=confidence,
        model_agreement=agreement,
        drivers=tuple(drivers),
        counter_signals=tuple(counter),
        context=tuple(context),
        data_quality=snapshot.missingness,
    )


def _reason_codes(
    snapshot: ForecastInputSnapshot, agreement: ModelAgreement
) -> tuple[list[str], list[str], list[str]]:
    drivers, counter = _form_and_strength_reasons(snapshot)
    context: list[str] = []
    _append_h2h_reason(snapshot, drivers, context)
    if agreement.agreement in ("LOW", "MIXED"):
        counter.append("MODEL_DISAGREEMENT")
    if min(snapshot.home_form_10.match_count, snapshot.away_form_10.match_count) < 10:
        counter.append("LIMITED_HISTORY")
    return drivers, counter, context


def _form_and_strength_reasons(
    snapshot: ForecastInputSnapshot,
) -> tuple[list[str], list[str]]:
    drivers: list[str] = []
    counter: list[str] = []
    if snapshot.rating.rating_difference >= 75:
        drivers.append("HOME_STRENGTH_ADVANTAGE")
    elif snapshot.rating.rating_difference <= -75:
        drivers.append("AWAY_STRENGTH_ADVANTAGE")
    if snapshot.home_form_5.goals_for is not None and snapshot.home_form_5.goals_for >= 1.8:
        drivers.append("HOME_ATTACK_FORM_STRONG")
    if snapshot.away_form_5.goals_for is not None and snapshot.away_form_5.goals_for >= 1.8:
        drivers.append("AWAY_ATTACK_FORM_STRONG")
    if snapshot.home_form_5.goals_against is not None and snapshot.home_form_5.goals_against >= 1.8:
        counter.append("HOME_DEFENCE_WEAK")
    if snapshot.away_form_5.goals_against is not None and snapshot.away_form_5.goals_against >= 1.8:
        counter.append("AWAY_DEFENCE_WEAK")
    rest_delta = _rest_delta(snapshot)
    if rest_delta is not None and rest_delta >= 3:
        drivers.append("REST_ADVANTAGE_HOME")
    elif rest_delta is not None and rest_delta <= -3:
        drivers.append("REST_ADVANTAGE_AWAY")
    return drivers, counter


def _append_h2h_reason(
    snapshot: ForecastInputSnapshot, drivers: list[str], context: list[str]
) -> None:
    h2h = next(
        (item for item in snapshot.h2h if item.competition_context is snapshot.competition_context),
        None,
    )
    if h2h is not None:
        context.append(f"H2H_{h2h.competition_context}_SAMPLE_{h2h.sample_size}")
        if h2h.effective_sample_size >= 5 and h2h.home_team_win_rate is not None:
            if h2h.home_team_win_rate >= 0.6:
                drivers.append(_h2h_code(snapshot.competition_context, home=True))
            elif h2h.away_team_win_rate is not None and h2h.away_team_win_rate >= 0.6:
                drivers.append(_h2h_code(snapshot.competition_context, home=False))


def model_agreement(forecasts: tuple[ModelForecast, ...]) -> ModelAgreement:
    if not forecasts:
        return ModelAgreement(0, 0, 0, 0, "UNAVAILABLE", 0.0)
    probabilities = tuple(
        (item.home_probability, item.draw_probability, item.away_probability) for item in forecasts
    )
    leans = tuple(max(range(3), key=row.__getitem__) for row in probabilities)
    top_count = max(leans.count(index) for index in range(3))
    ratio = top_count / len(leans)
    spread = max(
        max(row[index] for row in probabilities) - min(row[index] for row in probabilities)
        for index in range(3)
    )
    if ratio == 1.0 and spread <= 0.08:
        label = "HIGH"
    elif ratio >= 0.67 and spread <= 0.15:
        label = "MODERATE"
    elif ratio >= 0.5:
        label = "MIXED"
    else:
        label = "LOW"
    return ModelAgreement(
        available_models=len(forecasts),
        home_lean=leans.count(0),
        draw_lean=leans.count(1),
        away_lean=leans.count(2),
        agreement=label,
        probability_spread=spread,
    )


def uncertainty_classification(
    forecast: ModelForecast,
    agreement: ModelAgreement,
    snapshot: ForecastInputSnapshot,
) -> str:
    values = sorted(
        (forecast.home_probability, forecast.draw_probability, forecast.away_probability),
        reverse=True,
    )
    entropy = -sum(value * math.log(value) for value in values if value > 0) / math.log(3)
    margin = values[0] - values[1]
    incomplete = (
        bool(snapshot.missingness)
        or min(snapshot.home_form_10.match_count, snapshot.away_form_10.match_count) < 10
    )
    if entropy >= 0.9 or margin < 0.1 or agreement.agreement in ("LOW", "MIXED") or incomplete:
        return "HIGH"
    if entropy >= 0.72 or margin < 0.2 or agreement.agreement != "HIGH":
        return "MEDIUM"
    return "LOW"


def _rest_delta(snapshot: ForecastInputSnapshot) -> float | None:
    home = snapshot.home_rest.days_since_last_match
    away = snapshot.away_rest.days_since_last_match
    return home - away if home is not None and away is not None else None


def _h2h_code(context: CompetitionContext, *, home: bool) -> str:
    side = "HOME" if home else "AWAY"
    prefix = "LEAGUE" if context is CompetitionContext.LEAGUE else "CUP"
    return f"{prefix}_H2H_{side}_EDGE"
