from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1, ProviderFetchError
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.providers.sources.flashscore import FlashscoreSource


def page(status: str = "3", extra: str = "") -> bytes:
    environment = {
        "sport_id": 1,
        "selected_season_id": 0,
        "season_list": [{"id": 0, "name": "2026/2027", "pathname": "/standings/seasonid/stageid/"}],
    }
    header = (
        "SA÷1¬~ZA÷ENGLAND: League¬ZEE÷leagueid¬ZC÷stageid¬ZE÷seasonid¬"
        "ZL÷/football/england/league/¬~"
    )
    match = (
        f"AA÷match001¬AD÷1793476800¬AB÷{status}¬AC÷{status}¬AE÷Home¬AF÷Away¬"
        f"PX÷home0001¬PY÷away0001¬AG÷1¬AH÷0¬AT÷1¬AU÷0¬{extra}~"
    )
    return (
        "<script>window.environment = "
        + json.dumps(environment)
        + ";</script><script>cjs.initialFeeds['results'] = {data: `"
        + header
        + match
        + "`};cjs.initialFeeds['fixtures'] = {data: `"
        + header
        + "`};</script>"
    ).encode()


def normalize(raw: bytes) -> NormalizationResult:
    uid = UUID(int=1)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    ctx = NormalizationContext(
        provenance=ObservationProvenance(
            "flashscore", None, uid, uid, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="football/england/league/results",
        competition_native_id="leagueid",
        season_label="2026/2027",
    )
    result = normalize_resource(ctx, "league", raw)
    assert result == normalize_resource(ctx, "league", raw)
    return result


def test_embedded_results_use_primary_key_definitions_without_backdated_knowledge() -> None:
    result = normalize(page())
    assert not result.findings
    outcome = next(o.to_dict() for o in result.observations if o.CONTRACT == "ResultObservationV2")
    assert (
        outcome["home_goals"] == 1
        and outcome["away_goals"] == 0
        and outcome["score_basis"] == "UNKNOWN"
    )
    assert all(o.time.event_time is None for o in result.observations)
    assert not any(o.CONTRACT == "PeriodScoreObservationV3" for o in result.observations)


def test_scheduled_score_placeholders_are_excluded() -> None:
    result = normalize(page("1"))
    assert not result.findings
    assert not any(o.CONTRACT == "ResultObservationV2" for o in result.observations)


def test_current_score_does_not_replace_explicit_full_time_score() -> None:
    result = normalize(page().replace("AG÷1".encode(), "AG÷9".encode()))
    row = next(o.to_dict() for o in result.observations if o.CONTRACT == "ResultObservationV2")
    assert row["home_goals"] == 1


@pytest.mark.parametrize(
    "raw",
    [
        page("999"),
        page().replace(b"stageid", b"conflict", 1),
        page().replace(b"leagueid", b"otherid1", 1),
        page().replace(b"away0001", b"home0001"),
    ],
)
def test_unmapped_status_duplicate_named_field_or_scope_is_held(raw: bytes) -> None:
    result = normalize(raw)
    assert any(f.severity == "QUARANTINE" for f in result.findings)
    assert not any(o.CONTRACT == "ResultObservationV2" for o in result.observations)


@pytest.mark.parametrize(
    "raw",
    [
        page(extra="AA÷otherid1¬"),
        page().replace(b"window.environment", b"window.other"),
        page().replace(b"`SA", b"`${unknown}SA"),
        page().replace(b'"sport_id": 1', b'"sport_id": NaN'),
    ],
)
def test_malformed_embedded_source_is_rejected(raw: bytes) -> None:
    with pytest.raises(ValueError):
        normalize(raw)


def test_empty_source_fixture_feed_is_reported_and_not_fabricated() -> None:
    prefix, _ = page().split(b"cjs.initialFeeds['fixtures'] = {data: `")
    raw = prefix + b"cjs.initialFeeds['fixtures'] = {data: ``};</script>"
    result = normalize(raw)
    assert any(f.rule_code == "MF_NORM_FEED_EMPTY" for f in result.findings)
    assert sum(o.CONTRACT == "FixtureObservationV2" for o in result.observations) == 1


def test_source_route_guard_and_error() -> None:
    calls: list[str] = []
    guards: list[bool] = []

    class Transport:
        status = 200

        def get_response(
            self, url: str, *, timeout_seconds: float, max_bytes: int
        ) -> HttpResponseV1:
            calls.append(url)
            return HttpResponseV1(b"<html></html>", self.status, "text/html", None, None)

        def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
            raise AssertionError("response metadata required")

    transport = Transport()
    source = FlashscoreSource(transport=transport, request_guard=lambda: guards.append(True))
    result = source.league("england", "premier-league-2024-2025")
    assert (
        result.raw == b"<html></html>"
        and result.resource_key == "football/england/premier-league-2024-2025/results"
    )
    assert len(calls) == len(guards) == 1
    with pytest.raises(ValueError):
        source.league("england", "../league")
    assert len(calls) == 1
    transport.status = 403
    with pytest.raises(ProviderFetchError):
        source.league("england", "league")
