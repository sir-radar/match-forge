from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from football.forecasting.model_contracts import ForecastMode, ModelForecast, ModelStatus


@dataclass(frozen=True, slots=True)
class CoverageObservation:
    forecast: ModelForecast
    competition_id: str
    season_label: str


def coverage_report(
    observations: tuple[CoverageObservation, ...], *, eligible_targets: int
) -> dict[str, object]:
    if eligible_targets < 0:
        raise ValueError("eligible_targets must be non-negative")
    fixture_ids = {item.forecast.fixture_id for item in observations}
    if len(fixture_ids) != len(observations):
        raise ValueError("coverage observations must contain one forecast per fixture")
    if len(observations) > eligible_targets:
        raise ValueError("successful forecasts cannot exceed eligible targets")
    successful = tuple(item for item in observations if item.forecast.status is ModelStatus.SUCCESS)
    counts = Counter(
        item.forecast.lineage.forecast_mode
        for item in successful
        if item.forecast.lineage is not None
    )
    grouped: dict[str, dict[str, list[CoverageObservation]]] = {
        "competition": defaultdict(list),
        "season_domain": defaultdict(list),
        "promoted_status": defaultdict(list),
        "team_state": defaultdict(list),
    }
    for item in successful:
        grouped["competition"][item.competition_id].append(item)
        grouped["season_domain"][item.season_label].append(item)
        lineage = item.forecast.lineage
        if lineage is None:
            continue
        promotion = _promotion_key(lineage.home_promoted, lineage.away_promoted)
        grouped["promoted_status"][promotion].append(item)
        for state in {lineage.home_history_state, lineage.away_history_state}:
            grouped["team_state"][state].append(item)
    return {
        **_coverage_counts(len(successful), eligible_targets, counts),
        "by_competition": _group_reports(grouped["competition"]),
        "by_season_domain": _group_reports(grouped["season_domain"]),
        "by_promoted_status": _group_reports(grouped["promoted_status"]),
        "by_team_state": _group_reports(grouped["team_state"]),
    }


def assert_full_coverage(
    observations: tuple[CoverageObservation, ...], *, eligible_targets: int
) -> None:
    report = coverage_report(observations, eligible_targets=eligible_targets)
    if report["successful_forecasts"] != eligible_targets:
        raise AssertionError(
            f"full-coverage invariant failed: {report['successful_forecasts']} / {eligible_targets}"
        )


def _coverage_counts(
    successful: int, eligible: int, counts: Counter[ForecastMode]
) -> dict[str, int | float]:
    native = counts[ForecastMode.NATIVE]
    cold_home = counts[ForecastMode.COLD_START_HOME]
    cold_away = counts[ForecastMode.COLD_START_AWAY]
    cold_both = counts[ForecastMode.COLD_START_BOTH]
    fallback = counts[ForecastMode.CHAMPION_FALLBACK]
    cold_total = cold_home + cold_away + cold_both
    return {
        "eligible_targets": eligible,
        "successful_forecasts": successful,
        "coverage": successful / eligible if eligible else 0.0,
        "native_fitted_count": native,
        "cold_start_home_count": cold_home,
        "cold_start_away_count": cold_away,
        "cold_start_both_count": cold_both,
        "champion_fallback_count": fallback,
        "native_fitted_rate": native / eligible if eligible else 0.0,
        "cold_start_rate": cold_total / eligible if eligible else 0.0,
        "fallback_rate": fallback / eligible if eligible else 0.0,
    }


def _group_reports(
    values: dict[str, list[CoverageObservation]],
) -> dict[str, dict[str, int | float]]:
    reports: dict[str, dict[str, int | float]] = {}
    for key, rows in sorted(values.items()):
        counts = Counter(
            item.forecast.lineage.forecast_mode
            for item in rows
            if item.forecast.lineage is not None
        )
        reports[key] = _coverage_counts(len(rows), len(rows), counts)
    return reports


def _promotion_key(home: bool | None, away: bool | None) -> str:
    if home is True or away is True:
        return "PROMOTED_TEAM"
    if home is None or away is None:
        return "PROMOTION_STATUS_UNKNOWN"
    return "NOT_PROMOTED"
