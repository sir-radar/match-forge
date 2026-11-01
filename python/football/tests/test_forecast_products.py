import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from football.cli.main import run
from football.forecasting.contracts import CornerForecastPayloadV1, forecast_payload_dict
from football.forecasting.model_contracts import PROBABILITY_TOLERANCE
from football.forecasting.multimodel_cli import _forecast_dict
from football.forecasting.products import score_products
from test_multi_model_forecasting import _forecast

MATRIX = ((0.1, 0.2, 0.0), (0.15, 0.25, 0.0), (0.05, 0.05, 0.2))


def test_score_products_share_one_distribution_and_keep_bucket_semantics() -> None:
    forecast = _forecast("score-model", MATRIX)
    before = _forecast_dict(forecast)
    products = score_products(forecast)
    assert products["product_family"] == "SCORE_DISTRIBUTION"
    assert products["model_artifact_sha256"] == forecast.model_artifact_sha256
    assert products["input_snapshot_sha256"] == forecast.input_snapshot_sha256
    assert products["one_x_two"] == pytest.approx({"home": 0.25, "draw": 0.55, "away": 0.2})
    assert products["double_chance"] == pytest.approx(
        {"home_or_draw": 0.8, "away_or_draw": 0.75, "home_or_away": 0.45}
    )
    assert products["btts"] == pytest.approx({"yes": 0.5, "no": 0.5})
    assert products["totals"]["over_2_5"] == pytest.approx(0.25)
    assert products["team_goals"]["home"] == pytest.approx([0.3, 0.4, 0.3])
    assert products["team_goals"]["away"] == pytest.approx([0.3, 0.5, 0.2])
    assert products["team_goals"]["labels"] == ["0", "1", "2+"]
    assert products["totals"]["distribution_semantics"] == "SUM_OF_SCORE_BUCKET_INDICES"
    assert products["clean_sheet"] == pytest.approx({"home": 0.3, "away": 0.3})
    assert products["score_distribution"]["support"] == "CENSORED_BUCKETS"
    assert products["score_distribution"]["labels"] == ["0", "1", "2+"]
    assert products["score_distribution"]["matrix"] == [list(row) for row in MATRIX]
    assert products["exact_scores"] == [
        {"home_goals": h, "away_goals": a, "probability": MATRIX[h][a]}
        for h in range(2)
        for a in range(2)
    ]
    products["score_distribution"]["matrix"][0][0] = 0.9
    assert _forecast_dict(forecast) == before


def test_exact_support_is_never_renormalized_and_tail_stays_explicit() -> None:
    from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
    from football.forecasting.runtime_models import ModelRegistration, load_registered_champion
    from test_feature_snapshots import _input

    entry = ModelRegistration.from_bytes(Path("config/models/current-champion.json").read_bytes())
    forecast = TransferableRollingGoalsChampion().predict(
        load_registered_champion(entry, Path(".")), _input()
    )
    products = score_products(forecast)
    assert products["score_distribution"]["support"] == "EXACT_SCORES"
    assert (
        products["score_distribution"]["unresolved_tail_probability"]
        == forecast.unresolved_tail_probability
    )
    assert len(products["exact_scores"]) == len(forecast.score_labels) ** 2
    assert sum(row["probability"] for row in products["exact_scores"]) == pytest.approx(
        1.0 - forecast.unresolved_tail_probability, abs=1e-14
    )
    assert products["one_x_two"]["home"] == forecast.home_probability
    assert products["totals"]["distribution"] == list(forecast.total_goal_distribution)
    derived = products["derived_goals"]
    for partition in (
        derived["draw_no_bet"]["home"],
        derived["winning_margin"],
        derived["result_btts"],
    ):
        assert partition["unresolved_probability"] == forecast.unresolved_tail_probability
        assert sum(partition["resolved"].values()) + partition[
            "unresolved_probability"
        ] == pytest.approx(1, abs=1e-14)
        for outcome, lower in partition["resolved"].items():
            assert partition["bounds"][outcome]["lower"] == lower
            assert lower <= partition["bounds"][outcome]["upper"] <= 1
    assert (
        derived["draw_no_bet"]["home"]["bounds"]["FULL_WIN"]["lower"] - PROBABILITY_TOLERANCE
        <= forecast.home_probability
    )
    assert (
        derived["draw_no_bet"]["home"]["bounds"]["FULL_WIN"]["upper"] + PROBABILITY_TOLERANCE
        >= forecast.home_probability
    )


def test_independent_corner_payload_does_not_require_or_invent_goal_probabilities() -> None:
    corners = CornerForecastPayloadV1("negative_binomial", 5.0, 4.0, 7.5, 5.6, 10.0)
    payload = forecast_payload_dict(None, corners=corners)
    assert payload["match_result"] is None
    assert "goal" not in payload
    assert payload["corners"] == corners.to_dict()
    assert not {"score_matrix", "cards", "players"}.intersection(payload)


def test_products_command_only_reads_supplied_forecast(tmp_path: Path) -> None:
    forecast = _forecast("score-model", MATRIX)
    source = tmp_path / "forecast.json"
    source.write_text(json.dumps(_forecast_dict(forecast)))
    before = source.read_bytes()
    output, errors = io.StringIO(), io.StringIO()
    assert (
        run(
            ["models", "products", "--forecast", str(source)],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert not errors.getvalue()
    assert json.loads(output.getvalue()) == score_products(forecast)
    assert source.read_bytes() == before


@pytest.mark.parametrize("change", [{"status": "MODEL_ERROR"}, {"home_probability": 0.9}])
def test_failed_or_inconsistent_forecast_cannot_be_projected(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        score_products(replace(_forecast("score-model", MATRIX), **change))


@pytest.mark.parametrize(
    "product",
    [
        "CORNERS_DISTRIBUTION",
        "CARDS_DISTRIBUTION",
        "PLAYER_MINUTES",
        "PLAYER_SHOTS",
        "PLAYER_GOALS",
    ],
)
def test_product_metadata_cannot_route_other_families_to_a_goal_model(
    product: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
    from football.forecasting.model_runner import ModelRegistry, ModelRunner
    from football.forecasting.runtime_models import ModelRegistration, load_registered_champion
    from test_feature_snapshots import _input

    entry = ModelRegistration.from_bytes(Path("config/models/current-champion.json").read_bytes())
    artifact = load_registered_champion(entry, Path("."))

    def unexpected_prediction(*args: object) -> None:
        pytest.fail("a goal model must not predict another product")

    monkeypatch.setattr(TransferableRollingGoalsChampion, "predict", unexpected_prediction)
    registry = ModelRegistry.from_registrations(
        (replace(entry, eligible_products=(product,)),),
        (TransferableRollingGoalsChampion(),),
        {entry.artifact_hash: artifact},
        enabled=frozenset((entry.model_id,)),
    )
    result = ModelRunner(registry).run(_input())
    assert result.forecasts == ()
    assert result.availability[0].reason == "PRODUCT_NOT_ELIGIBLE"


def test_unknown_score_labels_are_rejected_instead_of_inventing_exact_scores() -> None:
    with pytest.raises(ValueError, match="labels"):
        score_products(
            replace(_forecast("score-model", MATRIX), score_labels=("zero", "one", "many"))
        )


@pytest.mark.parametrize("payload", [[], {}, {"probabilities": []}])
def test_products_command_reports_invalid_forecast_without_a_traceback(
    payload: object, tmp_path: Path
) -> None:
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(payload))
    output, errors = io.StringIO(), io.StringIO()
    assert (
        run(
            ["models", "products", "--forecast", str(source)],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 4
    )
    assert not output.getvalue()
    assert "invalid score forecast" in errors.getvalue()
