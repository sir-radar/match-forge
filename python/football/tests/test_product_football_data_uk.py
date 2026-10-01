from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime

from football.product.football_data_uk import (
    _is_closed_season,
    csv_members,
    discover_resources,
    parse_csv_resource,
)


def test_closed_seasons_can_skip_unchanged_remote_archives() -> None:
    observed_at = datetime(2026, 9, 30, tzinfo=UTC)
    assert _is_closed_season("2025-2026", observed_at)
    assert not _is_closed_season("2026-2027", observed_at)
    assert not _is_closed_season(None, observed_at)


def test_discovers_csv_and_zip_without_hardcoded_catalog() -> None:
    html = b"""
    <a href="mmz4281/2526/E0.csv">Premier League</a>
    <a href="datazip/2526/England.zip">England archive</a>
    <a href="notes.txt">notes</a>
    """
    resources = discover_resources(html)
    assert [resource.archive for resource in resources] == [True, False]
    csv_resource = next(resource for resource in resources if not resource.archive)
    assert csv_resource.season == "2025-2026"
    assert csv_resource.division == "E0"


def test_csv_parser_handles_bom_old_dates_time_and_incomplete_rows() -> None:
    payload = (
        "\ufeffDiv,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
        "E0,16/08/25,15:00,Arsenal,Leeds,2,0,H,1,0,H\n"
        "E0,17/08/2025,,Liverpool,Everton,1,1,D,0,0,D\n"
        "E0,18/08/2025,,Chelsea,Fulham,,,,,,\n"
    ).encode()
    matches = parse_csv_resource(
        payload,
        source_path="mmz4281/2526/E0.csv",
        season="2025-2026",
    )
    assert len(matches) == 2
    assert matches[0].kickoff_precision == "EXACT"
    assert matches[0].kickoff_at.hour == 14
    assert matches[1].kickoff_precision == "DATE_ONLY"
    assert matches[0].competition_name == "Premier League"
    assert matches[0].country == "England"


def test_zip_archive_yields_every_csv() -> None:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("E0.csv", "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        archive.writestr("nested/E1.csv", "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\n")
        archive.writestr("notes.txt", "ignored")
    assert [name for name, _ in csv_members(target.getvalue())] == ["E0.csv", "nested/E1.csv"]


def test_csv_parser_accepts_legacy_windows_encoding() -> None:
    payload = ("Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nF1,01/08/2004,N\u00eemes,Lyon,0,1\n").encode(
        "cp1252"
    )
    matches = parse_csv_resource(payload, source_path="legacy/F1.csv", season="2004-2005")
    assert matches[0].home_team_name == "N\u00eemes"
