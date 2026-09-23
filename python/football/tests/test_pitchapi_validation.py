from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime

import pytest
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
from football.validation.pitchapi_contingency import PitchApiSeriesGateReportV1


def _scope(
    key: str,
    league_id: str,
    season: str,
    expected_match_count: int,
) -> PitchApiSeasonScope:
    return PitchApiSeasonScope(
        key=key,
        league_id=league_id,
        season=season,
        expected_match_count=expected_match_count,
    )


def _fixture_payload(scope: PitchApiSeasonScope, match_ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "data": {
            "league": {
                "id": scope.league_id,
                "name": scope.key,
                "season": scope.season,
            },
            "matches": [
                {
                    "id": match_id,
                    "date": f"2023-08-{index + 1:02d}",
                    "time_utc": f"2023-08-{index + 1:02d}T18:30:00Z",
                    "status": "finished",
                    "home_team": {"id": f"t_home{index}", "name": "Home"},
                    "away_team": {"id": f"t_away{index}", "name": "Away"},
                    "score_home": 1,
                    "score_away": 0,
                }
                for index, match_id in enumerate(match_ids)
            ],
        }
    }


def _shot(
    shot_id: str,
    team_id: str,
    *,
    expected_goals: object = 0.25,
    situation: object = "RegularPlay",
) -> dict[str, object]:
    return {
        "id": shot_id,
        "team_id": team_id,
        "expected_goals": expected_goals,
        "situation": situation,
        "shot_type": "RightFoot",
        "minute": 12,
        "event_type": "AttemptSaved",
    }


def _shot_payload(
    match_id: str,
    *,
    first_half: list[dict[str, object]] | None = None,
    second_half: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    periods: list[dict[str, object]] = []
    if first_half is not None:
        periods.append({"period": "FirstHalf", "shots": first_half})
    if second_half is not None:
        periods.append({"period": "SecondHalf", "shots": second_half})
    return {"data": {"match_id": match_id, "periods": periods}}


def _metadata() -> PitchApiAuditMetadata:
    return PitchApiAuditMetadata(
        endpoint_version="v1",
        observed_provider_version="docs-2026-09-23",
        acquisition_started_at=datetime(2026, 9, 23, 12, 0, tzinfo=UTC),
        acquisition_ended_at=datetime(2026, 9, 23, 12, 5, tzinfo=UTC),
        code_git_sha="a" * 40,
        dependency_lock_sha256="b" * 64,
        credential_reference="env:PITCH_API_TOKEN",
    )


def _evidence(
    *, xg_series_by_scope: dict[str, str | None] | None = None
) -> PitchApiQualificationEvidence:
    return PitchApiQualificationEvidence(
        automated_private_research_permitted=True,
        immutable_raw_retention_permitted=True,
        attribution_requirements_recorded=True,
        correction_history_available=True,
        immutable_revision_identity_available=True,
        stable_identifier_policy_available=True,
        xg_series_by_scope=xg_series_by_scope
        or {"bundesliga": "provider:model:v1", "ligue1": "provider:model:v1"},
        source_series_gate=PitchApiSeriesGateReportV1(
            status="PASS",
            series_identity_sha256="c" * 64,
            findings=(),
        ),
    )


def _audit(
    *,
    first_payload: Mapping[str, object] | None = None,
    second_payload: Mapping[str, object] | None = None,
    first_shots: Mapping[str, Mapping[str, object] | None] | None = None,
    second_shots: Mapping[str, Mapping[str, object] | None] | None = None,
    request_log: tuple[PitchApiRequestRecord, ...] | None = None,
    request_ceiling: int = 5,
    evidence: PitchApiQualificationEvidence | None = None,
) -> PitchApiAuditInput:
    bundesliga = _scope("bundesliga", "l_1Isor4", "2023/2024", 2)
    ligue1 = _scope("ligue1", "l_3FJFUl", "2022/2023", 1)
    first_match_ids = ("m_b01", "m_b02")
    second_match_ids = ("m_f01",)
    first_payload = first_payload or _fixture_payload(bundesliga, first_match_ids)
    second_payload = second_payload or _fixture_payload(ligue1, second_match_ids)
    first_shots = first_shots or {
        "m_b01": _shot_payload(
            "m_b01",
            first_half=[_shot("s_01", "t_home0")],
            second_half=[_shot("s_02", "t_away0", situation="Penalty")],
        ),
        "m_b02": _shot_payload("m_b02"),
    }
    second_shots = second_shots or {
        "m_f01": _shot_payload(
            "m_f01",
            first_half=[_shot("s_01", "t_home0")],
            second_half=[],
        )
    }
    if request_log is None:
        request_log = (
            PitchApiRequestRecord(
                path="/v1/leagues/l_1Isor4/matches?season=2023%2F2024",
                status_code=200,
            ),
            PitchApiRequestRecord(path="/v1/matches/m_b01/shots", status_code=200),
            PitchApiRequestRecord(path="/v1/matches/m_b02/shots", status_code=200),
            PitchApiRequestRecord(
                path="/v1/leagues/l_3FJFUl/matches?season=2022%2F2023",
                status_code=200,
            ),
            PitchApiRequestRecord(path="/v1/matches/m_f01/shots", status_code=200),
        )
    return PitchApiAuditInput(
        seasons=(
            PitchApiSeasonAuditInput(bundesliga, first_payload, first_shots),
            PitchApiSeasonAuditInput(ligue1, second_payload, second_shots),
        ),
        request_log=request_log,
        budget=PitchApiRequestBudget(ceiling=request_ceiling, retry_reserve=0),
        metadata=_metadata(),
        qualification_evidence=evidence or _evidence(),
    )


def _codes(audit: PitchApiAuditInput) -> set[str]:
    return {finding.code for finding in validate_pitchapi_audit(audit).findings}


def test_complete_audit_passes_and_counts_penalties_and_empty_resources() -> None:
    report = validate_pitchapi_audit(_audit())

    assert report.technical_status == "PASS"
    assert report.evaluation_v2_status == "PASS"
    assert report.cross_season_xg_series_status == "PASS"
    assert report.request_count == 5
    assert report.total_matches == 3
    assert report.total_shots == 3
    assert report.total_penalties == 1
    assert report.total_regulation_shots == 3
    assert report.total_empty_shot_resources == 1
    assert report.findings == ()


def test_missing_shot_resource_is_not_treated_as_zero_shots() -> None:
    report = validate_pitchapi_audit(
        _audit(first_shots={"m_b01": _shot_payload("m_b01"), "m_b02": None})
    )

    assert report.technical_status == "FAIL"
    assert report.evaluation_v2_status == "FAIL"
    assert "MISSING_SHOT_RESOURCE" in {finding.code for finding in report.findings}
    bundesliga = next(item for item in report.seasons if item.scope_key == "bundesliga")
    assert bundesliga.empty_shot_resources == 1
    assert bundesliga.missing_shot_resources == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01, True, "0.4"])
def test_rejects_non_finite_out_of_range_or_non_numeric_xg(value: object) -> None:
    shots = {
        "m_b01": _shot_payload(
            "m_b01", first_half=[_shot("s_bad", "t_home0", expected_goals=value)]
        ),
        "m_b02": _shot_payload("m_b02"),
    }

    report = validate_pitchapi_audit(_audit(first_shots=shots))

    assert report.technical_status == "FAIL"
    assert "INVALID_EXPECTED_GOALS" in {finding.code for finding in report.findings}
    assert report.invalid_xg_count == 1


def test_penalty_identification_uses_only_exact_situation_value() -> None:
    shots = {
        "m_b01": _shot_payload(
            "m_b01",
            first_half=[
                _shot("s_penalty1", "t_home0", expected_goals=0.78, situation="Penalty"),
                _shot("s_nonpenalty1", "t_home0", expected_goals=0.78),
            ],
        ),
        "m_b02": _shot_payload("m_b02"),
    }

    report = validate_pitchapi_audit(_audit(first_shots=shots))

    assert report.total_penalties == 1
    assert report.technical_status == "PASS"


def test_rejects_unknown_or_missing_period_without_minute_inference() -> None:
    unknown = _shot_payload("m_b01")
    unknown["data"]["periods"] = [  # type: ignore[index]
        {"period": "ExtraTime", "shots": [_shot("s_01", "t_home0")]},
        {"shots": [_shot("s_02", "t_home0")]},
    ]
    shots = {"m_b01": unknown, "m_b02": _shot_payload("m_b02")}

    report = validate_pitchapi_audit(_audit(first_shots=shots))

    assert report.technical_status == "FAIL"
    bundesliga = next(item for item in report.seasons if item.scope_key == "bundesliga")
    assert bundesliga.regulation_shots == 0
    assert {"UNKNOWN_PERIOD", "MISSING_PERIOD"} <= {finding.code for finding in report.findings}


def test_rejects_unknown_or_missing_situation() -> None:
    first = _shot("s_01", "t_home0", situation="NewProviderValue")
    second = _shot("s_02", "t_home0")
    del second["situation"]
    shots = {
        "m_b01": _shot_payload("m_b01", first_half=[first, second]),
        "m_b02": _shot_payload("m_b02"),
    }

    report = validate_pitchapi_audit(_audit(first_shots=shots))

    assert {"UNKNOWN_SITUATION", "MISSING_SITUATION"} <= {
        finding.code for finding in report.findings
    }
    bundesliga = next(item for item in report.seasons if item.scope_key == "bundesliga")
    assert bundesliga.missing_fields == 1


def test_malformed_period_is_not_reported_as_a_valid_empty_resource() -> None:
    malformed: dict[str, object] = {
        "data": {"match_id": "m_b01", "periods": [{"period": "FirstHalf"}]}
    }
    shots = {"m_b01": malformed, "m_b02": _shot_payload("m_b02")}

    report = validate_pitchapi_audit(_audit(first_shots=shots))

    bundesliga = next(item for item in report.seasons if item.scope_key == "bundesliga")
    assert bundesliga.malformed_shot_resources == 1
    assert bundesliga.empty_shot_resources == 1
    assert "MALFORMED_PERIOD" in {finding.code for finding in report.findings}


def test_rejects_duplicate_shot_ids_within_match_but_allows_match_scoped_reuse() -> None:
    duplicate = {
        "m_b01": _shot_payload(
            "m_b01",
            first_half=[_shot("s_same", "t_home0")],
            second_half=[_shot("s_same", "t_away0")],
        ),
        "m_b02": _shot_payload("m_b02"),
    }
    assert "DUPLICATE_SHOT_ID" in _codes(_audit(first_shots=duplicate))

    scoped_reuse = deepcopy(duplicate)
    scoped_reuse["m_b01"] = _shot_payload("m_b01", first_half=[_shot("s_same", "t_home0")])
    assert "DUPLICATE_SHOT_ID" not in _codes(_audit(first_shots=scoped_reuse))


def test_rejects_duplicate_match_ids_and_partial_seasons() -> None:
    scope = _scope("bundesliga", "l_1Isor4", "2023/2024", 2)
    duplicate = _fixture_payload(scope, ("m_same", "m_same"))
    partial = _fixture_payload(scope, ("m_only",))

    assert "DUPLICATE_MATCH_ID" in _codes(_audit(first_payload=duplicate))
    assert "MATCH_COUNT_MISMATCH" in _codes(_audit(first_payload=partial))


def test_rejects_shot_team_outside_fixture_and_mismatched_response_match() -> None:
    mismatch = _shot_payload("m_other", first_half=[_shot("s_01", "t_not_in_fixture")])
    shots = {"m_b01": mismatch, "m_b02": _shot_payload("m_b02")}

    codes = _codes(_audit(first_shots=shots))

    assert "SHOT_RESPONSE_MATCH_MISMATCH" in codes
    assert "SHOT_TEAM_NOT_IN_FIXTURE" in codes


def test_request_budget_and_unbudgeted_paths_stop_audit() -> None:
    too_many = (*_audit().request_log, PitchApiRequestRecord(path="/v1/leagues", status_code=200))
    report = validate_pitchapi_audit(_audit(request_log=too_many, request_ceiling=5))

    assert report.stopped is True
    assert report.technical_status == "FAIL"
    assert {"REQUEST_BUDGET_EXCEEDED", "UNBUDGETED_REQUEST_PATH"} <= {
        finding.code for finding in report.findings
    }


def test_authentication_failure_and_repeated_rate_limit_stop_audit() -> None:
    unauthorized = list(_audit().request_log)
    unauthorized[0] = PitchApiRequestRecord(path=unauthorized[0].path, status_code=401)
    auth_report = validate_pitchapi_audit(_audit(request_log=tuple(unauthorized)))
    assert auth_report.stopped is True
    assert "AUTHORIZATION_FAILED" in {finding.code for finding in auth_report.findings}

    path = "/v1/matches/m_b01/shots"
    rate_limited = (
        *_audit().request_log,
        PitchApiRequestRecord(
            path=path,
            status_code=429,
            provider_code="RATE_LIMIT_EXCEEDED",
            retry_after_seconds=10,
        ),
        PitchApiRequestRecord(
            path=path,
            status_code=429,
            provider_code="RATE_LIMIT_EXCEEDED",
            retry_after_seconds=10,
        ),
    )
    rate_report = validate_pitchapi_audit(
        PitchApiAuditInput(
            seasons=_audit().seasons,
            request_log=rate_limited,
            budget=PitchApiRequestBudget(ceiling=7, retry_reserve=2),
            metadata=_metadata(),
            qualification_evidence=_evidence(),
        )
    )
    assert rate_report.stopped is True
    assert "REPEATED_RATE_LIMIT" in {finding.code for finding in rate_report.findings}


def test_transport_failure_is_sanitized_and_counted_per_season() -> None:
    request_log = list(_audit().request_log)
    request_log[1] = PitchApiRequestRecord(
        path=request_log[1].path,
        failure_kind="timeout",
    )

    report = validate_pitchapi_audit(_audit(request_log=tuple(request_log)))

    bundesliga = next(item for item in report.seasons if item.scope_key == "bundesliga")
    assert bundesliga.request_failures == 1
    assert "REQUEST_FAILED" in {finding.code for finding in report.findings}
    assert "timeout" not in str(report.to_dict())


def test_cross_season_series_is_partial_when_unknown_and_fails_when_mixed() -> None:
    unknown = validate_pitchapi_audit(
        _audit(evidence=_evidence(xg_series_by_scope={"bundesliga": None, "ligue1": None}))
    )
    assert unknown.technical_status == "PARTIAL"
    assert unknown.cross_season_xg_series_status == "UNPROVED"
    assert unknown.evaluation_v2_status == "FAIL"

    mixed = validate_pitchapi_audit(
        _audit(
            evidence=_evidence(
                xg_series_by_scope={
                    "bundesliga": "provider:model:v1",
                    "ligue1": "provider:model:v2",
                }
            )
        )
    )
    assert mixed.technical_status == "FAIL"
    assert mixed.cross_season_xg_series_status == "FAIL"
    assert "MIXED_XG_SERIES" in {finding.code for finding in mixed.findings}


def test_evaluation_status_fails_when_retention_or_correction_evidence_is_missing() -> None:
    evidence = PitchApiQualificationEvidence(
        automated_private_research_permitted=True,
        immutable_raw_retention_permitted=False,
        attribution_requirements_recorded=True,
        correction_history_available=False,
        immutable_revision_identity_available=False,
        stable_identifier_policy_available=False,
        xg_series_by_scope={"bundesliga": "provider:model:v1", "ligue1": "provider:model:v1"},
        source_series_gate=None,
    )

    report = validate_pitchapi_audit(_audit(evidence=evidence))

    assert report.technical_status == "PASS"
    assert report.evaluation_v2_status == "FAIL"
    assert "EVALUATION_PERMISSION_OR_LINEAGE_UNPROVED" in {
        finding.code for finding in report.findings
    }


def test_equal_free_form_series_labels_do_not_qualify_without_attested_gate() -> None:
    evidence = _evidence()
    evidence = PitchApiQualificationEvidence(
        automated_private_research_permitted=evidence.automated_private_research_permitted,
        immutable_raw_retention_permitted=evidence.immutable_raw_retention_permitted,
        attribution_requirements_recorded=evidence.attribution_requirements_recorded,
        correction_history_available=evidence.correction_history_available,
        immutable_revision_identity_available=evidence.immutable_revision_identity_available,
        stable_identifier_policy_available=evidence.stable_identifier_policy_available,
        xg_series_by_scope=evidence.xg_series_by_scope,
        source_series_gate=None,
    )

    report = validate_pitchapi_audit(_audit(evidence=evidence))

    assert report.cross_season_xg_series_status == "PASS"
    assert report.evaluation_v2_status == "FAIL"
    assert "EVALUATION_PERMISSION_OR_LINEAGE_UNPROVED" in {
        finding.code for finding in report.findings
    }


def test_malformed_payloads_fail_without_echoing_secrets() -> None:
    secret = "synthetic-secret-that-must-not-echo"
    malformed = {"data": {"league": {"id": secret}, "matches": secret}}

    report = validate_pitchapi_audit(_audit(first_payload=malformed))
    serialized = str(report.to_dict())

    assert report.technical_status == "FAIL"
    assert "MALFORMED_FIXTURE_PAYLOAD" in {finding.code for finding in report.findings}
    assert secret not in serialized
    assert secret not in repr(report)


def test_metadata_requires_non_secret_credential_reference() -> None:
    with pytest.raises(ValueError, match="credential reference"):
        PitchApiAuditMetadata(
            endpoint_version="v1",
            observed_provider_version=None,
            acquisition_started_at=datetime(2026, 9, 23, tzinfo=UTC),
            acquisition_ended_at=datetime(2026, 9, 23, 0, 1, tzinfo=UTC),
            code_git_sha="a" * 40,
            dependency_lock_sha256="b" * 64,
            credential_reference="synthetic-secret-that-must-not-be-stored",
        )
