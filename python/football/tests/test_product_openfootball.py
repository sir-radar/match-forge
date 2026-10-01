from __future__ import annotations

import json
from pathlib import Path

from football.product.openfootball import discover_catalog, parse_competition


def test_discovers_seasons_competitions_and_completed_matches(tmp_path: Path) -> None:
    season = tmp_path / "2025-26"
    season.mkdir()
    (tmp_path / "README.md").write_text("ignored")
    (season / "en.1.json").write_text(
        json.dumps(
            {
                "name": "English Premier League 2025/26",
                "matches": [
                    {
                        "date": "2025-08-16",
                        "time": "15:00",
                        "team1": "Arsenal FC",
                        "team2": "Leeds United",
                        "score": {"ht": [1, 0], "ft": [2, 0]},
                    },
                    {
                        "date": "2025-08-17",
                        "team1": "Liverpool FC",
                        "team2": "Everton FC",
                        "score": {},
                    },
                ],
            }
        )
    )
    catalog = discover_catalog(tmp_path, "a" * 40)
    assert len(catalog) == 1
    assert catalog[0].season == "2025-26"
    assert catalog[0].match_count == 2
    assert catalog[0].completed_match_count == 1

    matches = parse_competition(catalog[0])
    assert len(matches) == 1
    assert matches[0].competition_name == "English Premier League 2025/26"
    assert matches[0].country == "England"
    assert matches[0].division == 1
    assert matches[0].kickoff_precision == "EXACT"
    assert matches[0].kickoff_at.hour == 14
    assert (matches[0].home_goals, matches[0].away_goals) == (2, 0)


def test_parses_calendar_season_date_only_and_team_objects(tmp_path: Path) -> None:
    season = tmp_path / "2026"
    season.mkdir()
    source = season / "br.1.json"
    source.write_text(
        json.dumps(
            {
                "name": "Brasileirao 2026",
                "matches": [
                    {
                        "date": "2026-03-02",
                        "team1": {"name": "Flamengo"},
                        "team2": {"name": "Palmeiras"},
                        "score": {"ft": [1, 1]},
                    }
                ],
            }
        )
    )
    match = parse_competition(discover_catalog(tmp_path, "b" * 40)[0])[0]
    assert match.season == "2026"
    assert match.country == "Brazil"
    assert match.kickoff_precision == "DATE_ONLY"
    assert match.kickoff_at.hour == 23
