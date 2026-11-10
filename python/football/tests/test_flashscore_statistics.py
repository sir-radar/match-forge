from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1
from football.providers.native.reader import native_json
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.providers.sources.contracts import ProviderPayload
from football.providers.sources.flashscore import FlashscoreSource


def normalize(feed: str) -> NormalizationResult:
    raw = feed.encode()
    uid = UUID(int=1)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "flashscore", None, uid, uid, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="df_st_1_match001",
        fixture_native_id="match001",
    )
    result = normalize_resource(context, "statistics", raw)
    assert result == normalize_resource(context, "statistics", raw)
    return result


def test_named_counts_periods_and_unresolved_source_sides() -> None:
    result = normalize(
        "SE÷Match¬~SD÷34¬SG÷Total shots¬SH÷10¬SI÷0¬~SD÷17¬SG÷Offsides¬SH÷1¬SI÷0¬~"
        "SE÷1st Half¬~SD÷16¬SG÷Corner kicks¬SH÷2¬SI÷0¬~"
    )
    assert not any(f.severity == "QUARANTINE" for f in result.findings)
    stats = [o.to_dict() for o in result.observations if o.CONTRACT.startswith("TeamStatistic")]
    assert len(stats) == 4
    assert stats[0]["total_shots"] == 10 and stats[1]["total_shots"] == 0
    assert stats[2]["period"] == "FIRST_HALF"
    for stat in stats:
        team = stat["team"]
        assert isinstance(team, dict) and team["provider_native_id"] is None
    assert any(f.rule_code == "MF_NORM_TEAM_ID_UNRESOLVED" for f in result.findings)


def test_pass_fraction_not_converted_into_unverified_count() -> None:
    result = normalize(
        "SE÷Match¬~SD÷342¬SG÷Passes¬SH÷86% (374/434)¬SI÷89% (478/540)¬~"
        "SD÷34¬SG÷Total shots¬SH÷10¬SI÷8¬~"
    )
    assert not any(f.severity == "QUARANTINE" for f in result.findings)
    assert any(f.rule_code == "MF_NORM_STATISTIC_VALUE_UNQUALIFIED" for f in result.findings)
    assert all(o.to_dict().get("passes") is None for o in result.observations)


def test_conflicting_repeated_measurement_does_not_choose_one_value() -> None:
    result = normalize(
        "SE÷Match¬~SD÷34¬SG÷Total shots¬SH÷10¬SI÷8¬~SD÷34¬SG÷Total shots¬SH÷11¬SI÷8¬~"
    )
    assert any(f.rule_code == "MF_NORM_STATISTIC_DUPLICATE" for f in result.findings)
    assert not any(o.to_dict().get("total_shots") in (10, 11) for o in result.observations)


def page_payload(change: str = "") -> ProviderPayload:
    environment: dict[str, Any] = {
        "event_id_c": "match001",
        "sport_id": 1,
        "config": {
            "app": {
                "project": {"id": 2},
                "project_type": {"id": 1},
                "feed_sign": "public-value",
                "feed_resolver": {"default_url": "https://global.flashscore.ninja"},
            }
        },
    }
    if change == "event":
        environment["event_id_c"] = "other001"
    if change == "origin":
        environment["config"]["app"]["feed_resolver"]["default_url"] = "http://127.0.0.1"
    if change == "type":
        environment["sport_id"] = True
    if change == "signature":
        environment["config"]["app"]["feed_sign"] = "bad\r\nvalue"
    return ProviderPayload(
        provider="other" if change == "provider" else "flashscore",
        resource_key="match/match001" if change != "scope" else "match/../match001",
        acquired_at=datetime(2026, 11, 1, tzinfo=UTC),
        media_type="text/html",
        raw=("<script>window.environment = " + json.dumps(environment) + ";</script>").encode(),
    )


@pytest.mark.parametrize(
    "method,suffix",
    [("statistics", "st"), ("events", "sui"), ("lineups", "li"), ("summary", "sur")],
)
def test_match_feed_request_uses_verified_page_and_public_client_header(
    method: str, suffix: str
) -> None:
    calls: list[str] = []
    guards: list[bool] = []

    def transport(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
        calls.append(url)
        assert headers["x-fsign"] == "public-value"
        return HttpResponseV1(b"SE\xc3\xb7Match", 200, "text/plain", None, None)

    source = FlashscoreSource(feed_transport=transport, request_guard=lambda: guards.append(True))
    response = getattr(source, method)(page_payload())
    assert calls == [f"https://global.flashscore.ninja/2/x/feed/df_{suffix}_1_match001"]
    assert response.resource_key == f"df_{suffix}_1_match001" and response.raw == b"SE\xc3\xb7Match"
    assert len(guards) == 1


@pytest.mark.parametrize("change", ["provider", "scope", "event", "origin", "type", "signature"])
def test_invalid_page_scope_never_sends_feed_request(change: str) -> None:
    def transport(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
        raise AssertionError("no request authorized for invalid page")

    with pytest.raises(ValueError):
        FlashscoreSource(feed_transport=transport).statistics(page_payload(change))


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e9999}'])
def test_shared_native_json_reader_rejects_ambiguous_or_nonfinite_json(raw: bytes) -> None:
    with pytest.raises(ValueError):
        native_json(raw)


@pytest.mark.parametrize(
    "feed",
    [
        "<html>Error</html>",
        "SE÷Unknown¬~SD÷34¬SG÷Total shots¬SH÷10¬SI÷8¬~",
        "SE÷Match¬~SD÷34¬SG÷Total shots¬SH÷-1¬SI÷8¬~",
    ],
)
def test_invalid_feed_or_count_stays_quarantined(feed: str) -> None:
    result = normalize(feed)
    assert any(f.severity == "QUARANTINE" for f in result.findings)
