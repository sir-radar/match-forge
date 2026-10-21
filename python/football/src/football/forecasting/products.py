"""Read-only score products; count/player models retain their own contracts."""

from typing import Any

from football.forecasting.model_contracts import (
    ModelForecast,
    ModelStatus,
    validate_model_forecast,
)


def score_products(forecast: ModelForecast) -> dict[str, Any]:
    """Project validated probabilities without fitting, sampling or changing mass.

    A legacy grid can contain censored score buckets. Those buckets are never
    presented as exact scores or an exact total-goal distribution.
    """
    if forecast.status is not ModelStatus.SUCCESS:
        raise ValueError("score products require a successful forecast")
    validate_model_forecast(forecast)
    size = len(forecast.score_labels)
    exact_labels = tuple(str(index) for index in range(size))
    censored_labels = exact_labels[:-1] + (f"{size - 1}+",)
    if forecast.score_labels not in (exact_labels, censored_labels):
        raise ValueError("score product labels require integer scores or a final censored bucket")
    exact = forecast.score_labels == exact_labels
    limit = size if exact else size - 1
    return {
        "product_family": "SCORE_DISTRIBUTION",
        "fixture_id": str(forecast.fixture_id),
        "model_id": forecast.model_id,
        "model_artifact_sha256": forecast.model_artifact_sha256,
        "input_snapshot_sha256": forecast.input_snapshot_sha256,
        "football_cutoff": forecast.football_cutoff.isoformat(),
        "knowledge_cutoff": forecast.knowledge_cutoff.isoformat(),
        "numerical_contract_version": forecast.numerical_contract_version,
        "one_x_two": {
            "home": forecast.home_probability,
            "draw": forecast.draw_probability,
            "away": forecast.away_probability,
        },
        "double_chance": {
            "home_or_draw": forecast.home_probability + forecast.draw_probability,
            "away_or_draw": forecast.away_probability + forecast.draw_probability,
            "home_or_away": forecast.home_probability + forecast.away_probability,
        },
        "btts": {"yes": forecast.btts_yes, "no": forecast.btts_no},
        "totals": {
            "over_2_5": forecast.total_over_2_5,
            "under_2_5": forecast.total_under_2_5,
            "distribution": list(forecast.total_goal_distribution),
            "distribution_semantics": (
                "EXACT_RESOLVED_TOTALS" if exact else "SUM_OF_SCORE_BUCKET_INDICES"
            ),
        },
        "exact_scores": [
            {
                "home_goals": home,
                "away_goals": away,
                "probability": forecast.score_matrix[home][away],
            }
            for home in range(limit)
            for away in range(limit)
        ],
        "score_distribution": {
            "support": "EXACT_SCORES" if exact else "CENSORED_BUCKETS",
            "labels": list(forecast.score_labels),
            "matrix": [list(row) for row in forecast.score_matrix],
            "unresolved_tail_probability": forecast.unresolved_tail_probability,
        },
        "team_goals": {
            "labels": list(forecast.score_labels),
            "home": list(forecast.home_goal_distribution),
            "away": list(forecast.away_goal_distribution),
        },
        "clean_sheet": {"home": forecast.home_clean_sheet, "away": forecast.away_clean_sheet},
    }
