"""Independent score-cell and settlement examples for deterministic goal products."""

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from football.cli.main import run
from football.forecasting.model_contracts import ModelForecast
from football.forecasting.multimodel_cli import _forecast_dict
from football.forecasting.products import score_products
from test_forecast_products import MATRIX
from test_multi_model_forecasting import _forecast


def exact_forecast(matrix: tuple[tuple[float, ...], ...] = MATRIX) -> ModelForecast:
    return replace(
        _forecast("score-model", matrix), score_labels=tuple(map(str, range(len(matrix))))
    )


def test_draw_no_bet_margin_and_result_btts_share_the_exact_matrix() -> None:
    forecast = exact_forecast()
    before = _forecast_dict(forecast)
    value = score_products(forecast)["derived_goals"]
    assert value["status"] == "COMPUTED"
    assert value["draw_no_bet"]["home"]["resolved"] == pytest.approx(
        {"FULL_WIN": 0.25, "HALF_WIN": 0, "PUSH": 0.55, "HALF_LOSS": 0, "FULL_LOSS": 0.2}
    )
    assert value["winning_margin"]["resolved"] == pytest.approx(
        {"-2": 0, "-1": 0.2, "0": 0.55, "1": 0.2, "2": 0.05}
    )
    assert value["result_btts"]["resolved"]["DRAW_YES"] == pytest.approx(0.45)
    assert value["result_btts"]["resolved"]["HOME_YES"] == pytest.approx(0.05)
    assert _forecast_dict(forecast) == before


@pytest.mark.parametrize(
    ("margin", "handicap", "outcome"),
    [
        (0, -0.25, "HALF_LOSS"),
        (0, 0.25, "HALF_WIN"),
        (1, -0.75, "HALF_WIN"),
        (1, -1, "PUSH"),
        (1, -1.25, "HALF_LOSS"),
        (1, -1.5, "FULL_LOSS"),
        (1, -0.5, "FULL_WIN"),
    ],
)
def test_signed_asian_lines_split_stake_at_adjacent_half_lines(
    margin: int, handicap: float, outcome: str
) -> None:
    matrix = tuple(tuple(float(h == margin and a == 0) for a in range(3)) for h in range(3))
    value = score_products(exact_forecast(matrix), asian_handicaps=(handicap,))["derived_goals"]
    home = value["asian_handicaps"][0]["home"]["resolved"]
    away = value["asian_handicaps"][0]["away"]["resolved"]
    assert home[outcome] == 1
    opposite = {
        "FULL_WIN": "FULL_LOSS",
        "HALF_WIN": "HALF_LOSS",
        "PUSH": "PUSH",
        "HALF_LOSS": "HALF_WIN",
        "FULL_LOSS": "FULL_WIN",
    }
    assert away[opposite[outcome]] == 1
    assert sum(home.values()) == sum(away.values()) == 1


def test_totals_team_ranges_and_joint_conditions_are_coherent() -> None:
    value = score_products(
        exact_forecast(), goal_lines=(2.25,), european_handicaps=(-1,), goal_ranges=((1, 2),)
    )["derived_goals"]
    totals = value["totals"][0]
    assert totals["total"]["over"]["resolved"] == pytest.approx(
        {"FULL_WIN": 0.25, "HALF_WIN": 0, "PUSH": 0, "HALF_LOSS": 0.30, "FULL_LOSS": 0.45}
    )
    assert totals["home"]["over"]["resolved"]["HALF_LOSS"] == pytest.approx(0.3)
    assert value["goal_ranges"][0]["total"]["resolved"]["INSIDE"] == pytest.approx(0.65)
    assert value["goal_ranges"][0]["home"]["resolved"]["INSIDE"] == pytest.approx(0.7)
    assert value["european_handicaps"][0]["resolved"] == pytest.approx(
        {"HOME": 0.05, "DRAW": 0.2, "AWAY": 0.75}
    )
    joint = value["result_totals"][0]["resolved"]
    assert joint["HOME_OVER"] == pytest.approx(0.05)
    assert joint["DRAW_OVER"] == pytest.approx(0.2)
    assert sum(joint.values()) == pytest.approx(1)
    assert joint["HOME_OVER"] != pytest.approx(0.25 * 0.25)


def test_censored_buckets_do_not_become_exact_handicap_or_margin_atoms() -> None:
    value = score_products(_forecast("legacy", MATRIX), asian_handicaps=(0,))["derived_goals"]
    assert value["status"] == "UNSUPPORTED_CENSORED_SUPPORT"
    assert "draw_no_bet" not in value


@pytest.mark.parametrize(
    "kwargs",
    [
        {"goal_lines": (True,)},
        {"goal_lines": (-0.5,)},
        {"goal_lines": (0.3,)},
        {"asian_handicaps": (float("nan"),)},
        {"asian_handicaps": (float("inf"),)},
        {"european_handicaps": (0.5,)},
        {"european_handicaps": (False,)},
        {"goal_ranges": ((2, 1),)},
        {"goal_ranges": ((True, 2),)},
        {"goal_ranges": ((0, 1.5),)},
    ],
)
def test_invalid_line_and_range_parameters_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        score_products(exact_forecast(), **kwargs)


def test_cli_lines_are_explicit_and_projection_remains_read_only(tmp_path: Path) -> None:
    forecast = exact_forecast()
    source = tmp_path / "forecast.json"
    source.write_text(json.dumps(_forecast_dict(forecast)))
    before = source.read_bytes()
    output, errors = io.StringIO(), io.StringIO()
    assert (
        run(
            [
                "models",
                "products",
                "--forecast",
                str(source),
                "--goal-line",
                "2.25",
                "--asian-handicap",
                "-0.25",
                "--european-handicap",
                "-1",
                "--goal-range",
                "1",
                "2",
            ],
            environ={},
            stdout=output,
            stderr=errors,
        )
        == 0
    )
    assert json.loads(output.getvalue()) == score_products(
        forecast,
        goal_lines=(2.25,),
        asian_handicaps=(-0.25,),
        european_handicaps=(-1,),
        goal_ranges=((1, 2),),
    )
    assert not errors.getvalue()
    assert source.read_bytes() == before


def test_request_order_and_duplicates_do_not_change_projections() -> None:
    forecast = exact_forecast()
    left = score_products(forecast, goal_lines=(3.5, 0, 2.5, 2.5), asian_handicaps=(0, -0.25, 0))
    right = score_products(forecast, goal_lines=(0, 2.5, 3.5), asian_handicaps=(-0.25, 0))
    assert left == right
    totals = left["derived_goals"]["totals"]
    assert totals[0]["total"]["over"]["resolved"]["PUSH"] == pytest.approx(0.1)
    assert totals[-1]["total"]["over"]["resolved"]["FULL_WIN"] == pytest.approx(0.2)
