from datetime import date

from football.product.external_prediction_sources import (
    collect_sources,
    parse_1960tips,
    parse_matchoutlook,
    parse_r2bet,
    parse_slybet,
)

TARGET_DATE = date(2026, 9, 30)


def test_r2bet_parser_extracts_dated_fixture_and_market() -> None:
    html = """
    <h2>Best Picks</h2><p>30th , Wed Sep 2026</p>
    <article>
      <div data-link="https://r2bet.com/match/1"><p>UEFA U21 Championship</p><p>17:00</p></div>
      <div class="teams"><p>Poland U21</p><svg></svg><p>Sweden U21</p></div>
      <div data-link="https://r2bet.com/match/1"><p>Odds: <span>1.41</span></p>
        <p>Pick: <span>Home(1)</span></p></div>
    </article>
    """

    rows = parse_r2bet(html, TARGET_DATE, "https://r2bet.com/picks")

    assert [(row.competition, row.home_team, row.away_team) for row in rows] == [
        ("UEFA U21 Championship", "Poland U21", "Sweden U21")
    ]
    assert (rows[0].market, rows[0].selection) == ("RESULT_1X2", "HOME_WIN")
    assert rows[0].original_date_text == "30th , Wed Sep 2026"


def test_1960tips_parser_selects_structured_public_tip() -> None:
    html = """
    <h1>Today's Football Predictions — Wed, 30 Sep 2026</h1>
    <div class="caz-b-tip" id="m0-tip-date-1">
      <div class="table-row"><div class="tb-league">ENG NL</div>
        <div class="tb-match">Eastleigh vs Southend United</div>
        <div class="tb-tip">X2</div></div>
    </div>
    """

    rows = parse_1960tips(html, TARGET_DATE, "https://www.1960tips.com/todays-predictions")

    assert len(rows) == 1
    assert (rows[0].competition, rows[0].home_team, rows[0].away_team) == (
        "ENG NL",
        "Eastleigh",
        "Southend United",
    )
    assert (rows[0].market, rows[0].selection) == ("DOUBLE_CHANCE", "DRAW_OR_AWAY")


def test_slybet_parser_emits_each_supported_market() -> None:
    html = """
    <table class="smp-picks-table"><thead><tr><th class="smp-col-date">30.09.26</th></tr></thead>
      <tbody><tr><td class="smp-col-date"><img alt="England" /></td>
        <td class="smp-col-teams"><span class="smp-team1">Eastleigh</span>
          <span class="smp-team2">Southend</span></td>
        <td class="smp-col-1x2">1X</td><td class="smp-col-ou">+2.5</td>
        <td class="smp-col-btts">Yes</td></tr></tbody>
    </table>
    """

    rows = parse_slybet(html, TARGET_DATE, "https://slybet.net/")

    assert {(row.market, row.selection) for row in rows} == {
        ("DOUBLE_CHANCE", "HOME_OR_DRAW"),
        ("TOTAL_GOALS", "TOTAL_OVER_2_5"),
        ("BTTS", "BTTS_YES"),
    }
    assert all(row.competition == "England" for row in rows)


def test_matchoutlook_parser_extracts_supported_public_selections_only() -> None:
    html = """
    <h1>Today's Football Predictions</h1>
    <div id="today-div">
      <div class="match-section"><div class="match-title">UEFA Champions League <b>17:00</b></div>
        <div class="match-content"><b>SK Brann</b><b>vs</b><b>HJK Helsinki</b>
          <b class="our-bet">Best Bet: <b>Home win</b></b></div></div>
      <div class="match-section"><div class="match-title">England National League</div>
        <div class="match-content"><b>Eastleigh</b><b>vs</b><b>Southend</b>
          <b class="our-bet">Best Bet: <b>Over 1.5</b></b></div></div>
      <div class="match-section"><div class="match-title">Egypt Cup <b>18:00</b></div>
        <div class="match-content"><b>Ceramica Cleopatra</b><b>vs</b><b>Al-Masry</b>
          <b class="our-bet">Best Bet: <b>Under 3.5</b></b></div></div>
    </div>
    """

    rows = parse_matchoutlook(
        html, TARGET_DATE, "https://www.matchoutlook.com/todays-football-predictions"
    )

    assert [(row.competition, row.home_team, row.away_team, row.selection) for row in rows] == [
        ("UEFA Champions League", "SK Brann", "HJK Helsinki", "HOME_WIN"),
        ("England National League", "Eastleigh", "Southend", "TOTAL_OVER_1_5"),
        ("Egypt Cup", "Ceramica Cleopatra", "Al-Masry", "TOTAL_UNDER_3_5"),
    ]


def test_collection_isolates_source_failure_and_keeps_forebet_disabled() -> None:
    pages = {
        "r2bet.com": "<h2>Best Picks</h2><p>30th , Wed Sep 2026</p>",
        "slybet.net": "".join(
            (
                '<table class="smp-picks-table">',
                '<th class="smp-col-date">30.09.26</th></table>',
            )
        ),
        "matchoutlook.com": "<html><body>layout changed</body></html>",
    }

    def fetch(url: str) -> str:
        if "1960tips" in url:
            raise OSError("temporary network failure")
        return next(body for host, body in pages.items() if host in url)

    results = collect_sources(TARGET_DATE, fetcher=fetch, today=TARGET_DATE)

    statuses = {result.source_code: result.status for result in results}
    assert statuses == {
        "r2bet": "NO_PREDICTIONS",
        "tips1960": "TECHNICALLY_UNAVAILABLE",
        "slybet": "NO_PREDICTIONS",
        "matchoutlook": "PARSER_BROKEN",
        "forebet": "TECHNICALLY_UNAVAILABLE",
    }


def test_collection_source_filter_fetches_only_requested_source() -> None:
    requested_urls: list[str] = []

    def fetch(url: str) -> str:
        requested_urls.append(url)
        return '<table class="smp-picks-table"><th class="smp-col-date">30.09.26</th></table>'

    results = collect_sources(
        TARGET_DATE, requested_source="slybet", fetcher=fetch, today=TARGET_DATE
    )

    assert [result.source_code for result in results] == ["slybet"]
    assert len(requested_urls) == 1
