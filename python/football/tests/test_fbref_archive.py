from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def page(*, epoch: str = 'data-venue-epoch="1505502000"', match: str = "00836893") -> str:
    return f"""<link rel="canonical" href="https://fbref.com/en/matches/{match}/Match-Report">
    <div class="scorebox"><div><a href="/en/squads/4ba7cbea/2017-2018/Team">Home</a>
    <div class="score">2</div></div><div><a href="/en/squads/d07537b9/2017-2018/Team">Away</a>
    <div class="score">1</div></div><span data-venue-date="2017-09-15" {epoch}></span>
    <a href="/en/comps/9/2017-2018/League">Premier League</a></div>
    <table id="stats_4ba7cbea_summary"><tbody><tr>
    <th data-stat="player" data-append-csv="f1e8372d">
    <a href="/en/players/f1e8372d/Player">Player</a></th>
    <td data-stat="minutes">90</td><td data-stat="goals">0</td>
    <td data-stat="shots_on_target">0</td><td data-stat="shots"></td>
    <td data-stat="passes_completed">15</td><td data-stat="tackles">2</td>
    </tr></tbody><tfoot><tr><td data-stat="goals">99</td></tr></tfoot></table>"""


def normalize(html: str, *, season: str | None = None) -> NormalizationResult:
    raw = html.encode()
    now = datetime(2026, 11, 2, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "fbref", None, UUID(int=1), UUID(int=2), hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="archive/" + "a" * 64 + "/matches/00836893.html",
        fixture_native_id="00836893",
        season_label=season,
    )
    return normalize_resource(context, "archived_match_html", raw)


def test_original_match_tables_keep_native_ids_minutes_and_utc_separate() -> None:
    result = normalize(page())
    players = [o.to_dict() for o in result.observations if o.CONTRACT == "PlayerObservationV2"]
    assert len(players) == 1
    player = players[0]["player"]
    assert isinstance(player, dict) and player["provider_native_id"] == "f1e8372d"
    stats = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "PlayerStatisticObservationV3"
    )
    assert stats["minutes_played"] == 90
    assert stats["goals"] == stats["shots_on_target"] == 0
    assert stats["shots"] is None
    fixture = next(o.to_dict() for o in result.observations if o.CONTRACT == "FixtureObservationV2")
    assert fixture["kickoff_at"] == "2017-09-15T19:00:00+00:00"
    assert fixture["kickoff_precision"] == "EXACT"
    assert fixture["status"] == "UNKNOWN"
    assert all(o.time.known_at == datetime(2026, 11, 2, tzinfo=UTC) for o in result.observations)


def test_naive_venue_date_does_not_become_exact_utc() -> None:
    result = normalize(page(epoch=""))
    fixture = next(o.to_dict() for o in result.observations if o.CONTRACT == "FixtureObservationV2")
    assert fixture["kickoff_precision"] == "DATE_ONLY"


def test_canonical_mismatch_and_conflicting_player_ids_are_rejected() -> None:
    assert not normalize(page(match="ffffffff")).observations
    result = normalize(page().replace("/en/players/f1e8372d/", "/en/players/ffffffff/"))
    assert not result.observations
    assert result.findings


def test_comment_tables_parse_as_data_without_script_execution() -> None:
    html = page()
    start = html.index("<table")
    html = html[:start] + "<!--" + html[start:] + '--><script>throw new Error("never run")</script>'
    result = normalize(html)
    assert any(o.CONTRACT == "PlayerObservationV2" for o in result.observations)


def test_short_competition_url_keeps_missing_season_unknown() -> None:
    html = page().replace("/en/comps/9/2017-2018/League", "/en/comps/9/Premier-League-Stats")
    result = normalize(html)
    fixture = next(o.to_dict() for o in result.observations if o.CONTRACT == "FixtureObservationV2")
    assert fixture["season_label"] is None
    assert any("SEASON_LABEL_UNVERIFIED" in f.rule_code for f in result.findings)
    assert not normalize(html, season="2017-2018").observations
