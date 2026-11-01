from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.base import HttpResponseV1
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.providers.sources.understat import UnderstatSource


def test_understat_session_is_guarded_private_and_scoped() -> None:
    calls: list[tuple[str, Mapping[str, str]]] = []
    reservations: list[bool] = []

    def transport(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
        calls.append((url, dict(headers)))
        return HttpResponseV1(
            b"{}",
            200,
            "application/json",
            None,
            None,
            headers={"set-cookie": "PHPSESSID=private; Path=/\nUID=anonymous; Path=/"},
        )

    source = UnderstatSource(transport=transport, request_guard=lambda: reservations.append(True))
    payload = source.results("EPL", "2024")
    assert payload.resource_key == "getLeagueData/EPL/2024"
    assert calls[0][0] == "https://understat.com/league/EPL/2024"
    assert calls[1][1]["X-Requested-With"] == "XMLHttpRequest"
    assert "PHPSESSID=private" in calls[1][1]["Cookie"]
    source.shots("26602")
    assert len(calls) == len(reservations) == 3
    assert calls[2][0] == "https://understat.com/getMatchData/26602"
    assert "private" not in repr(payload)
    with pytest.raises(ValueError):
        source.results("../EPL", "2024")
    assert len(calls) == 3


def test_understat_gzip_results_keep_zero_xg_unknown_clock_and_native_ids() -> None:
    payload = {
        "dates": [
            {
                "id": "26602",
                "isResult": True,
                "h": {"id": "89", "title": "Home"},
                "a": {"id": "228", "title": "Away"},
                "goals": {"h": "1", "a": "0"},
                "xG": {"h": "0", "a": None},
                "datetime": "2024-08-16 19:00:00",
            }
        ]
    }
    raw = gzip.compress(json.dumps(payload).encode(), mtime=0)
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "understat", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key="getLeagueData/EPL/2024",
        competition_native_id="EPL",
        season_label="2024",
    )
    result = normalize_resource(context, "results", raw)
    assert not result.findings
    assert result == normalize_resource(context, "results", raw)
    fixture = next(o for o in result.observations if o.CONTRACT == "FixtureObservationV2")
    assert fixture.to_dict()["kickoff_precision"] == "DATE_ONLY"
    assert fixture.time.event_time is None and fixture.time.known_at == now
    xg = [o for o in result.observations if o.CONTRACT == "ExpectedGoalsObservationV2"]
    assert len(xg) == 1 and xg[0].to_dict()["expected_goals"] == 0


def test_understat_guard_failure_stops_before_transport() -> None:
    def deny() -> None:
        raise RuntimeError("quota deferred")

    def transport(url: str, headers: Mapping[str, str]) -> HttpResponseV1:
        raise AssertionError("transport must not run")

    with pytest.raises(RuntimeError, match="quota deferred"):
        UnderstatSource(transport=transport, request_guard=deny).results("EPL", "2024")


def test_understat_decoding_bounds_expansion_and_rejects_corruption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.providers.normalization import understat

    monkeypatch.setattr(understat, "MAX_SOURCE_RESOURCE_BYTES", 16)
    assert understat.json_bytes(b"{}") == b"{}"
    with pytest.raises(ValueError, match="byte limit"):
        understat.json_bytes(gzip.compress(b"a" * 17, mtime=0))
    with pytest.raises(ValueError, match="compressed"):
        understat.json_bytes(b"\x1f\x8bbroken")
    with pytest.raises(ValueError, match="compressed"):
        understat.json_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03\xff" + b"\x00" * 8)


def _normalize(
    resource: str, payload: object, *, key: str, fixture: str | None = None
) -> NormalizationResult:
    raw = gzip.compress(json.dumps(payload).encode(), mtime=0)
    source = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")
    now = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "understat", None, source, source, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key=key,
        fixture_native_id=fixture,
    )
    return normalize_resource(context, resource, raw)


def test_understat_shot_final_scores_and_assistant_names_never_become_context_ids() -> None:
    payload: dict[str, Any] = {
        "rosters": {
            "h": {
                "appearance1": {
                    "player_id": "1228",
                    "team_id": "89",
                    "player": "Player",
                    "h_a": "h",
                }
            },
            "a": {
                "appearance2": {"player_id": "2", "team_id": "228", "player": "Away", "h_a": "a"}
            },
        },
        "shots": {
            "h": [
                {
                    "id": "584630",
                    "match_id": "26602",
                    "player_id": "1228",
                    "h_a": "h",
                    "minute": "19",
                    "result": "MissedShots",
                    "xG": "0",
                    "shotType": "LeftFoot",
                    "situation": "OpenPlay",
                    "X": "0.97",
                    "Y": "0.67",
                    "h_goals": "1",
                    "a_goals": "0",
                    "player_assisted": "Assistant",
                }
            ],
            "a": [],
        },
    }
    result = _normalize("shots", payload, key="getMatchData/26602", fixture="26602")
    shot = next(
        json.loads(o.to_bytes()) for o in result.observations if o.CONTRACT == "ShotObservationV3"
    )
    assert shot["expected_goals"] == 0 and shot["body_part"] == "LeftFoot"
    assert shot["team"]["provider_native_id"] == "89"
    assert shot["player"]["provider_native_id"] == "1228"
    assert shot["assisting_player"] is None and shot["home_goals_before_shot"] is None
    assert shot["away_goals_before_shot"] is None
    assert shot["x_norm"] is None and shot["y_norm"] is None
    assert shot["period"] is None
    assert {f.rule_code for f in result.findings} >= {
        "MF_NORM_COORDINATE_FRAME_UNKNOWN",
        "MF_NORM_ASSIST_ID_UNAVAILABLE",
    }
    payload["shots"]["h"][0]["match_id"] = "26603"
    rejected = _normalize("shots", payload, key="getMatchData/26602", fixture="26602")
    assert not any(o.CONTRACT == "ShotObservationV3" for o in rejected.observations)
    assert any(f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for f in rejected.findings)


@pytest.mark.parametrize(
    "key,payload",
    [("getLeagueData/../../2024", {"dates": []}), ("getLeagueData/EPL/2024", {"unexpected": []})],
)
def test_understat_bad_scope_or_response_is_reported(key: str, payload: object) -> None:
    result = _normalize("results", payload, key=key)
    assert any(f.rule_code == "MF_NORM_RESOURCE_INVALID" for f in result.findings)


def test_default_understat_transport_preserves_wire_bytes_and_both_cookies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from email.message import Message
    from io import BytesIO
    from urllib.request import Request

    from football.providers.sources import understat

    class Response(BytesIO):
        def __init__(self) -> None:
            super().__init__(b"{}")
            self.status = 200
            self.headers = Message()
            self.headers["Content-Type"] = "text/javascript"
            self.headers["Set-Cookie"] = "PHPSESSID=private; Path=/"
            self.headers["Set-Cookie"] = "UID=anonymous; Path=/"

    seen: list[Request] = []

    def open_response(request: Request, *, timeout: float) -> Response:
        seen.append(request)
        assert timeout > 0
        return Response()

    monkeypatch.setattr(understat, "open_bounded", open_response)
    payload = understat.UnderstatSource().results("EPL", "2024")
    assert payload.raw == b"{}" and payload.media_type == "text/javascript"
    cookie = seen[1].get_header("Cookie")
    assert cookie is not None
    assert "PHPSESSID=private" in cookie
    assert "UID=anonymous" in cookie
    assert "private" not in repr(payload)


def test_understat_scheduled_matches_never_emit_source_scores_xg_or_forecasts() -> None:
    from test_provider_native_records import EXAMPLES

    row = json.loads(json.dumps(EXAMPLES["UnderstatMatch"]))
    row["isResult"] = False
    row["forecast"] = {"w": "0.9", "d": "0.05", "l": "0.05"}
    result = _normalize("results", {"dates": [row]}, key="getLeagueData/EPL/2024")
    assert not result.findings
    assert not any(
        o.CONTRACT in ("ResultObservationV2", "ExpectedGoalsObservationV2")
        for o in result.observations
    )
    row["h"]["id"] = row["a"]["id"]
    rejected = _normalize("results", {"dates": [row]}, key="getLeagueData/EPL/2024")
    assert not any(o.CONTRACT == "FixtureObservationV2" for o in rejected.observations)
    assert any(f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for f in rejected.findings)
