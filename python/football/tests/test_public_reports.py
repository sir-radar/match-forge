"""Invalid stored comparisons cannot become published probability claims."""

from typing import Any

import pytest
from football.product.public_reports import _comparison


@pytest.mark.parametrize(
    "values",
    [{"home": True}, {"home": "0.6"}, {"home": float("nan")}, {"home": 1.1}, [0.6, 0.2, 0.2]],
)
def test_malformed_comparison_probabilities_are_rejected(values: Any) -> None:
    with pytest.raises(ValueError, match="comparison probabilities"):
        _comparison({"market": "RESULT_1X2", "selection": "HOME_WIN", "probabilities": values})


def test_no_forecast_remains_explicitly_unable_to_evaluate() -> None:
    assert _comparison(
        {
            "prediction_id": "prediction",
            "forecast_id": None,
            "market": "RESULT_1X2",
            "selection": "HOME_WIN",
            "probabilities": None,
        }
    ) == {
        "prediction_id": "prediction",
        "forecast_id": None,
        "matchforge_probability": None,
        "agreement": "UNABLE_TO_EVALUATE",
    }
