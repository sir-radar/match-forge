from __future__ import annotations

from football.product.live_resources import normalize_events, normalize_statistics


def test_pitchapi_goals_keep_zero_pre_event_score_out_of_contract() -> None:
    result = normalize_events(
        "pitchapi",
        "m_123456",
        {
            "events": [
                {
                    "event_type": "goal",
                    "minute": 30,
                    "minute_added": 0,
                    "period": "FirstHalf",
                    "team_id": "t_home01",
                    "player": {"id": "p_123456", "name": "Scorer"},
                    "score_home": 0,
                    "score_away": 0,
                    "is_penalty": True,
                    "is_own_goal": False,
                }
            ]
        },
        home_provider_team_id="t_home01",
        away_provider_team_id="t_away01",
    )
    assert result["events"][0] == {
        "id": result["events"][0]["id"],
        "provider_event_id": result["events"][0]["provider_event_id"],
        "type": "GOAL",
        "team_side": "HOME",
        "provider_team_id": "t_home01",
        "player_id": "p_123456",
        "player_name": "Scorer",
        "minute": 30,
        "added_time": 0,
        "period": "FirstHalf",
        "own_goal": False,
        "penalty": True,
        "disallowed": False,
    }


def test_fotmob_events_exclude_shootout_and_preserve_missing_scorer() -> None:
    result = normalize_events(
        "fotmob",
        "123",
        {
            "events": [
                {
                    "eventId": 1,
                    "type": "Goal",
                    "time": 45,
                    "overloadTime": 2,
                    "isHome": True,
                    "ownGoal": True,
                },
                {
                    "eventId": 2,
                    "type": "Goal",
                    "time": 120,
                    "isHome": False,
                    "isPenaltyShootoutEvent": True,
                },
                {"eventId": 3, "type": "Card", "card": "Red", "time": 70, "isHome": False},
            ]
        },
        home_provider_team_id="10",
        away_provider_team_id="20",
    )
    assert [event["type"] for event in result["events"]] == ["GOAL", "RED_CARD"]
    assert result["events"][0]["player_name"] is None
    assert result["events"][0]["added_time"] == 2
    assert result["events"][0]["own_goal"] is True


def test_statistics_preserve_zero_missing_periods_and_provider_xg() -> None:
    result = normalize_statistics(
        "pitchapi",
        {
            "periods": [
                {
                    "period": "All",
                    "groups": [
                        {
                            "items": [
                                {
                                    "key": "expected_goals",
                                    "title": "Expected goals (xG)",
                                    "home": "0",
                                    "away": "1.25",
                                },
                                {
                                    "key": "total_shots",
                                    "title": "Total shots",
                                    "home": None,
                                    "away": "8",
                                },
                            ]
                        }
                    ],
                },
                {
                    "period": "FirstHalf",
                    "groups": [
                        {
                            "items": [
                                {"key": "corners", "title": "Corners", "home": "0", "away": "2"}
                            ]
                        }
                    ],
                },
            ]
        },
    )
    stats = {(row["period"], row["metric"]): row for row in result["statistics"]}
    assert stats[("FULL_MATCH", "expected_goals")]["home"] == 0.0
    assert stats[("FULL_MATCH", "total_shots")]["home"] is None
    assert stats[("FIRST_HALF", "corners")]["away"] == 2.0


def test_events_deduplicate_stable_provider_identity_and_keep_disallowed_goal() -> None:
    goal = {
        "id": "event-1",
        "event_type": "goal",
        "minute": 51,
        "team_id": "t_home01",
        "player": {"id": "p_1", "name": "Scorer"},
    }
    result = normalize_events(
        "pitchapi",
        "m_123456",
        {"events": [goal, goal, {**goal, "id": "event-2", "event_type": "disallowed_goal"}]},
        home_provider_team_id="t_home01",
        away_provider_team_id="t_away01",
    )
    assert [(event["id"], event["type"], event["disallowed"]) for event in result["events"]] == [
        ("pitchapi:event-1", "GOAL", False),
        ("pitchapi:event-2", "DISALLOWED_GOAL", True),
    ]


def test_synthetic_event_identity_does_not_change_when_provider_order_changes() -> None:
    goal = {
        "event_type": "goal",
        "minute": 30,
        "team_id": "t_home01",
        "player": {"id": "p_1", "name": "Scorer"},
    }
    substitution = {"event_type": "substitution", "minute": 20, "team_id": "t_home01"}
    inputs = ([goal], [substitution, goal])
    identities = []
    for events in inputs:
        normalized = normalize_events(
            "pitchapi",
            "m_123456",
            {"events": events},
            home_provider_team_id="t_home01",
            away_provider_team_id="t_away01",
        )
        identities.append(
            next(event["id"] for event in normalized["events"] if event["type"] == "GOAL")
        )
    assert identities[0] == identities[1]
