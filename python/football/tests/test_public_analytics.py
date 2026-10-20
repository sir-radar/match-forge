"""Frozen public analytics move from Go to Python without changing the policy."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from football.product.public_analytics import (
    PerformanceObservation,
    performance_baselines,
    performance_report,
    selection_agreement,
    summarize_form,
    summarize_h2h,
)

REFERENCE = json.loads(
    Path(__file__).with_name("fixtures").joinpath("legacy-public-performance.json").read_bytes()
)
COMPETITION = "00000000-0000-4000-8000-000000000001"
BASE = datetime(2025, 1, 1, 12, tzinfo=UTC)


def observation(index: int, style: str = "good") -> PerformanceObservation:
    kickoff = BASE + timedelta(days=index // 2)
    home, away = ((1, 0), (0, 0), (0, 2))[index % 3]
    if index % 11 == 0:
        home, away = 7, 0
    outcome = "home" if home > away else "away" if away > home else "draw"
    predicted = outcome
    if style == "bad" or (style == "late_bad" and index >= 100):
        predicted = {"home": "draw", "draw": "away", "away": "home"}[outcome]
    probabilities = {"home": 0.1, "draw": 0.1, "away": 0.1, "total_over_2_5": 0.6, "btts_yes": 0.4}
    probabilities[predicted] = 0.8
    return PerformanceObservation.from_source(
        {
            "kickoff_at": kickoff.isoformat(),
            "knowledge_cutoff": (
                kickoff - timedelta(hours=48 if index % 7 == 0 else 1)
            ).isoformat(),
            "outcome_known_at": None
            if style == "unknown_knowledge" and index % 3 == 0
            else (kickoff + timedelta(hours=2)).isoformat(),
            "home_score": home,
            "away_score": away,
            "probabilities": probabilities,
            "score_matrix": [
                {"home_goals": h, "away_goals": a, "probability": p}
                for h, a, p in (
                    (0, 0, 0.3),
                    (1, 0, 0.25),
                    (0, 1, 0.2),
                    (2, 0, 0.1),
                    (5, 0, 0.1),
                    (1, 1, 0.05),
                )
            ],
            "score_matrix_version": "legacy-compact-index-v1",
            "model_algorithm_version": "transferable-rolling-goals-poisson-v1",
        }
    )


@pytest.mark.parametrize(
    "case", REFERENCE["cases"], ids=lambda case: f"{case['style']}-{case['count']}"
)
def test_frozen_go_reference_is_preserved(case: dict[str, Any]) -> None:
    records = tuple(observation(i, case["style"]) for i in range(case["count"]))
    actual = performance_report(COMPETITION, records, horizon="LATEST")
    actual.update(league="Test League", country="Test", continent="Other")
    assert actual.keys() == case["expected"].keys()
    for key, expected in case["expected"].items():
        if isinstance(expected, float):
            assert actual[key] == pytest.approx(expected, abs=1e-12, rel=0), key
        else:
            assert actual[key] == expected, key


def test_same_kickoff_and_unknown_outcome_times_stay_out_of_prior_baselines() -> None:
    records = tuple(observation(i) for i in range(4))
    baseline = performance_baselines(records)
    assert baseline[0] == baseline[1] == {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}
    assert baseline[2] == {"home": 2 / 5, "draw": 2 / 5, "away": 1 / 5}
    unknown = tuple(observation(i, "unknown_knowledge") for i in range(4))
    assert performance_baselines(unknown)[2] == {"home": 1 / 4, "draw": 2 / 4, "away": 1 / 4}


@pytest.mark.parametrize(
    "selection,market,value,label",
    [
        ("HOME_WIN", "RESULT_1X2", 0.55, "AGREES"),
        ("BTTS_YES", "BTTS", 0.44, "WEAK_SUPPORT"),
        ("AWAY_WIN", "RESULT_1X2", 0.2, "DISAGREES"),
        ("TOTAL_OVER_1_5", "TOTAL_GOALS", 0.72, "AGREES"),
        ("TOTAL_UNDER_3_5", "TOTAL_GOALS", 0.68, "AGREES"),
        (" home_or_draw ", "DOUBLE_CHANCE", 0.8, "AGREES"),
        ("DRAW_OR_AWAY", "DOUBLE_CHANCE", 0.45, "WEAK_SUPPORT"),
    ],
)
def test_existing_selection_comparisons_are_preserved(
    selection: str, market: str, value: float, label: str
) -> None:
    probabilities = {
        "home": 0.55,
        "draw": 0.25,
        "away": 0.2,
        "btts_yes": 0.44,
        "total_over_1_5": 0.72,
        "total_under_3_5": 0.68,
    }
    actual, label_actual = selection_agreement(market, selection, probabilities)
    assert actual == pytest.approx(value, abs=1e-12, rel=0)
    assert label_actual == label


@pytest.mark.parametrize("selection", ["UNKNOWN", "Draw No Bet"])
def test_unknown_selections_remain_explicit(selection: str) -> None:
    assert selection_agreement("RESULT_1X2", selection, {"home": 0.55}) == (
        None,
        "UNABLE_TO_EVALUATE",
    )


def test_context_summaries_keep_the_existing_public_meaning() -> None:
    form = ({"goals_for": 2, "goals_against": 1}, {"goals_for": 1, "goals_against": 1})
    assert summarize_form(form) == {
        "recent_matches": 2,
        "goals_for": 3,
        "goals_against": 2,
        "average_goals_for": 1.5,
        "average_goals_against": 1.0,
    }
    assert summarize_form(()) is None
    result = summarize_h2h(({"home_goals": 2, "away_goals": 0}, {"home_goals": 1, "away_goals": 1}))
    assert result == {
        "meetings": 2,
        "home_wins": 1,
        "draws": 1,
        "away_wins": 0,
        "home_goals": 3,
        "away_goals": 1,
    }


@pytest.mark.parametrize("goals", [5, 6, 9])
def test_censored_buckets_are_never_exact_scores(goals: int) -> None:
    from dataclasses import replace

    from football.product.public_analytics import score_cells

    cells = score_cells(
        [
            {"home_goals": 5, "away_goals": 0, "probability": 0.8},
            {"home_goals": 1, "away_goals": 0, "probability": 0.2},
        ],
        "legacy-compact-index-v1",
        "transferable-rolling-goals-poisson-v1",
    )
    result = performance_report(
        COMPETITION,
        (replace(observation(0), scores=cells, home_goals=goals, away_goals=0),),
        horizon="LATEST",
    )
    assert (
        result["exact_score_rate"] == 0
        and result["top_three_score_rate"] == result["top_five_score_rate"] == 1
    )


def test_explicit_exact_buckets_and_invalid_labels_preserve_the_contract() -> None:
    from dataclasses import replace

    from football.product.public_analytics import score_cells

    cell = {
        "home_goals": 5,
        "away_goals": 0,
        "probability": 1.0,
        "home_bucket_kind": "EXACT",
        "away_bucket_kind": "EXACT",
        "home_label": "5",
        "away_label": "0",
    }
    cells = score_cells([cell], "compact-buckets-v2", "")
    result = performance_report(
        COMPETITION,
        (replace(observation(0), scores=cells, home_goals=5, away_goals=0),),
        horizon="LATEST",
    )
    assert result["exact_score_rate"] == 1
    cell["home_label"] = "5+"
    with pytest.raises(ValueError, match="bucket label"):
        score_cells([cell], "compact-buckets-v2", "")
    with pytest.raises(ValueError, match="legacy score interpretation"):
        score_cells([cell], "legacy-compact-index-v1", "unknown")


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), 1.01, True])
def test_invalid_comparison_probabilities_are_explicitly_unavailable(probability: float) -> None:
    assert selection_agreement("RESULT_1X2", "HOME_WIN", {"home": probability}) == (
        None,
        "UNABLE_TO_EVALUATE",
    )


@pytest.mark.parametrize(
    "changes", [{"home": 0.7}, {"draw": None}, {"draw": True}, {"draw": float("nan")}]
)
def test_invalid_stored_performance_probabilities_are_rejected(changes: dict[str, Any]) -> None:
    # Reuse a real source shape, including legacy bucket labels and final clocks.
    raw = {
        "probabilities": {**dict(observation(0).probabilities), **changes},
        "score_matrix": [],
        "score_matrix_version": "legacy-compact-index-v1",
        "model_algorithm_version": "transferable-rolling-goals-poisson-v1",
        "home_score": 1,
        "away_score": 0,
        "kickoff_at": BASE,
        "knowledge_cutoff": BASE - timedelta(hours=1),
        "outcome_known_at": None,
    }
    with pytest.raises(ValueError, match="probabilit"):
        PerformanceObservation.from_source(raw)


def test_baseline_includes_outcome_at_exact_knowledge_boundary() -> None:
    from dataclasses import replace

    first = observation(0)
    assert first.outcome_known_at is not None
    second = replace(observation(2), knowledge_cutoff=first.outcome_known_at)
    assert performance_baselines((first, second))[1] == {"home": 0.5, "draw": 0.25, "away": 0.25}


def test_current_product_serializer_buckets_are_consumed_without_translation() -> None:
    from football.product.domain import forecast_from_history, forecast_payload
    from football.product.public_analytics import score_cells
    from jsonschema import Draft202012Validator
    from test_product_domain import ARTIFACT, AWAY, HOME, _history

    target = BASE + timedelta(days=100)
    forecast = forecast_from_history(
        artifact_path=ARTIFACT,
        target_kickoff=target,
        home_team_id=HOME,
        away_team_id=AWAY,
        history=_history(target, 10),
    )
    assert forecast is not None
    payload = json.loads(json.dumps(forecast_payload(forecast)))
    schema = json.loads(Path("schemas/contracts/product-score-buckets-v2.schema.json").read_bytes())
    Draft202012Validator(schema).validate(payload)
    cells = score_cells(payload["score_matrix"], payload["score_matrix_version"], "")
    assert len(cells) == len(forecast.score_matrix) == 36
    assert cells[-1].home_kind == cells[-1].away_kind == "AT_LEAST"
    assert cells[-1].matches(7, 8)
    assert [cell.probability for cell in cells] == [
        row["probability"] for row in forecast.score_matrix
    ]


def test_missing_modern_bucket_labels_are_rejected_as_invalid_data() -> None:
    from football.product.public_analytics import score_cells

    with pytest.raises(ValueError, match="bucket label"):
        score_cells(
            [
                {
                    "home_goals": 1,
                    "away_goals": 0,
                    "probability": 1.0,
                    "home_bucket_kind": "EXACT",
                    "away_bucket_kind": "EXACT",
                    "home_bucket_label": "1",
                    "away_bucket_label": "0",
                }
            ],
            "compact-buckets-v2",
            "",
        )
