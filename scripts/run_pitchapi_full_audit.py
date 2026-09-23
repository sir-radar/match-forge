#!/usr/bin/env python3
"""Run the owner-approved PitchAPI continuation without retaining raw responses."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiSeasonAuditInput,
    PitchApiSeasonScope,
    validate_pitchapi_audit,
)

from scripts.run_pitchapi_validation_pilot import (
    PilotHttpClient,
    PilotManifestSelection,
    PilotStop,
    _dependency_lock_sha256,
    _git_sha,
    _minimum_interval,
    _read_env_secret,
    select_pilot_manifest,
)

_PILOT_EVIDENCE = Path("docs/evidence/pitchapi-live-audit-replacement-pilot-2026-09-23.json")
_TOKEN_NAME = "PITCH_API_TOKEN"
_PRIOR_ATTEMPTS_USED = 24
_REMAINING_ATTEMPT_CEILING = 678
_BASE_ATTEMPTS = 668
_RETRY_RESERVE = 10
_SAMPLE_SIZE = 10
_SCOPES = (
    PitchApiSeasonScope("bundesliga", "l_1Isor4", "2023/2024", _SAMPLE_SIZE),
    PitchApiSeasonScope("ligue1", "l_3FJFUl", "2022/2023", _SAMPLE_SIZE),
)
_EXPECTED_MANIFESTS: Mapping[str, Mapping[str, object]] = {
    "bundesliga": {
        "match_count": 306,
        "manifest_identity_sha256": (
            "6e528b44917ec41c2d2565fb2d9ccb879a40ae1c7ed456c6a29c213f213241a1"
        ),
        "selection_sha256": "e5b54af79f531df4222e69fd0d47d0354e008580cf457b0f0e03245fda21aef1",
    },
    "ligue1": {
        "match_count": 380,
        "manifest_identity_sha256": (
            "6d9d73c27a5cdc7947b255608ebdd8e9d1657df27d8cf86bb595322c78caa3f2"
        ),
        "selection_sha256": "18f7f76b6f3d7f92b2645bc70d5191160b21e4865b9296ecedf8f2348994e48b",
    },
}
_COUNT_FIELDS = (
    "successful_shot_resources",
    "empty_shot_resources",
    "missing_shot_resources",
    "malformed_shot_resources",
    "shots",
    "penalties",
    "regulation_shots",
    "invalid_xg",
    "duplicate_shot_ids",
    "unknown_periods",
    "unknown_situations",
    "missing_fields",
    "request_failures",
)


def run_full_audit(api_key: str, pilot_evidence: Mapping[str, Any]) -> dict[str, object]:
    client = PilotHttpClient(
        api_key,
        attempt_ceiling=_REMAINING_ATTEMPT_CEILING,
        retry_reserve=_RETRY_RESERVE,
    )
    try:
        return _execute_full_audit(client, pilot_evidence)
    except PilotStop as error:
        return _stopped_report(client, error.code)


def _execute_full_audit(
    client: PilotHttpClient,
    pilot_evidence: Mapping[str, Any],
) -> dict[str, object]:
    pilot_seasons = validate_pilot_evidence(pilot_evidence)
    started_at = datetime.now(UTC)
    selections: dict[str, PilotManifestSelection] = {}
    for scope in _SCOPES:
        payload = client.get_json(scope.manifest_path)
        selection = select_pilot_manifest(
            payload,
            scope,
            full_expected_match_count=_expected_match_count(scope.key),
        )
        verify_manifest_hashes(scope.key, selection)
        selections[scope.key] = selection
        del payload

    season_inputs: list[PitchApiSeasonAuditInput] = []
    processed = 0
    for scope in _SCOPES:
        selection = selections[scope.key]
        remaining_matches = selection.ordered_matches[_SAMPLE_SIZE:]
        remaining_scope = PitchApiSeasonScope(
            scope.key,
            scope.league_id,
            scope.season,
            len(remaining_matches),
        )
        fixture_payload = {
            "data": {
                "league": {
                    "id": scope.league_id,
                    "name": scope.key,
                    "season": scope.season,
                },
                "matches": list(remaining_matches),
            }
        }
        shot_payloads: dict[str, Mapping[str, Any]] = {}
        for match in remaining_matches:
            match_id = str(match["id"])
            shot_payloads[match_id] = client.get_json(f"/v1/matches/{match_id}/shots")
            processed += 1
            if processed % 50 == 0 or processed == 666:
                _progress(processed, client)
        season_inputs.append(
            PitchApiSeasonAuditInput(remaining_scope, fixture_payload, shot_payloads)
        )

    ended_at = datetime.now(UTC)
    audit = PitchApiAuditInput(
        seasons=tuple(season_inputs),
        request_log=tuple(client.records),
        budget=PitchApiRequestBudget(
            ceiling=_REMAINING_ATTEMPT_CEILING,
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
    audit_report = validate_pitchapi_audit(audit)
    remaining_reports = {report.scope_key: report.to_dict() for report in audit_report.seasons}
    combined_seasons = [
        combine_season_reports(
            scope.key,
            _expected_match_count(scope.key),
            pilot_seasons[scope.key],
            remaining_reports[scope.key],
        )
        for scope in _SCOPES
    ]
    attempts_used = len(client.records)
    result: dict[str, object] = {
        "contract": "PitchApiFullSeasonAuditReportV1",
        "status": "STOPPED" if audit_report.stopped else "COMPLETED",
        "coverage_basis": "pilot_aggregates_plus_hash_locked_unsampled_resources_v1",
        "manifests": {
            key: {
                "observed_matches": selection.observed_match_count,
                "manifest_identity_sha256": selection.manifest_identity_sha256,
                "selection_sha256": selection.selection_sha256,
                "pilot_hashes_matched": True,
            }
            for key, selection in selections.items()
        },
        "request_budget": _request_budget(client, attempts_used),
        "rate_control": _rate_control(client),
        "validation": {
            "technical_status": audit_report.technical_status,
            "evaluation_v2_status": audit_report.evaluation_v2_status,
            "cross_season_xg_series_status": audit_report.cross_season_xg_series_status,
            "stopped": audit_report.stopped,
            "seasons": combined_seasons,
            "totals": _totals(combined_seasons),
            "findings": [finding.to_dict() for finding in audit_report.findings],
            "metadata": audit_report.to_dict()["metadata"],
        },
        "restrictions": _restrictions(),
    }
    del season_inputs, audit, audit_report, selections
    return result


def validate_pilot_evidence(evidence: Mapping[str, Any]) -> dict[str, Mapping[str, object]]:
    if evidence.get("contract") != "PitchApiLiveAuditPilotReportV1":
        raise PilotStop("PILOT_EVIDENCE_CONTRACT_MISMATCH")
    if evidence.get("status") != "COMPLETED":
        raise PilotStop("PILOT_EVIDENCE_NOT_COMPLETE")
    manifests = evidence.get("manifests")
    validation = evidence.get("validation")
    if not isinstance(manifests, Mapping) or not isinstance(validation, Mapping):
        raise PilotStop("MALFORMED_PILOT_EVIDENCE")
    _validate_pilot_manifests(manifests)
    return _pilot_seasons(validation)


def _validate_pilot_manifests(manifests: Mapping[object, object]) -> None:
    for key, expected in _EXPECTED_MANIFESTS.items():
        actual = manifests.get(key)
        if not isinstance(actual, Mapping):
            raise PilotStop("MALFORMED_PILOT_EVIDENCE")
        if actual.get("observed_matches") != expected["match_count"]:
            raise PilotStop("PILOT_EVIDENCE_MATCH_COUNT_MISMATCH")
        if actual.get("manifest_identity_sha256") != expected["manifest_identity_sha256"]:
            raise PilotStop("PILOT_EVIDENCE_MANIFEST_HASH_MISMATCH")
        if actual.get("selection_sha256") != expected["selection_sha256"]:
            raise PilotStop("PILOT_EVIDENCE_SELECTION_HASH_MISMATCH")


def _pilot_seasons(validation: Mapping[object, object]) -> dict[str, Mapping[str, object]]:
    seasons = validation.get("seasons")
    if not _sequence(seasons):
        raise PilotStop("MALFORMED_PILOT_EVIDENCE")
    by_key: dict[str, Mapping[str, object]] = {}
    for item in cast(Sequence[object], seasons):
        if not isinstance(item, Mapping) or not isinstance(item.get("scope_key"), str):
            raise PilotStop("MALFORMED_PILOT_EVIDENCE")
        by_key[str(item["scope_key"])] = cast(Mapping[str, object], item)
    if set(by_key) != set(_EXPECTED_MANIFESTS):
        raise PilotStop("PILOT_EVIDENCE_SCOPE_MISMATCH")
    if any(item.get("observed_matches") != _SAMPLE_SIZE for item in by_key.values()):
        raise PilotStop("PILOT_EVIDENCE_SAMPLE_COUNT_MISMATCH")
    return by_key


def verify_manifest_hashes(scope_key: str, selection: PilotManifestSelection) -> None:
    expected = _EXPECTED_MANIFESTS[scope_key]
    if selection.observed_match_count != expected["match_count"]:
        raise PilotStop("FULL_SEASON_MATCH_COUNT_MISMATCH")
    if selection.manifest_identity_sha256 != expected["manifest_identity_sha256"]:
        raise PilotStop("MANIFEST_IDENTITY_HASH_MISMATCH")
    if selection.selection_sha256 != expected["selection_sha256"]:
        raise PilotStop("SELECTION_HASH_MISMATCH")


def combine_season_reports(
    scope_key: str,
    expected_matches: int,
    pilot: Mapping[str, object],
    remainder: Mapping[str, object],
) -> dict[str, object]:
    result: dict[str, object] = {
        "scope_key": scope_key,
        "expected_matches": expected_matches,
        "observed_matches": _integer(pilot, "observed_matches")
        + _integer(remainder, "observed_matches"),
    }
    for field in _COUNT_FIELDS:
        result[field] = _integer(pilot, field) + _integer(remainder, field)
    return result


def _request_budget(client: PilotHttpClient, attempts_used: int) -> dict[str, int]:
    return {
        "original_audit_attempt_ceiling": 702,
        "prior_attempts_used": _PRIOR_ATTEMPTS_USED,
        "absolute_remaining_ceiling_before_run": _REMAINING_ATTEMPT_CEILING,
        "base_attempts_authorized": _BASE_ATTEMPTS,
        "attempts_used_this_run": attempts_used,
        "cumulative_attempts_used": _PRIOR_ATTEMPTS_USED + attempts_used,
        "retries_used_this_run": client.state.retries,
        "remaining_total_attempts": _REMAINING_ATTEMPT_CEILING - attempts_used,
        "remaining_retry_reserve": _RETRY_RESERVE - client.state.retries,
    }


def _rate_control(client: PilotHttpClient) -> dict[str, object]:
    return {
        "concurrency": 1,
        "target_requests_per_second": 1,
        "minimum_start_interval_seconds": _minimum_interval(client.request_start_times),
        "rate_limit_responses": client.state.rate_limit_responses,
        "timeout_seconds": 30,
        "wall_clock_ceiling_minutes": 45,
    }


def _stopped_report(client: PilotHttpClient, stop_code: str) -> dict[str, object]:
    attempts_used = len(client.records)
    return {
        "contract": "PitchApiFullSeasonAuditStopV1",
        "status": "STOPPED",
        "stop_code": stop_code,
        "request_budget": _request_budget(client, attempts_used),
        "rate_control": _rate_control(client),
        "restrictions": _restrictions(),
    }


def _restrictions() -> dict[str, bool]:
    return {
        "raw_responses_retained": False,
        "ingestion_authorized": False,
        "model_implementation_authorized": False,
        "evaluation_v2_authorized": False,
        "corpus_admission_authorized": False,
        "mandatory_rust_requirement_changed": False,
    }


def _totals(seasons: Sequence[Mapping[str, object]]) -> dict[str, int]:
    fields = ("observed_matches",) + _COUNT_FIELDS
    return {field: sum(_integer(season, field) for season in seasons) for field in fields}


def _integer(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool) or item < 0:
        raise PilotStop("MALFORMED_AGGREGATE_EVIDENCE")
    return item


def _expected_match_count(scope_key: str) -> int:
    value = _EXPECTED_MANIFESTS[scope_key].get("match_count")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PilotStop("INVALID_FROZEN_MATCH_COUNT")
    return value


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _progress(processed: int, client: PilotHttpClient) -> None:
    print(
        json.dumps(
            {
                "event": "sanitized_progress",
                "unsampled_shot_resources_processed": processed,
                "attempts_used_this_run": len(client.records),
                "retries_used_this_run": client.state.retries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
        flush=True,
    )


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise PilotStop("PILOT_EVIDENCE_UNAVAILABLE") from None
    if not isinstance(value, Mapping):
        raise PilotStop("MALFORMED_PILOT_EVIDENCE")
    return value


def main() -> int:
    try:
        pilot_evidence = _load_json(_PILOT_EVIDENCE)
        api_key = _read_env_secret(Path(".env"), _TOKEN_NAME)
        report = run_full_audit(api_key, pilot_evidence)
    except PilotStop as error:
        print(
            json.dumps(
                {
                    "contract": "PitchApiFullSeasonAuditStopV1",
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


if __name__ == "__main__":
    raise SystemExit(main())
