"""Original archived match HTML; no current-feed or historical-eligibility grant."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    FixtureObservationV2,
    PlayerObservationV2,
    PlayerStatisticObservationV2,
    ResultObservationV2,
    TeamObservationV2,
)
from football.contracts.observations_v3 import PlayerStatisticObservationV3
from football.providers.normalization.common import ObservationCollector, count, required_text
from football.providers.normalization.measurements import measurement, statistic_contract

PLAYER_FIELDS = {
    "minutes": "minutes_played",
    "goals": "goals",
    "assists": "assists",
    "shots": "shots",
    "shots_on_target": "shots_on_target",
    "cards_yellow": "yellow_cards",
    "cards_red": "red_cards",
    "passes": "passes",
    "passes_completed": "accurate_passes",
    "tackles": "tackles",
    "interceptions": "interceptions",
    "xg": "expected_goals",
    "xg_assist": "expected_assists",
}
METADATA_FIELDS = {"player", "shirtnumber", "nationality", "position", "age", "_player_id"}


class _MatchPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonical: list[str] = []
        self.div_depth = 0
        self.scorebox: int | None = None
        self.capture: tuple[str, str, str] | None = None
        self.captured: list[str] = []
        self.teams: list[tuple[str, str]] = []
        self.competitions: list[tuple[str, str, str]] = []
        self.scores: list[str] = []
        self.epoch: str | None = None
        self.venue_date: str | None = None
        self.tables: list[tuple[str, list[dict[str, str]]]] = []
        self.table: str | None = None
        self.rows: list[dict[str, str]] = []
        self.in_body = False
        self.row: dict[str, str] | None = None
        self.cell: str | None = None
        self.cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "div":
            self.div_depth += 1
            if "scorebox" in values.get("class", "").split():
                self.scorebox = self.div_depth
        self._metadata(tag, values)
        self._table_start(tag, values)

    def _metadata(self, tag: str, values: dict[str, str]) -> None:
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical.append(values.get("href", ""))
        if self.scorebox is None:
            return
        if "data-venue-date" in values:
            self.venue_date = values["data-venue-date"]
            self.epoch = values.get("data-venue-epoch")
        if tag == "div" and values.get("class") == "score":
            self.capture, self.captured = ("div", "score", ""), []
        if tag == "a":
            path = values.get("href", "")
            team = re.match(r"^/en/squads/([a-f0-9]{8})/", path)
            competition = re.match(r"^/en/comps/([1-9][0-9]*)/([0-9]{4}-[0-9]{4})/", path)
            if team:
                self.capture, self.captured = ("a", "team", team[1]), []
            elif competition:
                self.capture, self.captured = (
                    ("a", "competition", competition[1] + "/" + competition[2]),
                    [],
                )

    def _table_start(self, tag: str, values: dict[str, str]) -> None:
        if tag == "table":
            native = re.fullmatch(r"stats_([a-f0-9]{8})_summary", values.get("id", ""))
            self.table, self.rows = (native[1] if native else None), []
        if self.table is None:
            return
        if tag == "tbody":
            self.in_body = True
        if tag == "tr" and self.in_body:
            self.row = {}
        if self.row is not None:
            self._cell_start(tag, values)

    def _cell_start(self, tag: str, values: dict[str, str]) -> None:
        assert self.row is not None
        if tag in ("th", "td"):
            self.cell, self.cell_text = values.get("data-stat"), []
            if self.cell == "player" and values.get("data-append-csv"):
                self._player_id(values["data-append-csv"])
        if tag == "a" and self.cell == "player":
            native = re.match(r"^/en/players/([a-f0-9]{8})/", values.get("href", ""))
            if native:
                self._player_id(native[1])

    def _player_id(self, native: str) -> None:
        assert self.row is not None
        if not re.fullmatch(r"[a-f0-9]{8}", native):
            raise ValueError("FBref player identifier is invalid")
        if self.row.get("_player_id", native) != native:
            raise ValueError("FBref player link conflicts with its table identifier")
        self.row["_player_id"] = native

    def handle_data(self, data: str) -> None:
        if self.capture is not None:
            self.captured.append(data)
        if self.cell is not None:
            self.cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        self._metadata_end(tag)
        if tag in ("th", "td") and self.row is not None and self.cell is not None:
            if self.cell in self.row:
                raise ValueError("FBref summary row repeats a field")
            self.row[self.cell] = "".join(self.cell_text).strip()
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        if tag == "tbody":
            self.in_body = False
        if tag == "table" and self.table is not None:
            self.tables.append((self.table, self.rows))
            self.table = None

    def _metadata_end(self, tag: str) -> None:
        if self.capture is not None and tag == self.capture[0]:
            _, kind, native = self.capture
            text = "".join(self.captured).strip()
            if kind == "team":
                self.teams.append((native, text))
            elif kind == "competition":
                competition, season = native.split("/")
                self.competitions.append((competition, season, text))
            else:
                self.scores.append(text)
            self.capture = None
        if tag == "div":
            if self.div_depth == self.scorebox:
                self.scorebox = None
            self.div_depth -= 1

    def handle_comment(self, data: str) -> None:
        if "<table" in data:
            child = _MatchPage()
            child.feed(data)
            child.close()
            self.tables.extend(child.tables)


def _kickoff(page: _MatchPage) -> tuple[datetime, str]:
    if page.epoch is not None:
        if not re.fullmatch(r"[0-9]+", page.epoch):
            raise ValueError("FBref venue epoch is not an integer")
        try:
            return datetime.fromtimestamp(int(page.epoch), UTC), "EXACT"
        except (OverflowError, OSError) as error:
            raise ValueError("FBref venue epoch is invalid") from error
    if page.venue_date is None:
        raise ValueError("FBref archive has no observed kickoff date")
    day = date.fromisoformat(page.venue_date)
    return datetime(day.year, day.month, day.day, tzinfo=UTC), "DATE_ONLY"


def archived_match_html(output: ObservationCollector, payload: object) -> None:
    if not isinstance(payload, bytes):
        raise ValueError("FBref archived match requires retained HTML bytes")
    page = _MatchPage()
    page.feed(payload.decode("utf-8"))
    page.close()
    expected = output.context.fixture_native_id
    if len(page.canonical) != 1:
        raise ValueError("FBref archive requires one original canonical match URL")
    url = urlsplit(page.canonical[0])
    native = re.match(r"^/en/matches/([a-f0-9]{8})/", url.path)
    if (url.scheme, url.netloc) != ("https", "fbref.com") or not native or native[1] != expected:
        raise ValueError("FBref original URL conflicts with requested native match")
    if len(page.teams) != 2 or len({team[0] for team in page.teams}) != 2:
        raise ValueError("FBref scorebox requires distinct home and away native teams")
    if len(page.competitions) != 1:
        raise ValueError("FBref scorebox requires one source competition/season")
    competition, season, name = page.competitions[0]
    if output.context.competition_native_id not in (
        None,
        competition,
    ) or output.context.season_label not in (None, season):
        raise ValueError("FBref competition/season conflicts with requested scope")
    kickoff, precision = _kickoff(page)
    if not page.tables or len({team for team, _ in page.tables}) != len(page.tables):
        raise ValueError("FBref archive has missing or duplicate native summary tables")
    if any(team not in {row[0] for row in page.teams} for team, _ in page.tables):
        raise ValueError("FBref summary team conflicts with the match scorebox")
    _match(output, page, competition, season, name, kickoff, precision)
    for team, rows in page.tables:
        _players(output, team, rows)


def _match(
    output: ObservationCollector,
    page: _MatchPage,
    competition: str,
    season: str,
    name: str,
    kickoff: datetime,
    precision: str,
) -> None:
    comp = output.context.reference(competition, "html:scorebox/competition")
    teams = [
        output.context.reference(native, "html:scorebox/team/" + str(index))
        for index, (native, _) in enumerate(page.teams)
    ]
    for ref, (_, label) in zip(teams, page.teams, strict=True):
        output.emit(
            TeamObservationV2,
            ref.source_record_key or "",
            ref.provider_native_id,
            team=ref,
            name=required_text(label),
        )
    output.emit(
        CompetitionObservationV2,
        "html:scorebox/competition",
        competition,
        competition=comp,
        name=required_text(name),
        season_label=season,
    )
    output.emit(
        FixtureObservationV2,
        "html:scorebox",
        output.context.fixture_native_id,
        fixture=output.context.fixture(),
        competition=comp,
        home_team=teams[0],
        away_team=teams[1],
        kickoff_at=kickoff,
        kickoff_precision=precision,
        status="UNKNOWN",
        season_label=season,
    )
    output.finding(
        "MATCH_STATUS_UNVERIFIED",
        "html:scorebox",
        "Archived scorebox does not establish final status or settlement",
        severity="WARNING",
    )
    if len(page.scores) == 2:
        output.emit(
            ResultObservationV2,
            "html:scorebox/score",
            fixture=output.context.fixture(),
            status="UNKNOWN",
            score_basis="UNKNOWN",
            home_goals=count(page.scores[0]),
            away_goals=count(page.scores[1]),
        )


def _players(output: ObservationCollector, native_team: str, rows: list[dict[str, str]]) -> None:
    table = "html:stats_" + native_team + "_summary"
    team = output.context.reference(native_team, table)
    seen: set[str] = set()
    vocabulary = {key.replace("_", ""): target for key, target in PLAYER_FIELDS.items()}
    for index, row in enumerate(rows):
        path = table + "/tbody/" + str(index)
        with output.record(path):
            native = required_text(row.get("_player_id"))
            if native in seen:
                raise ValueError("FBref native player occurs twice in one summary table")
            seen.add(native)
            player = output.context.reference(native, path + "/player")
            values: dict[str, Any] = {}
            for field, value in row.items():
                if field in METADATA_FIELDS:
                    continue
                parsed = measurement(output, field, value, path + "/" + field, vocabulary)
                if parsed is not None:
                    values[parsed[0]] = parsed[1]
            output.emit(
                PlayerObservationV2,
                path + "/player",
                native,
                player=player,
                team=team,
                name=required_text(row.get("player")),
            )
            if values:
                output.emit(
                    statistic_contract(
                        values, PlayerStatisticObservationV2, PlayerStatisticObservationV3
                    ),
                    path,
                    fixture=output.context.fixture(),
                    team=team,
                    player=player,
                    **values,
                )
