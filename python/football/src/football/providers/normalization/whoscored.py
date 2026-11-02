"""Read public fixture JSON without executing the page's JavaScript."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from football.contracts.observations_v2 import (
    CompetitionObservationV2,
    FixtureObservationV2,
    ResultObservationV2,
    TeamStatisticObservationV2,
)
from football.providers.native.reader import native_record
from football.providers.native.whoscored import WhoScoredMatch, WhoScoredTournament
from football.providers.normalization.common import (
    ObservationCollector,
    array,
    count,
    object_value,
    timestamp,
)
from football.providers.normalization.participants import emit_team


class _FixtureScript(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.blocks: list[list[str]] = []
        self.active = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.active = dict(attrs).get("data-hypernova-key") == "tournamentfixtures"
            if self.active:
                if dict(attrs).get("type") != "application/json":
                    raise ValueError("WhoScored fixture script must declare JSON")
                self.blocks.append([])

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.blocks[-1].append(data)


def json_bytes(raw: bytes) -> bytes:
    parser = _FixtureScript()
    parser.feed(raw.decode("utf-8"))
    parser.close()
    if len(parser.blocks) != 1:
        raise ValueError("WhoScored page requires one explicit fixture JSON block")
    value = "".join(parser.blocks[0]).strip()
    if value.startswith("<!--") and value.endswith("-->"):
        value = value[4:-3]
    return value.encode("utf-8")


def fixtures(output: ObservationCollector, payload: object) -> None:
    root = object_value(payload)
    if "tournaments" not in root:
        raise ValueError("WhoScored fixture block has no tournaments array")
    for index, raw in enumerate(array(root["tournaments"])):
        path = f"json:/tournaments/{index}"
        with output.record(path):
            league = native_record(WhoScoredTournament, raw)
            _scope(output, league)
            comp = output.context.reference(league["tournamentId"], path)
            output.emit(
                CompetitionObservationV2,
                path,
                league["tournamentId"],
                competition=comp,
                name=league["tournamentName"],
                season_label=league["seasonName"],
            )
            for mi, match in enumerate(league["matches"]):
                field = f"{path}/matches/{mi}"
                with output.record(field):
                    _match(output, league, match, field)


def _scope(output: ObservationCollector, league: WhoScoredTournament) -> None:
    route = re.fullmatch(
        r"/?regions/[1-9][0-9]*/tournaments/([1-9][0-9]*)"
        r"(?:/seasons/([1-9][0-9]*)(?:/stages/([1-9][0-9]*)/fixtures)?)?"
        r"(?:/[A-Za-z0-9-]+)?",
        urlsplit(output.context.resource_key).path,
        flags=re.IGNORECASE,
    )
    native = str(league["tournamentId"])
    if route is None or route[1] != native:
        raise ValueError("WhoScored tournament conflicts with registered request")
    if route[2] is not None and route[2] != str(league["seasonId"]):
        raise ValueError("WhoScored season conflicts with registered request")
    if route[3] is not None and route[3] != str(league["stageId"]):
        raise ValueError("WhoScored stage conflicts with registered request")
    if output.context.competition_native_id not in (
        None,
        native,
    ) or output.context.season_label not in (None, league["seasonName"]):
        raise ValueError("WhoScored competition/season differs from requested scope")


def _match(
    output: ObservationCollector, league: WhoScoredTournament, row: WhoScoredMatch, path: str
) -> None:
    if row["stageId"] != league["stageId"] or row["homeTeamId"] == row["awayTeamId"]:
        raise ValueError("WhoScored match stage or participants conflict")
    status = {(6, "FT", 7): "FINISHED", (1, "", 0): "SCHEDULED"}.get(
        (row["status"], row["elapsed"], row["period"])
    )
    if status is None:
        raise ValueError("WhoScored status/elapsed/period tuple is not mapped")
    kickoff = timestamp(row["startTimeUtc"])
    teams = {
        side: emit_team(output, {"id": native, "name": name}, path + "/" + side)
        for side, native, name in (
            ("home", row["homeTeamId"], row["homeTeamName"]),
            ("away", row["awayTeamId"], row["awayTeamName"]),
        )
    }
    fixture = output.context.reference(row["id"], path)
    output.emit(
        FixtureObservationV2,
        path,
        row["id"],
        fixture=fixture,
        competition=output.context.reference(league["tournamentId"], path),
        home_team=teams["home"],
        away_team=teams["away"],
        kickoff_at=kickoff,
        kickoff_precision="EXACT",
        status=status,
        season_label=league["seasonName"],
    )
    if status != "FINISHED":
        return
    output.emit(
        ResultObservationV2,
        path,
        row["id"],
        fixture=fixture,
        status=status,
        score_basis="UNKNOWN",
        home_goals=count(row["homeScore"]),
        away_goals=count(row["awayScore"]),
    )
    for side, team in teams.items():
        yellow, red = count(row.get(side + "YellowCards")), count(row.get(side + "RedCards"))
        if yellow is not None or red is not None:
            output.emit(
                TeamStatisticObservationV2,
                path + "/" + side,
                fixture=fixture,
                team=team,
                period="FULL_MATCH",
                yellow_cards=yellow,
                red_cards=red,
            )
