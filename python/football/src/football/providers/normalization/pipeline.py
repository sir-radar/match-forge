"""Checksum-verified, offline resource normalization; no canonical admission or I/O."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from urllib.parse import parse_qs, urlsplit

from football.providers.native.reader import native_json
from football.providers.normalization import (
    api_football,
    api_football_rich,
    espn,
    files,
    flashscore,
    flashscore_events,
    flashscore_lineups,
    flashscore_statistics,
    flashscore_summary,
    football_data_org,
    fotmob,
    pitchapi,
    statsbomb,
    understat,
    whoscored,
)
from football.providers.normalization.common import (
    NormalizationContext,
    NormalizationResult,
    ObservationCollector,
)

NORMALIZERS: dict[tuple[str, str], Callable[[ObservationCollector, object], None]] = {
    ("soccerway", "league"): flashscore.league,
    ("soccerway", "statistics"): flashscore_statistics.statistics,
    ("soccerway", "events"): flashscore_events.events,
    ("soccerway", "lineups"): flashscore_lineups.lineups,
    ("soccerway", "summary"): flashscore_summary.summary,
    ("flashscore", "league"): flashscore.league,
    ("flashscore", "statistics"): flashscore_statistics.statistics,
    ("flashscore", "events"): flashscore_events.events,
    ("flashscore", "lineups"): flashscore_lineups.lineups,
    ("flashscore", "summary"): flashscore_summary.summary,
    ("whoscored", "fixtures"): whoscored.fixtures,
    ("espn", "scoreboard"): espn.scoreboard,
    ("espn", "summary"): espn.summary,
    ("understat", "results"): understat.results,
    ("understat", "shots"): understat.shots,
    ("openfootball", "fixtures"): files.openfootball,
    ("openfootball", "results"): files.openfootball,
    ("football_data_uk", "fixtures"): files.football_data_uk,
    ("football_data_uk", "results"): files.football_data_uk,
    ("football_data_uk", "statistics"): files.football_data_uk,
    ("football_data_uk", "odds"): files.football_data_uk,
    ("statsbomb_open_data", "competitions"): statsbomb.competitions,
    ("statsbomb_open_data", "results"): statsbomb.results,
    ("statsbomb_open_data", "lineups"): statsbomb.lineups,
    ("statsbomb_open_data", "events"): statsbomb.events,
    ("statsbomb_open_data", "shots"): statsbomb.shots,
    ("api_football", "fixtures"): api_football.fixtures,
    ("api_football", "results"): api_football.fixtures,
    ("api_football", "competitions"): api_football.competitions,
    ("api_football", "lineups"): api_football.lineups,
    ("api_football", "availability"): api_football.availability,
    ("api_football", "statistics"): api_football_rich.statistics,
    ("api_football", "events"): api_football_rich.events,
    ("api_football", "player_statistics"): api_football_rich.player_statistics,
    ("api_football", "standings"): api_football.standings,
    ("football_data_org", "fixtures"): football_data_org.fixtures,
    ("football_data_org", "results"): football_data_org.fixtures,
    ("football_data_org", "standings"): football_data_org.standings,
    ("fotmob", "fixtures"): fotmob.fixtures,
    ("fotmob", "results"): fotmob.fixtures,
    ("fotmob", "lineups"): fotmob.lineups,
    ("fotmob", "shots"): fotmob.shots,
    ("fotmob", "statistics"): fotmob.statistics,
    ("fotmob", "player_statistics"): fotmob.player_statistics,
    ("fotmob", "events"): fotmob.events,
    ("pitchapi", "fixtures"): pitchapi.fixtures,
    ("pitchapi", "results"): pitchapi.fixtures,
    ("pitchapi", "lineups"): pitchapi.lineups,
    ("pitchapi", "shots"): pitchapi.shots,
    ("pitchapi", "statistics"): pitchapi.statistics,
    ("pitchapi", "player_statistics"): pitchapi.player_statistics,
    ("pitchapi", "events"): pitchapi.events,
}


def normalize_resource(
    context: NormalizationContext, resource: str, raw: bytes
) -> NormalizationResult:
    if hashlib.sha256(raw).hexdigest() != context.provenance.source_sha256:
        raise ValueError("source checksum does not match registered provenance")
    output = ObservationCollector(context, resource)
    normalizer = NORMALIZERS.get((context.provenance.provider, resource))
    if normalizer is None:
        output.finding(
            "RESOURCE_UNSUPPORTED",
            "resource",
            "No normalizer for this provider resource",
            evidence={"provider": context.provenance.provider, "resource": resource},
        )
        return output.result()
    payload: object
    if context.provenance.provider == "football_data_uk" or (
        context.provenance.provider in {"flashscore", "soccerway"}
        and resource in {"statistics", "events", "lineups", "summary"}
    ):
        payload = raw
    else:
        decoders = {
            "understat": understat.json_bytes,
            "whoscored": whoscored.json_bytes,
            "flashscore": flashscore.json_bytes,
            "soccerway": flashscore.json_bytes,
        }
        decoder = decoders.get(context.provenance.provider)
        decoded = decoder(raw) if decoder is not None else raw
        payload = native_json(decoded)
    try:
        if context.provenance.provider in {"flashscore", "soccerway"}:
            flashscore.validate_resource_scope(context, resource)
        _validate_scope(context, payload)
        normalizer(output, payload)
    except ValueError as error:
        output.finding("RESOURCE_INVALID", "json:/", str(error))
    return output.result()


def _validate_scope(context: NormalizationContext, payload: object) -> None:
    if context.fixture_native_id is None:
        return
    payload = payload if isinstance(payload, dict) else {}
    if context.provenance.provider == "pitchapi":
        data = payload.get("data")
        native_id = data.get("match_id", data.get("id")) if isinstance(data, dict) else None
    elif context.provenance.provider == "fotmob":
        general = payload.get("general")
        native_id = general.get("matchId") if isinstance(general, dict) else None
    elif context.provenance.provider == "api_football":
        parameters = payload.get("parameters")
        native_id = parameters.get("fixture") if isinstance(parameters, dict) else None
    elif context.provenance.provider == "espn":
        header = payload.get("header")
        native_id = header.get("id") if isinstance(header, dict) else None
    else:
        native_id = None
    if native_id is not None and str(native_id) != context.fixture_native_id:
        raise ValueError("source fixture conflicts with requested scope")
    requested = _request_fixture(context)
    if requested is not None and requested != context.fixture_native_id:
        raise ValueError("registered request fixture conflicts with requested scope")
    if native_id is None and requested is None:
        raise ValueError("fixture scope has no matching source or registered request evidence")


def _request_fixture(context: NormalizationContext) -> str | None:
    key = context.resource_key
    patterns = {
        "statsbomb_open_data": r"^(?:data/)?(?:events|lineups)/(\d+)\.json$",
        "api_football": r"^fixture-(\d+)-(?:lineups|injuries)$",
        "pitchapi": r"^match-(m_[A-Za-z0-9]+)-(?:shots|lineups|stats|players|events)$",
        "understat": r"^getMatchData/([1-9][0-9]*)$",
        "flashscore": r"^df_(?:st|sur|sui|li)_1_([A-Za-z0-9]+)$",
        "soccerway": r"^df_(?:st|sur|sui|li)_1_([A-Za-z0-9]+)$",
    }
    match = re.fullmatch(patterns.get(context.provenance.provider, r"(?!)"), key)
    if match is not None:
        return match[1]
    request = urlsplit(key)
    if context.provenance.provider == "api_football":
        values = parse_qs(request.query).get("fixture", [])
        return values[0] if len(values) == 1 else None
    if context.provenance.provider == "espn" and request.path.endswith("/summary"):
        values = parse_qs(request.query).get("event", [])
        return values[0] if len(values) == 1 else None
    if context.provenance.provider == "pitchapi":
        match = re.fullmatch(
            r"/v1/matches/(m_[A-Za-z0-9]+)/(?:shots|lineups|stats|players|events)", request.path
        )
        return match[1] if match is not None else None
    return None
