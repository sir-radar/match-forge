#!/usr/bin/env python3
"""Run the owner-approved PitchAPI pilot without retaining raw responses."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiRequestRecord,
    PitchApiSeasonAuditInput,
    PitchApiSeasonScope,
    validate_pitchapi_audit,
)

_BASE_URL = "https://api.pitchapi.dev"
_TOKEN_NAME = "PITCH_API_TOKEN"
_TIMEOUT_SECONDS = 30
_MIN_REQUEST_INTERVAL_SECONDS = 1.0
_RETRY_DELAY_SECONDS = 5
_WALL_CLOCK_SECONDS = 45 * 60
_PILOT_BASE_ATTEMPTS = 22
_RETRY_RESERVE = 12
_PILOT_ATTEMPT_CEILING = 34
_ORIGINAL_AUDIT_CEILING = 702
_PRIOR_ATTEMPTS_USED = 2
_REMAINING_AUDIT_CEILING = 700
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_RETRYABLE_STATUS_CODES = frozenset((408, 429, 500, 502, 503, 504))

_SCOPES = (
    PitchApiSeasonScope("bundesliga", "l_1Isor4", "2023/2024", 10),
    PitchApiSeasonScope("ligue1", "l_3FJFUl", "2022/2023", 10),
)
_FULL_MATCH_COUNTS = {"bundesliga": 306, "ligue1": 380}


class PilotStop(RuntimeError):
    """The approved pilot reached a declared stop condition."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PilotManifestSelection:
    payload: Mapping[str, Any]
    ordered_matches: tuple[Mapping[str, object], ...]
    observed_match_count: int
    manifest_identity_sha256: str
    selection_sha256: str


@dataclass(slots=True)
class _RuntimeState:
    started_monotonic: float
    attempts: int = 0
    retries: int = 0
    rate_limit_responses: int = 0
    last_request_started: float | None = None


class PilotHttpClient:
    def __init__(
        self,
        api_key: str,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        opener: Callable[..., Any] = urllib.request.urlopen,
        attempt_ceiling: int = _PILOT_ATTEMPT_CEILING,
        retry_reserve: int = _RETRY_RESERVE,
    ) -> None:
        if not api_key:
            raise PilotStop("MISSING_CREDENTIAL")
        self._api_key = api_key
        self._sleep = sleep
        self._monotonic = monotonic
        self._opener = opener
        self._attempt_ceiling = attempt_ceiling
        self._retry_reserve = retry_reserve
        self.state = _RuntimeState(started_monotonic=monotonic())
        self.records: list[PitchApiRequestRecord] = []
        self.request_start_times: list[float] = []

    def get_json(self, path: str) -> Mapping[str, Any]:
        for path_attempt in (1, 2):
            self._before_request()
            try:
                payload = self._request(path)
            except urllib.error.HTTPError as error:
                if self._handle_http_error(path, path_attempt, error):
                    continue
                raise PilotStop("PATH_ATTEMPT_LIMIT_REACHED") from error
            except (TimeoutError, urllib.error.URLError):
                self.records.append(PitchApiRequestRecord(path=path, failure_kind="network_error"))
                if self._retry(path_attempt, _RETRY_DELAY_SECONDS):
                    continue
                raise PilotStop("TRANSPORT_FAILURE") from None
            if not isinstance(payload, Mapping):
                raise PilotStop("MALFORMED_JSON_RESPONSE")
            return payload
        raise PilotStop("PATH_ATTEMPT_LIMIT_REACHED")

    def _before_request(self) -> None:
        now = self._monotonic()
        if now - self.state.started_monotonic >= _WALL_CLOCK_SECONDS:
            raise PilotStop("WALL_CLOCK_CEILING_REACHED")
        if self.state.attempts >= self._attempt_ceiling:
            raise PilotStop("PILOT_ATTEMPT_CEILING_REACHED")
        if self.state.last_request_started is not None:
            wait = _MIN_REQUEST_INTERVAL_SECONDS - (now - self.state.last_request_started)
            if wait > 0:
                self._sleep(wait)
        started = self._monotonic()
        self.state.last_request_started = started
        self.request_start_times.append(started)
        self.state.attempts += 1

    def _request(self, path: str) -> object:
        request = urllib.request.Request(
            f"{_BASE_URL}{path}",
            headers={
                "Accept": "application/json",
                "User-Agent": "MatchForge-private-research/1.0",
                "X-API-KEY": self._api_key,
            },
            method="GET",
        )
        with self._opener(request, timeout=_TIMEOUT_SECONDS) as response:
            status = int(response.status)
            if status != 200:
                raise PilotStop("UNEXPECTED_SUCCESS_RESPONSE_STATUS")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > _MAX_RESPONSE_BYTES:
                raise PilotStop("RESPONSE_SIZE_LIMIT_EXCEEDED")
            body = response.read(_MAX_RESPONSE_BYTES + 1)
            if len(body) > _MAX_RESPONSE_BYTES:
                raise PilotStop("RESPONSE_SIZE_LIMIT_EXCEEDED")
            self.records.append(
                PitchApiRequestRecord(
                    path=path,
                    status_code=200,
                    request_id_present=bool(response.headers.get("X-Request-ID")),
                )
            )
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise PilotStop("MALFORMED_JSON_RESPONSE") from None

    def _handle_http_error(
        self,
        path: str,
        path_attempt: int,
        error: urllib.error.HTTPError,
    ) -> bool:
        status = int(error.code)
        retry_after = _retry_after_seconds(
            error.headers.get("Retry-After") if error.headers is not None else None
        )
        self.records.append(
            PitchApiRequestRecord(
                path=path,
                status_code=status,
                provider_code=_safe_provider_code(status),
                request_id_present=bool(
                    error.headers.get("X-Request-ID") if error.headers is not None else None
                ),
                retry_after_seconds=retry_after,
            )
        )
        if status in (401, 403):
            raise PilotStop("AUTHORIZATION_FAILED")
        if status == 429:
            self.state.rate_limit_responses += 1
            if retry_after is None:
                raise PilotStop("RATE_LIMIT_WITHOUT_RETRY_AFTER")
            if self.state.rate_limit_responses >= 2:
                raise PilotStop("REPEATED_RATE_LIMIT")
        if status not in _RETRYABLE_STATUS_CODES:
            raise PilotStop("NON_RETRYABLE_HTTP_STATUS")
        if status == 429:
            assert retry_after is not None
            delay = retry_after + _RETRY_DELAY_SECONDS
        else:
            delay = _RETRY_DELAY_SECONDS
        return self._retry(path_attempt, delay)

    def _retry(self, path_attempt: int, delay_seconds: int) -> bool:
        if path_attempt >= 2:
            return False
        if self.state.retries >= self._retry_reserve:
            raise PilotStop("RETRY_RESERVE_EXHAUSTED")
        self.state.retries += 1
        self._sleep(delay_seconds)
        return True


def select_pilot_manifest(
    payload: Mapping[str, Any],
    scope: PitchApiSeasonScope,
    *,
    full_expected_match_count: int,
) -> PilotManifestSelection:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise PilotStop("MALFORMED_MANIFEST")
    league = data.get("league")
    matches = data.get("matches")
    if not isinstance(league, Mapping) or not _sequence(matches):
        raise PilotStop("MALFORMED_MANIFEST")
    match_sequence = cast(Sequence[object], matches)
    if league.get("id") != scope.league_id or league.get("season") != scope.season:
        raise PilotStop("MANIFEST_SCOPE_MISMATCH")
    if len(match_sequence) != full_expected_match_count:
        raise PilotStop("FULL_SEASON_MATCH_COUNT_MISMATCH")
    normalized = [_normalized_fixture(match) for match in match_sequence]
    match_ids = [str(match["id"]) for match in normalized]
    if len(match_ids) != len(set(match_ids)):
        raise PilotStop("DUPLICATE_MANIFEST_MATCH_ID")
    ordered = sorted(normalized, key=lambda match: (str(match["time_utc"]), str(match["id"])))
    selected = ordered[: scope.expected_match_count]
    if len(selected) != scope.expected_match_count:
        raise PilotStop("PILOT_SELECTION_SHORTAGE")
    selected_payload = {
        "data": {
            "league": {
                "id": scope.league_id,
                "name": str(league.get("name", "")),
                "season": scope.season,
            },
            "matches": selected,
        }
    }
    return PilotManifestSelection(
        payload=selected_payload,
        ordered_matches=tuple(ordered),
        observed_match_count=len(normalized),
        manifest_identity_sha256=_identity_sha256(ordered),
        selection_sha256=_identity_sha256(selected),
    )


def run_pilot(api_key: str) -> dict[str, object]:
    client = PilotHttpClient(api_key)
    try:
        return _execute_pilot(client)
    except PilotStop as error:
        return _stopped_report(client, error.code)


def _execute_pilot(client: PilotHttpClient) -> dict[str, object]:
    started_at = datetime.now(UTC)
    season_inputs: list[PitchApiSeasonAuditInput] = []
    manifest_summaries: dict[str, dict[str, object]] = {}
    for scope in _SCOPES:
        manifest = client.get_json(scope.manifest_path)
        selection = select_pilot_manifest(
            manifest,
            scope,
            full_expected_match_count=_FULL_MATCH_COUNTS[scope.key],
        )
        shot_payloads: dict[str, Mapping[str, Any]] = {}
        selected_data = selection.payload.get("data")
        if not isinstance(selected_data, Mapping):
            raise PilotStop("MALFORMED_SELECTED_MANIFEST")
        selected_matches = selected_data.get("matches")
        if not _sequence(selected_matches):
            raise PilotStop("MALFORMED_SELECTED_MANIFEST")
        for match in cast(Sequence[object], selected_matches):
            if not isinstance(match, Mapping):
                raise PilotStop("MALFORMED_SELECTED_MANIFEST")
            match_id = str(match["id"])
            shot_payloads[match_id] = client.get_json(f"/v1/matches/{match_id}/shots")
        season_inputs.append(PitchApiSeasonAuditInput(scope, selection.payload, shot_payloads))
        manifest_summaries[scope.key] = {
            "observed_matches": selection.observed_match_count,
            "selected_matches": scope.expected_match_count,
            "manifest_identity_sha256": selection.manifest_identity_sha256,
            "selection_sha256": selection.selection_sha256,
        }
        del manifest, shot_payloads
    ended_at = datetime.now(UTC)
    audit = PitchApiAuditInput(
        seasons=tuple(season_inputs),
        request_log=tuple(client.records),
        budget=PitchApiRequestBudget(
            ceiling=_PILOT_ATTEMPT_CEILING,
            retry_reserve=_RETRY_RESERVE,
        ),
        metadata=PitchApiAuditMetadata(
            endpoint_version="v1",
            observed_provider_version=None,
            acquisition_started_at=started_at,
            acquisition_ended_at=ended_at,
            code_git_sha=_git_sha(),
            dependency_lock_sha256=_dependency_lock_sha256(),
            credential_reference="env:PITCH_API_TOKEN",
        ),
        qualification_evidence=PitchApiQualificationEvidence(
            automated_private_research_permitted=False,
            immutable_raw_retention_permitted=False,
            attribution_requirements_recorded=False,
            correction_history_available=False,
            immutable_revision_identity_available=False,
            stable_identifier_policy_available=False,
            xg_series_by_scope={scope.key: None for scope in _SCOPES},
        ),
    )
    report = validate_pitchapi_audit(audit)
    attempts_used = len(client.records)
    result: dict[str, object] = {
        "contract": "PitchApiLiveAuditPilotReportV1",
        "status": "COMPLETED" if not report.stopped else "STOPPED",
        "selection_rule": "earliest_kickoff_then_match_id_v1",
        "manifests": manifest_summaries,
        "request_budget": {
            "pilot_base_attempts": _PILOT_BASE_ATTEMPTS,
            "pilot_attempt_ceiling": _PILOT_ATTEMPT_CEILING,
            "original_audit_attempt_ceiling": _ORIGINAL_AUDIT_CEILING,
            "absolute_remaining_ceiling_before_run": _REMAINING_AUDIT_CEILING,
            "prior_attempts_used": _PRIOR_ATTEMPTS_USED,
            "attempts_used_this_run": attempts_used,
            "cumulative_attempts_used": _PRIOR_ATTEMPTS_USED + attempts_used,
            "retries_used": client.state.retries,
            "remaining_total_attempts": _REMAINING_AUDIT_CEILING - attempts_used,
            "remaining_retry_reserve": _RETRY_RESERVE - client.state.retries,
        },
        "rate_control": {
            "concurrency": 1,
            "target_requests_per_second": 1,
            "minimum_start_interval_seconds": _minimum_interval(client.request_start_times),
            "rate_limit_responses": client.state.rate_limit_responses,
            "timeout_seconds": _TIMEOUT_SECONDS,
            "wall_clock_ceiling_minutes": 45,
        },
        "validation": report.to_dict(),
        "restrictions": {
            "raw_responses_retained": False,
            "ingestion_authorized": False,
            "model_implementation_authorized": False,
            "evaluation_v2_authorized": False,
            "full_audit_authorized_after_pilot": False,
            "mandatory_rust_requirement_changed": False,
        },
    }
    del season_inputs, audit, report
    return result


def main() -> int:
    try:
        api_key = _read_env_secret(Path(".env"), _TOKEN_NAME)
        report = run_pilot(api_key)
    except PilotStop as error:
        print(
            json.dumps(
                {
                    "contract": "PitchApiLiveAuditPilotStopV1",
                    "status": "STOPPED",
                    "stop_code": error.code,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    finally:
        if "api_key" in locals():
            del api_key
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 2 if report["status"] == "STOPPED" else 0


def _stopped_report(client: PilotHttpClient, stop_code: str) -> dict[str, object]:
    attempts_used = len(client.records)
    return {
        "contract": "PitchApiLiveAuditPilotStopV1",
        "status": "STOPPED",
        "stop_code": stop_code,
        "request_budget": {
            "pilot_base_attempts": _PILOT_BASE_ATTEMPTS,
            "pilot_attempt_ceiling": _PILOT_ATTEMPT_CEILING,
            "original_audit_attempt_ceiling": _ORIGINAL_AUDIT_CEILING,
            "absolute_remaining_ceiling_before_run": _REMAINING_AUDIT_CEILING,
            "prior_attempts_used": _PRIOR_ATTEMPTS_USED,
            "attempts_used_this_run": attempts_used,
            "cumulative_attempts_used": _PRIOR_ATTEMPTS_USED + attempts_used,
            "retries_used": client.state.retries,
            "remaining_total_attempts": _REMAINING_AUDIT_CEILING - attempts_used,
            "remaining_retry_reserve": _RETRY_RESERVE - client.state.retries,
        },
        "rate_control": {
            "concurrency": 1,
            "target_requests_per_second": 1,
            "minimum_start_interval_seconds": _minimum_interval(client.request_start_times),
            "rate_limit_responses": client.state.rate_limit_responses,
            "timeout_seconds": _TIMEOUT_SECONDS,
            "wall_clock_ceiling_minutes": 45,
        },
        "restrictions": {
            "raw_responses_retained": False,
            "full_audit_authorized_after_pilot": False,
        },
    }


def _normalized_fixture(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise PilotStop("MALFORMED_MANIFEST_FIXTURE")
    match_id = value.get("id")
    home_team = value.get("home_team")
    away_team = value.get("away_team")
    kickoff = value.get("time_utc")
    if not _provider_id(match_id, "m_"):
        raise PilotStop("MALFORMED_MANIFEST_FIXTURE")
    if not isinstance(home_team, Mapping) or not isinstance(away_team, Mapping):
        raise PilotStop("MALFORMED_MANIFEST_FIXTURE")
    home_id = home_team.get("id")
    away_id = away_team.get("id")
    if not _provider_id(home_id, "t_") or not _provider_id(away_id, "t_"):
        raise PilotStop("MALFORMED_MANIFEST_FIXTURE")
    if home_id == away_id or value.get("status") != "finished" or not _timestamp(kickoff):
        raise PilotStop("INVALID_MANIFEST_FIXTURE")
    return {
        "id": str(match_id),
        "date": str(value.get("date", "")),
        "time_utc": str(kickoff),
        "status": "finished",
        "home_team": {"id": str(home_id)},
        "away_team": {"id": str(away_id)},
        "score_home": value.get("score_home"),
        "score_away": value.get("score_away"),
        "has_playoff": value.get("has_playoff"),
    }


def _read_env_secret(path: Path, name: str) -> str:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                if key.strip() != name:
                    continue
                secret = value.strip().strip('"').strip("'")
                if not secret or any(character.isspace() for character in secret):
                    raise PilotStop("INVALID_CREDENTIAL")
                return secret
    except (OSError, UnicodeDecodeError):
        raise PilotStop("CREDENTIAL_FILE_UNAVAILABLE") from None
    raise PilotStop("MISSING_CREDENTIAL")


def _identity_sha256(matches: Sequence[Mapping[str, object]]) -> str:
    identity = [[match["id"], match["time_utc"]] for match in matches]
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _dependency_lock_sha256() -> str:
    return hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest()


def _minimum_interval(starts: Sequence[float]) -> float | None:
    if len(starts) < 2:
        return None
    return round(
        min(current - previous for previous, current in zip(starts, starts[1:], strict=False)),
        3,
    )


def _retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _safe_provider_code(status: int) -> str:
    return "RATE_LIMIT_EXCEEDED" if status == 429 else f"HTTP_{status}"


def _provider_id(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and len(value) > len(prefix)
        and value[len(prefix) :].isalnum()
    )


def _timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


if __name__ == "__main__":
    raise SystemExit(main())
