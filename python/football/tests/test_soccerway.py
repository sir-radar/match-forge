from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1
from football.providers.normalization.common import NormalizationContext
from football.providers.normalization.pipeline import normalize_resource
from football.providers.sources.contracts import ProviderPayload
from football.providers.sources.soccerway import SoccerwaySource


def test_source_uses_soccerway_route_and_provider_namespace() -> None:
    calls: list[str] = []
    guards: list[bool] = []

    class Transport:
        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            calls.append(url)
            return HttpResponseV1(b"<html></html>", 200, "text/html", None, None)

        def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
            raise AssertionError("response metadata required")

    result = SoccerwaySource(
        transport=Transport(), request_guard=lambda: guards.append(True)
    ).league("england", "premier-league")
    assert (
        result.provider == "soccerway" and result.resource_key == "england/premier-league/results"
    )
    assert (
        calls == ["https://www.soccerway.com/england/premier-league/results/"] and len(guards) == 1
    )


def test_shared_feed_format_preserves_separate_source_provenance_and_versions() -> None:
    env = {
        "sport_id": 1,
        "selected_season_id": 0,
        "season_list": [{"id": 0, "name": "2026/2027", "pathname": "/standings/seasonid/stageid/"}],
    }
    header = "SA÷1¬~ZA÷League¬ZEE÷leagueid¬ZC÷stageid¬ZE÷seasonid¬ZL÷/england/league/¬~"
    match = (
        "AA÷match001¬AD÷1793476800¬AB÷3¬AC÷3¬AE÷Home¬AF÷Away¬PX÷home0001¬PY÷away0001¬AT÷1¬AU÷0¬~"
    )
    raw = (
        "<script>window.environment = "
        + json.dumps(env)
        + ';cjs.initialFeeds["results"] = {data: `'
        + header
        + match
        + '`};cjs.initialFeeds["fixtures"] = {data: `'
        + header
        + "`};</script>"
    ).encode()
    uid = UUID(int=1)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "soccerway", None, uid, uid, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="england/league/results",
        competition_native_id="leagueid",
        season_label="2026/2027",
    )
    result = normalize_resource(context, "league", raw)
    assert not result.findings
    assert any(o.CONTRACT == "ResultObservationV2" for o in result.observations)
    assert all(
        o.provenance.provider == "soccerway"
        and o.versions.adapter_version == "soccerway-resource-adapter-v1"
        for o in result.observations
    )
    assert result == normalize_resource(context, "league", raw)


@pytest.mark.parametrize("project,valid", [(2020, True), (2, False)])
def test_match_feed_uses_its_own_project_and_provider(project: int, valid: bool) -> None:
    env = {
        "event_id_c": "match001",
        "sport_id": 1,
        "config": {
            "app": {
                "project": {"id": project},
                "project_type": {"id": 1},
                "feed_sign": "public-value",
                "feed_resolver": {"default_url": "https://global.flashscore.ninja"},
            }
        },
    }
    page = ProviderPayload(
        provider="soccerway",
        resource_key="match/match001",
        acquired_at=datetime(2026, 11, 1, tzinfo=UTC),
        raw=("<script>window.environment = " + json.dumps(env) + ";</script>").encode(),
        media_type="text/html",
    )
    calls: list[str] = []

    def transport(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
        calls.append(url)
        return HttpResponseV1(b"raw-feed", 200, "text/plain", None, None)

    source = SoccerwaySource(feed_transport=transport)
    if valid:
        result = source.statistics(page)
        assert result.provider == "soccerway" and calls == [
            "https://global.flashscore.ninja/2020/x/feed/df_st_1_match001"
        ]
    else:
        with pytest.raises(ValueError):
            source.statistics(page)
        assert not calls
