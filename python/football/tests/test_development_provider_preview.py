from football.product.development_provider_preview import _lineup_players, _shot_features


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
