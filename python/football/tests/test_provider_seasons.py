from datetime import UTC, datetime

import pytest
from football.product.operational_provider_sync import _fotmob_season_rows
from football.product.provider_history_scopes import normalize_seasons
from football.providers.fotmob import FotmobResponse


def test_seasons_preserve_competition_specific_depth_and_deduplicate_aliases() -> None:
    assert normalize_seasons(["1999/00", "1999/2000", "2026-27", 2010, " 2020 "]) == [
        "2026/2027",
        "2020",
        "2010",
        "1999/2000",
    ]
    assert normalize_seasons(["2025/2026"]) == ["2025/2026"]


@pytest.mark.parametrize("values", [None, [], [True], [None], [""], ["2022/2020"], ["current"]])
def test_invalid_advertised_seasons_fail_before_enqueue(values: object) -> None:
    with pytest.raises(ValueError):
        normalize_seasons(values)


def test_advertised_empty_fotmob_season_stays_empty() -> None:
    response = FotmobResponse(
        "league",
        datetime.now(UTC),
        "0" * 64,
        b"{}",
        {"details": {"id": 47, "selectedSeason": "1999/00"}, "fixtures": {"allMatches": []}},
    )
    assert _fotmob_season_rows(response, "47", "1999/2000") == ()


def test_multi_year_qualification_seasons_are_not_forced_into_annual_leagues() -> None:
    assert normalize_seasons(["2024/2026", "2022/2026"]) == ["2024/2026", "2022/2026"]


@pytest.mark.parametrize("league,season", [(48, "2020/2021"), (47, "2026/2027")])
def test_fotmob_rejects_competition_or_season_substitution(league: int, season: str) -> None:
    response = FotmobResponse(
        "league",
        datetime.now(UTC),
        "0" * 64,
        b"{}",
        {"details": {"id": league, "selectedSeason": season}, "fixtures": {"allMatches": []}},
    )
    with pytest.raises(ValueError):
        _fotmob_season_rows(response, "47", "2020/2021")
