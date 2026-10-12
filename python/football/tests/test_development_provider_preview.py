import pytest
from football.product.development_provider_preview import _lineup_players, _shot_features


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_provider_xg_is_not_silently_consumed(value: float) -> None:
    with pytest.raises(ValueError, match="expected goals"):
        _shot_features({"shots": [{"team_id": "t_home", "expected_goals": value}]})


def test_provider_feature_extractors_preserve_defined_semantics() -> None:
    shots = _shot_features(
        {
            "periods": [
                {
                    "shots": [
                        {"team_id": "t_home", "expected_goals": 0.2, "is_on_target": True},
                        {"team_id": "t_home", "expected_goals": 0.1, "is_on_target": False},
                        {"team_id": "t_away", "expected_goals": 0.4, "is_on_target": True},
                    ]
                }
            ]
        }
    )
    assert shots["shots"] == 3
    assert shots["shots_on_target"] == 2
    assert shots["xg_by_team"] == {"t_home": 0.30000000000000004, "t_away": 0.4}
    assert (
        _lineup_players(
            {"home": {"starters": list(range(11))}, "away": {"starters": list(range(11))}}
        )
        == 22
    )


def test_fotmob_shots_keep_provider_field_definitions() -> None:
    features = _shot_features(
        {"shots": [{"teamId": 8650, "expectedGoals": 0.2, "isOnTarget": True}]},
        provider_code="fotmob",
    )
    assert features["xg_by_team"] == {"8650": 0.2}
    assert features["shots_on_target"] == 1
