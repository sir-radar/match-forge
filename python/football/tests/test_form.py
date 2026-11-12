"""Form windows follow one policy. Seed cases are synthetic rows shaped like reported matches."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from football.product.form import STALE_AFTER, WINDOWS, team_form, window_matches
from football.product.public_context import context_features

KICKOFF = datetime(2026, 11, 10, 18, tzinfo=UTC)
LEAGUE, CUP, FRIENDLY = "league", "cup", "friendly"


def _at(days: float) -> str:
    return (KICKOFF - timedelta(days=days)).isoformat()


def played(
    fid: str, days: float, home: str, away: str, hg: int, ag: int, **extra: Any
) -> dict[str, Any]:
    return {
        "fixture_id": fid,
        "competition_id": extra.get("competition_id", LEAGUE),
        "home_team_id": home,
        "away_team_id": away,
        "home_team": home.title(),
        "away_team": away.title(),
        "kickoff_at": _at(days),
        "home_goals": hg,
        "away_goals": ag,
        "home_xg": None,
        "away_xg": None,
        "source_kickoff_precision": extra.get("precision", "EXACT"),
    }


def result(
    fid: str,
    days: float,
    home: str,
    away: str,
    hg: int,
    ag: int,
    status: str = "FINISHED",
    basis: str = "REGULATION_90",
    competition_id: str = LEAGUE,
) -> dict[str, Any]:
    return {
        "fixture_id": fid,
        "competition_id": competition_id,
        "home_team_id": home,
        "away_team_id": away,
        "home_team": home.title(),
        "away_team": away.title(),
        "kickoff_at": _at(days),
        "status": status,
        "home_goals": hg,
        "away_goals": ag,
        "score_basis": basis,
    }


def source(
    history: Sequence[dict[str, Any]] = (),
    results: Sequence[dict[str, Any]] = (),
    pending: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "fixture_id": "target",
        "competition_id": LEAGUE,
        "kickoff_at": KICKOFF.isoformat(),
        "home_team_id": "team",
        "away_team_id": "other",
        "history": list(history),
        "results": list(results),
        "pending_results": list(pending),
        "competition_scopes": {LEAGUE: "LEAGUE", CUP: "CUP", FRIENDLY: "FRIENDLY"},
        "coaches": [],
        "upcoming": [],
        "form_policy_version": "form-policy-v1",
    }


def windows(src: dict[str, Any], team: str = "team") -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = team_form(src, team)["windows"]
    return result


def test_withdrawn_team_official_form_includes_walkovers_but_played_form_does_not() -> None:
    # Shaped like the Sergipano A2 seed: recent results are awarded 3-0 losses,
    # the played history the product held was a year older.
    old = [played(f"p{i}", 370 + i * 3, "team", f"o{i}", 2, 1) for i in range(5)]
    awarded = [
        result(f"a{i}", 3 + i * 4, f"x{i}", "team", 3, 0, status="AWARDED", basis="UNKNOWN")
        for i in range(4)
    ]
    src = source(
        old, awarded + [result(f"p{i}", 370 + i * 3, "team", f"o{i}", 2, 1) for i in range(5)]
    )
    form = windows(src)
    assert form["OFFICIAL_ALL_5"]["results"] == "LLLLW"
    assert form["OFFICIAL_ALL_5"]["fixture_ids"][:4] == ["a0", "a1", "a2", "a3"]
    assert "AWARDED_INCLUDED" in form["OFFICIAL_ALL_5"]["flags"]
    assert form["PLAYED_ALL_5"]["results"] == "WWWWW"
    assert "STALE" in form["PLAYED_ALL_5"]["flags"]
    assert form["FORECAST_ELIGIBLE_ALL_5"]["fixture_ids"] == [f"p{i}" for i in range(5)]


def test_recent_unqualified_results_win_over_old_history_and_are_flagged() -> None:
    # Shaped like the Persha Liga seed: 2026 league results existed only as
    # canonical fixtures while 2025 history filled the window.
    old = [played(f"h{i}", 500 + i, "team", f"o{i}", 1, 0) for i in range(5)]
    recent = [
        result("r0", 9, "y", "team", 3, 1),
        result("r1", 12, "team", "e", 1, 2, competition_id=CUP),
        result("r2", 39, "s", "team", 3, 2, basis="UNKNOWN"),
    ]
    form = windows(source(old, recent))
    official = form["OFFICIAL_ALL_5"]
    assert official["results"] == "LLLWW" and official["coverage"] == "COMPLETE"
    assert {"UNQUALIFIED_RESULT", "UNKNOWN_SCORE_BASIS"} <= set(official["flags"])
    assert form["OFFICIAL_COMPETITION_5"]["fixture_ids"][:2] == ["r0", "r2"]
    # Played-only form excludes the UNKNOWN-basis unqualified row.
    assert "r2" not in form["PLAYED_ALL_5"]["fixture_ids"]
    assert form["FORECAST_ELIGIBLE_ALL_5"]["fixture_ids"] == [f"h{i}" for i in range(5)]


def test_reserve_and_first_team_are_different_opponents_and_cup_is_not_league() -> None:
    # Shaped like the Lithuania seed: a league match against a reserve side and
    # a cup tie against its first team nine days apart.
    rows = [
        result("cup", 30, "team", "zalgiris", 0, 3, competition_id=CUP),
        result("league", 39, "team", "zalgiris-ii", 5, 0),
    ]
    form = team_form(source((), rows), "team")
    matches = {row["fixture_id"]: row for row in form["matches"]}
    assert matches["cup"]["opponent_id"] != matches["league"]["opponent_id"]
    assert form["windows"]["OFFICIAL_ALL_5"]["results"] == "LW"
    assert form["windows"]["OFFICIAL_COMPETITION_5"]["results"] == "W"


def test_team_perspective_venue_and_home_away_windows() -> None:
    rows = [result("h", 3, "team", "a", 2, 0), result("a", 6, "b", "team", 2, 0)]
    form = team_form(source((), rows), "team")
    assert form["windows"]["OFFICIAL_ALL_5"]["results"] == "WL"
    assert form["windows"]["OFFICIAL_HOME_5"]["fixture_ids"] == ["h"]
    assert form["windows"]["OFFICIAL_AWAY_5"]["fixture_ids"] == ["a"]
    assert [row["venue"] for row in window_matches(form, "OFFICIAL_ALL_5")] == ["HOME", "AWAY"]


def test_penalty_shootout_is_a_draw_on_the_after_extra_time_score() -> None:
    rows = [
        result("pen", 2, "team", "x", 1, 1, basis="PENALTY_SHOOTOUT", competition_id=CUP),
        result("aet", 5, "team", "y", 2, 1, basis="EXTRA_TIME", competition_id=CUP),
    ]
    assert windows(source((), rows))["OFFICIAL_ALL_5"]["results"] == "DW"


def test_friendlies_never_count() -> None:
    rows = [
        result("f", 1, "team", "x", 0, 4, competition_id=FRIENDLY),
        result("l", 2, "team", "y", 1, 0),
    ]
    form = windows(source((), rows))
    for key in ("OFFICIAL_ALL_5", "PLAYED_ALL_5"):
        assert form[key]["fixture_ids"] == ["l"]


def test_last_ten_and_partial_coverage_never_fill_with_invented_matches() -> None:
    rows = [result(f"r{i}", i + 1, "team", f"o{i}", 1, 0) for i in range(7)]
    form = windows(source((), rows))
    assert (
        form["OFFICIAL_ALL_10"]["actual"] == 7 and form["OFFICIAL_ALL_10"]["coverage"] == "PARTIAL"
    )
    assert form["OFFICIAL_ALL_5"]["coverage"] == "COMPLETE"
    assert windows(source())["OFFICIAL_ALL_5"]["coverage"] == "EMPTY"


def test_same_day_date_only_ordering_is_flagged_and_stable() -> None:
    history = [
        played("b", 3.2, "team", "x", 1, 0, precision="DATE_ONLY"),
        played("a", 3.1, "team", "y", 0, 1, precision="DATE_ONLY"),
    ]
    history[0]["kickoff_at"] = history[1]["kickoff_at"] = _at(3)[:10] + "T00:00:00+00:00"
    first = windows(source(history))["PLAYED_ALL_5"]
    second = windows(source(list(reversed(history))))["PLAYED_ALL_5"]
    assert first == second and first["fixture_ids"] == ["a", "b"]
    assert "ORDER_AMBIGUOUS" in first["flags"]


def test_pending_result_inside_the_window_is_flagged() -> None:
    rows = [result(f"r{i}", 10 + i, "team", f"o{i}", 1, 0) for i in range(5)]
    pending = [
        {"team_id": "team", "fixture_id": "late", "kickoff_at": _at(4), "status": "SCHEDULED"}
    ]
    form = windows(source((), rows, pending))
    assert "RESULT_PENDING" in form["OFFICIAL_ALL_5"]["flags"]


def test_stale_threshold() -> None:
    fresh = windows(source((), [result("r", STALE_AFTER.days - 1, "team", "x", 1, 0)]))
    stale = windows(source((), [result("r", STALE_AFTER.days + 1, "team", "x", 1, 0)]))
    assert "STALE" not in fresh["OFFICIAL_ALL_5"]["flags"]
    assert "STALE" in stale["OFFICIAL_ALL_5"]["flags"]


def test_disagreeing_official_and_played_scores_are_flagged_not_merged() -> None:
    src = source([played("m", 2, "team", "x", 0, 0)], [result("m", 2, "team", "x", 1, 0)])
    window = windows(src)["OFFICIAL_ALL_5"]
    assert window["results"] == "W" and "SCORE_CONFLICT" in window["flags"]
    assert windows(src)["PLAYED_ALL_5"]["results"] == "D"


def test_awarded_after_play_keeps_the_official_result_and_on_field_score() -> None:
    src = source(
        [played("m", 2, "team", "x", 2, 2)],
        [result("m", 2, "team", "x", 0, 3, status="AWARDED", basis="UNKNOWN")],
    )
    form = team_form(src, "team")
    assert form["windows"]["OFFICIAL_ALL_5"]["results"] == "L"
    assert form["matches"][0]["result_class"] == "AWARDED_AFTER_PLAY"
    assert form["windows"]["PLAYED_ALL_5"]["results"] == "D"


def test_every_window_fingerprint_changes_only_with_its_selection() -> None:
    rows = [result(f"r{i}", i + 1, "team", f"o{i}", 1, 0) for i in range(12)]
    base = windows(source((), rows))
    extra = windows(source((), [*rows, result("old", 300, "team", "z", 0, 9)]))
    assert base["OFFICIAL_ALL_5"]["fingerprint"] == extra["OFFICIAL_ALL_5"]["fingerprint"]
    assert set(base) == set(WINDOWS)


def test_context_report_serves_default_window_and_played_statistics() -> None:
    src = source(
        [played(f"p{i}", 400 + i, "team", f"o{i}", 2, 0) for i in range(5)],
        [
            result(f"a{i}", 3 + i, "team", f"x{i}", 0, 3, status="AWARDED", basis="UNKNOWN")
            for i in range(5)
        ],
    )
    report = context_features(src)
    assert "".join(row["result"] for row in report["home_form"]) == "LLLLL"
    assert report["form"]["order"] == "NEWEST_FIRST"
    assert report["form"]["home"]["windows"]["OFFICIAL_ALL_5"]["results"] == "LLLLL"
    # Goal averages use on-field history only, never walkover goals.
    assert report["home_team_statistics"]["average_goals_for"] == 2.0


def test_context_rejects_a_source_built_for_another_policy() -> None:
    src = source()
    src["form_policy_version"] = "form-policy-v0"
    with pytest.raises(ValueError, match="form policy"):
        context_features(src)
