from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import quote

AuditStatus = Literal["PASS", "PARTIAL", "FAIL"]
SeriesStatus = Literal["PASS", "UNPROVED", "FAIL"]
FindingDomain = Literal["technical", "evaluation_v2"]
FindingSeverity = Literal["ERROR", "WARNING"]
RequestFailureKind = Literal["timeout", "network_error"]

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ID_PATTERNS = {
    "league": re.compile(r"^l_[A-Za-z0-9]+$"),
    "match": re.compile(r"^m_[A-Za-z0-9]+$"),
    "team": re.compile(r"^t_[A-Za-z0-9]+$"),
    "shot": re.compile(r"^s_[A-Za-z0-9]+$"),
}
_REGULATION_PERIODS = frozenset(("FirstHalf", "SecondHalf"))
_SHOT_SITUATIONS = frozenset(
    (
        "RegularPlay",
        "FromCorner",
        "SetPiece",
        "FastBreak",
        "FreeKick",
        "ThrowInSetPiece",
        "Penalty",
        "IndividualPlay",
    )
)


@dataclass(frozen=True, slots=True)
class PitchApiSeasonScope:
    key: str
    league_id: str
    season: str
    expected_match_count: int

    def __post_init__(self) -> None:
        if not self.key or not _valid_id(self.league_id, "league"):
            raise ValueError("scope key and valid PitchAPI league ID are required")
        if not re.fullmatch(r"[0-9]{4}/[0-9]{4}", self.season):
            raise ValueError("season must use YYYY/YYYY")
        if self.expected_match_count <= 0:
            raise ValueError("expected match count must be positive")

    @property
    def manifest_path(self) -> str:
        return f"/v1/leagues/{self.league_id}/matches?season={quote(self.season, safe='')}"


@dataclass(frozen=True, slots=True)
class PitchApiSeasonAuditInput:
    scope: PitchApiSeasonScope
    fixture_payload: Mapping[str, Any]
    shot_payloads: Mapping[str, Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class PitchApiRequestRecord:
    path: str
    status_code: int | None = None
    provider_code: str | None = None
    request_id_present: bool = False
    retry_after_seconds: int | None = None
    failure_kind: RequestFailureKind | None = None
    method: str = "GET"

    def __post_init__(self) -> None:
        if not self.path.startswith("/v1/") or any(char.isspace() for char in self.path):
            raise ValueError("request path must be a sanitized PitchAPI v1 path")
        if self.method != "GET":
            raise ValueError("PitchAPI qualification requests must be read-only GET requests")
        if (self.status_code is None) == (self.failure_kind is None):
            raise ValueError("request record requires exactly one response or transport failure")
        if self.status_code is not None and not 100 <= self.status_code <= 599:
            raise ValueError("request status code is invalid")
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("Retry-After seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class PitchApiRequestBudget:
    ceiling: int
    retry_reserve: int
    max_attempts_per_path: int = 2
    max_rate_limit_responses: int = 1

    def __post_init__(self) -> None:
        if self.ceiling <= 0:
            raise ValueError("request ceiling must be positive")
        if not 0 <= self.retry_reserve < self.ceiling:
            raise ValueError("retry reserve must be non-negative and below the ceiling")
        if self.max_attempts_per_path not in (1, 2):
            raise ValueError("at most one retry per path is supported")
        if self.max_rate_limit_responses != 1:
            raise ValueError("the audit permits exactly one rate-limit response before stopping")


@dataclass(frozen=True, slots=True)
class PitchApiAuditMetadata:
    endpoint_version: str
    observed_provider_version: str | None
    acquisition_started_at: datetime
    acquisition_ended_at: datetime
    code_git_sha: str
    dependency_lock_sha256: str
    credential_reference: str

    def __post_init__(self) -> None:
        if self.endpoint_version != "v1":
            raise ValueError("PitchAPI endpoint version must be v1")
        if not _timezone_aware(self.acquisition_started_at) or not _timezone_aware(
            self.acquisition_ended_at
        ):
            raise ValueError("audit timestamps must include a timezone")
        if self.acquisition_ended_at < self.acquisition_started_at:
            raise ValueError("audit end must not precede its start")
        if not _HEX_40.fullmatch(self.code_git_sha):
            raise ValueError("code Git SHA must be 40 lowercase hexadecimal characters")
        if not _HEX_64.fullmatch(self.dependency_lock_sha256):
            raise ValueError("dependency lock SHA-256 must be 64 lowercase hexadecimal characters")
        if self.credential_reference != "env:PITCH_API_TOKEN":
            raise ValueError("credential reference must be env:PITCH_API_TOKEN, never a secret")


@dataclass(frozen=True, slots=True)
class PitchApiQualificationEvidence:
    automated_private_research_permitted: bool
    immutable_raw_retention_permitted: bool
    attribution_requirements_recorded: bool
    correction_history_available: bool
    immutable_revision_identity_available: bool
    stable_identifier_policy_available: bool
    xg_series_by_scope: Mapping[str, str | None]

    @property
    def evaluation_requirements_proved(self) -> bool:
        return all(
            (
                self.automated_private_research_permitted,
                self.immutable_raw_retention_permitted,
                self.attribution_requirements_recorded,
                self.correction_history_available,
                self.immutable_revision_identity_available,
                self.stable_identifier_policy_available,
            )
        )


@dataclass(frozen=True, slots=True)
class PitchApiAuditInput:
    seasons: tuple[PitchApiSeasonAuditInput, ...]
    request_log: tuple[PitchApiRequestRecord, ...]
    budget: PitchApiRequestBudget
    metadata: PitchApiAuditMetadata
    qualification_evidence: PitchApiQualificationEvidence

    def __post_init__(self) -> None:
        keys = tuple(season.scope.key for season in self.seasons)
        if not keys or len(keys) != len(set(keys)):
            raise ValueError("audit season scopes must be present and unique")


@dataclass(frozen=True, slots=True)
class PitchApiValidationFinding:
    code: str
    domain: FindingDomain
    severity: FindingSeverity
    scope: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "domain": self.domain,
            "severity": self.severity,
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class PitchApiSeasonValidationReport:
    scope_key: str
    expected_matches: int
    observed_matches: int
    successful_shot_resources: int
    empty_shot_resources: int
    missing_shot_resources: int
    malformed_shot_resources: int
    shots: int
    penalties: int
    regulation_shots: int
    invalid_xg: int
    duplicate_shot_ids: int
    unknown_periods: int
    unknown_situations: int
    missing_fields: int
    request_failures: int

    def to_dict(self) -> dict[str, object]:
        return {
            "scope_key": self.scope_key,
            "expected_matches": self.expected_matches,
            "observed_matches": self.observed_matches,
            "successful_shot_resources": self.successful_shot_resources,
            "empty_shot_resources": self.empty_shot_resources,
            "missing_shot_resources": self.missing_shot_resources,
            "malformed_shot_resources": self.malformed_shot_resources,
            "shots": self.shots,
            "penalties": self.penalties,
            "regulation_shots": self.regulation_shots,
            "invalid_xg": self.invalid_xg,
            "duplicate_shot_ids": self.duplicate_shot_ids,
            "unknown_periods": self.unknown_periods,
            "unknown_situations": self.unknown_situations,
            "missing_fields": self.missing_fields,
            "request_failures": self.request_failures,
        }


@dataclass(frozen=True, slots=True)
class PitchApiAuditReport:
    technical_status: AuditStatus
    evaluation_v2_status: AuditStatus
    cross_season_xg_series_status: SeriesStatus
    stopped: bool
    request_count: int
    request_ceiling: int
    retry_reserve: int
    seasons: tuple[PitchApiSeasonValidationReport, ...]
    findings: tuple[PitchApiValidationFinding, ...]
    metadata: PitchApiAuditMetadata

    @property
    def total_matches(self) -> int:
        return sum(season.observed_matches for season in self.seasons)

    @property
    def total_shots(self) -> int:
        return sum(season.shots for season in self.seasons)

    @property
    def total_penalties(self) -> int:
        return sum(season.penalties for season in self.seasons)

    @property
    def total_regulation_shots(self) -> int:
        return sum(season.regulation_shots for season in self.seasons)

    @property
    def total_empty_shot_resources(self) -> int:
        return sum(season.empty_shot_resources for season in self.seasons)

    @property
    def invalid_xg_count(self) -> int:
        return sum(season.invalid_xg for season in self.seasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "PitchApiSyntheticValidationReportV1",
            "technical_status": self.technical_status,
            "evaluation_v2_status": self.evaluation_v2_status,
            "cross_season_xg_series_status": self.cross_season_xg_series_status,
            "stopped": self.stopped,
            "request_count": self.request_count,
            "request_ceiling": self.request_ceiling,
            "retry_reserve": self.retry_reserve,
            "totals": {
                "matches": self.total_matches,
                "shots": self.total_shots,
                "penalties": self.total_penalties,
                "regulation_shots": self.total_regulation_shots,
                "empty_shot_resources": self.total_empty_shot_resources,
                "invalid_xg": self.invalid_xg_count,
            },
            "seasons": [season.to_dict() for season in self.seasons],
            "findings": [finding.to_dict() for finding in self.findings],
            "metadata": {
                "endpoint_version": self.metadata.endpoint_version,
                "provider_version_observed": self.metadata.observed_provider_version is not None,
                "acquisition_started_at": self.metadata.acquisition_started_at.isoformat(),
                "acquisition_ended_at": self.metadata.acquisition_ended_at.isoformat(),
                "code_git_sha": self.metadata.code_git_sha,
                "dependency_lock_sha256": self.metadata.dependency_lock_sha256,
                "credential_reference": self.metadata.credential_reference,
            },
        }


@dataclass(frozen=True, slots=True)
class _Match:
    match_id: str
    team_ids: frozenset[str]


@dataclass(slots=True)
class _SeasonCounts:
    successful_shot_resources: int = 0
    empty_shot_resources: int = 0
    missing_shot_resources: int = 0
    malformed_shot_resources: int = 0
    shots: int = 0
    penalties: int = 0
    regulation_shots: int = 0
    invalid_xg: int = 0
    duplicate_shot_ids: int = 0
    unknown_periods: int = 0
    unknown_situations: int = 0
    missing_fields: int = 0


def validate_pitchapi_audit(audit: PitchApiAuditInput) -> PitchApiAuditReport:
    """Validate supplied PitchAPI payloads without network or persistence access."""

    findings: list[PitchApiValidationFinding] = []
    season_reports: list[PitchApiSeasonValidationReport] = []
    path_scopes: dict[str, str] = {}
    for season in audit.seasons:
        report, season_findings, season_paths = _validate_season(season)
        season_reports.append(report)
        findings.extend(season_findings)
        path_scopes.update(season_paths)

    expected_base_requests = len(audit.seasons) + sum(
        season.scope.expected_match_count for season in audit.seasons
    )
    request_findings, stopped, request_failures = _validate_requests(
        audit.request_log,
        audit.budget,
        path_scopes,
        expected_base_requests,
    )
    findings.extend(request_findings)
    season_reports = [
        replace(report, request_failures=request_failures.get(report.scope_key, 0))
        for report in season_reports
    ]

    series_status, series_findings = _xg_series_status(audit)
    findings.extend(series_findings)
    technical_status = _technical_status(findings, series_status)
    evaluation_status, evaluation_findings = _evaluation_status(
        technical_status,
        series_status,
        audit.qualification_evidence,
    )
    findings.extend(evaluation_findings)

    return PitchApiAuditReport(
        technical_status=technical_status,
        evaluation_v2_status=evaluation_status,
        cross_season_xg_series_status=series_status,
        stopped=stopped,
        request_count=len(audit.request_log),
        request_ceiling=audit.budget.ceiling,
        retry_reserve=audit.budget.retry_reserve,
        seasons=tuple(season_reports),
        findings=tuple(sorted(findings, key=lambda item: (item.domain, item.code, item.scope))),
        metadata=audit.metadata,
    )


def _validate_season(
    audit: PitchApiSeasonAuditInput,
) -> tuple[
    PitchApiSeasonValidationReport,
    list[PitchApiValidationFinding],
    dict[str, str],
]:
    findings: list[PitchApiValidationFinding] = []
    matches = _parse_fixture_payload(audit.scope, audit.fixture_payload, findings)
    counts = _SeasonCounts()
    expected_ids = {match.match_id for match in matches}
    for index, match in enumerate(matches):
        payload = audit.shot_payloads.get(match.match_id)
        _validate_shot_resource(audit.scope.key, index, match, payload, counts, findings)
    for extra_index, match_id in enumerate(sorted(set(audit.shot_payloads) - expected_ids)):
        del match_id
        findings.append(_error("UNEXPECTED_SHOT_RESOURCE", audit.scope.key, extra_index))
    paths = {audit.scope.manifest_path: audit.scope.key}
    paths.update({f"/v1/matches/{match.match_id}/shots": audit.scope.key for match in matches})
    return (
        _season_report(audit.scope, len(matches), counts),
        findings,
        paths,
    )


def _parse_fixture_payload(
    scope: PitchApiSeasonScope,
    payload: Mapping[str, Any],
    findings: list[PitchApiValidationFinding],
) -> tuple[_Match, ...]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        findings.append(_error("MALFORMED_FIXTURE_PAYLOAD", scope.key))
        return ()
    league = data.get("league")
    matches = data.get("matches")
    if not isinstance(league, Mapping) or not _is_sequence(matches):
        findings.append(_error("MALFORMED_FIXTURE_PAYLOAD", scope.key))
        return ()
    if league.get("id") != scope.league_id or league.get("season") != scope.season:
        findings.append(_error("FIXTURE_SCOPE_MISMATCH", scope.key))

    parsed: list[_Match] = []
    for index, value in enumerate(cast(Sequence[object], matches)):
        match = _parse_match(value, scope.key, index, findings)
        if match is not None:
            parsed.append(match)
    identifiers = [match.match_id for match in parsed]
    if len(identifiers) != len(set(identifiers)):
        findings.append(_error("DUPLICATE_MATCH_ID", scope.key))
    if len(parsed) != scope.expected_match_count:
        findings.append(_error("MATCH_COUNT_MISMATCH", scope.key))
    return tuple(parsed)


def _parse_match(
    value: object,
    scope_key: str,
    index: int,
    findings: list[PitchApiValidationFinding],
) -> _Match | None:
    item_scope = f"{scope_key}:fixture[{index}]"
    if not isinstance(value, Mapping):
        findings.append(_error("MALFORMED_FIXTURE", item_scope))
        return None
    match_id = value.get("id")
    home_id = _nested_id(value.get("home_team"), "team")
    away_id = _nested_id(value.get("away_team"), "team")
    if not _valid_id(match_id, "match") or home_id is None or away_id is None:
        findings.append(_error("MALFORMED_FIXTURE", item_scope))
        return None
    if home_id == away_id:
        findings.append(_error("DUPLICATE_FIXTURE_TEAM_ID", item_scope))
    if value.get("status") != "finished":
        findings.append(_error("NON_FINISHED_FIXTURE", item_scope))
    if value.get("has_playoff") is True:
        findings.append(_error("PLAYOFF_FIXTURE_INCLUDED", item_scope))
    if not _parse_timestamp(value.get("time_utc")):
        findings.append(_error("INVALID_KICKOFF", item_scope))
    return _Match(str(match_id), frozenset((home_id, away_id)))


def _validate_shot_resource(
    scope_key: str,
    match_index: int,
    match: _Match,
    payload: Mapping[str, Any] | None,
    counts: _SeasonCounts,
    findings: list[PitchApiValidationFinding],
) -> None:
    match_scope = f"{scope_key}:match[{match_index}]"
    if payload is None:
        counts.missing_shot_resources += 1
        findings.append(_error("MISSING_SHOT_RESOURCE", match_scope))
        return
    data = payload.get("data")
    if not isinstance(data, Mapping) or not _is_sequence(data.get("periods")):
        counts.malformed_shot_resources += 1
        findings.append(_error("MALFORMED_SHOT_PAYLOAD", match_scope))
        return
    counts.successful_shot_resources += 1
    if data.get("match_id") != match.match_id:
        findings.append(_error("SHOT_RESPONSE_MATCH_MISMATCH", match_scope))
    periods = cast(Sequence[object], data["periods"])
    structurally_valid = _validate_periods(match_scope, match, periods, counts, findings)
    if not structurally_valid:
        counts.malformed_shot_resources += 1


def _validate_periods(
    match_scope: str,
    match: _Match,
    periods: Sequence[object],
    counts: _SeasonCounts,
    findings: list[PitchApiValidationFinding],
) -> bool:
    seen_periods: set[str] = set()
    initial_shot_count = counts.shots
    seen_shot_ids: set[str] = set()
    structurally_valid = True
    for period_index, period in enumerate(periods):
        period_scope = f"{match_scope}:period[{period_index}]"
        if not isinstance(period, Mapping) or not _is_sequence(period.get("shots")):
            findings.append(_error("MALFORMED_PERIOD", period_scope))
            structurally_valid = False
            continue
        period_name = period.get("period")
        regulation_period = _validate_period_name(
            period_name, period_scope, seen_periods, counts, findings
        )
        for shot_index, shot in enumerate(period["shots"]):
            _validate_shot(
                f"{period_scope}:shot[{shot_index}]",
                shot,
                match,
                regulation_period,
                seen_shot_ids,
                counts,
                findings,
            )
    if counts.shots == initial_shot_count and structurally_valid:
        counts.empty_shot_resources += 1
    return structurally_valid


def _validate_period_name(
    value: object,
    scope: str,
    seen_periods: set[str],
    counts: _SeasonCounts,
    findings: list[PitchApiValidationFinding],
) -> bool:
    if not isinstance(value, str) or not value:
        counts.missing_fields += 1
        counts.unknown_periods += 1
        findings.append(_error("MISSING_PERIOD", scope))
        return False
    if value in seen_periods:
        findings.append(_error("DUPLICATE_PERIOD", scope))
    seen_periods.add(value)
    if value not in _REGULATION_PERIODS:
        counts.unknown_periods += 1
        findings.append(_error("UNKNOWN_PERIOD", scope))
        return False
    return True


def _validate_shot(
    scope: str,
    value: object,
    match: _Match,
    regulation_period: bool,
    seen_shot_ids: set[str],
    counts: _SeasonCounts,
    findings: list[PitchApiValidationFinding],
) -> None:
    counts.shots += 1
    if not isinstance(value, Mapping):
        findings.append(_error("MALFORMED_SHOT", scope))
        return
    counts.missing_fields += sum(
        field not in value for field in ("id", "team_id", "expected_goals", "situation")
    )
    shot_id = value.get("id")
    if not _valid_id(shot_id, "shot"):
        findings.append(_error("MISSING_OR_INVALID_SHOT_ID", scope))
    elif str(shot_id) in seen_shot_ids:
        counts.duplicate_shot_ids += 1
        findings.append(_error("DUPLICATE_SHOT_ID", scope))
    else:
        seen_shot_ids.add(str(shot_id))
    team_id = value.get("team_id")
    if not _valid_id(team_id, "team") or team_id not in match.team_ids:
        findings.append(_error("SHOT_TEAM_NOT_IN_FIXTURE", scope))
    if not _valid_xg(value.get("expected_goals")):
        counts.invalid_xg += 1
        findings.append(_error("INVALID_EXPECTED_GOALS", scope))
    situation = value.get("situation")
    if not isinstance(situation, str) or not situation:
        counts.unknown_situations += 1
        findings.append(_error("MISSING_SITUATION", scope))
    elif situation not in _SHOT_SITUATIONS:
        counts.unknown_situations += 1
        findings.append(_error("UNKNOWN_SITUATION", scope))
    elif situation == "Penalty":
        counts.penalties += 1
    if regulation_period:
        counts.regulation_shots += 1


def _validate_requests(
    records: tuple[PitchApiRequestRecord, ...],
    budget: PitchApiRequestBudget,
    path_scopes: Mapping[str, str],
    expected_base_requests: int,
) -> tuple[list[PitchApiValidationFinding], bool, dict[str, int]]:
    allowed_paths = set(path_scopes)
    budget_findings, budget_stop = _validate_request_budget(records, budget, expected_base_requests)
    path_findings, path_stop = _validate_request_paths(records, budget, allowed_paths)
    status_findings, status_stop, failure_counts = _validate_request_statuses(
        records, budget, path_scopes
    )
    return (
        budget_findings + path_findings + status_findings,
        any((budget_stop, path_stop, status_stop)),
        failure_counts,
    )


def _validate_request_budget(
    records: tuple[PitchApiRequestRecord, ...],
    budget: PitchApiRequestBudget,
    expected_base_requests: int,
) -> tuple[list[PitchApiValidationFinding], bool]:
    findings: list[PitchApiValidationFinding] = []
    if budget.ceiling - budget.retry_reserve != expected_base_requests:
        findings.append(_error("REQUEST_BUDGET_BASE_MISMATCH", "request_log"))
    if len(records) > budget.ceiling:
        findings.append(_error("REQUEST_BUDGET_EXCEEDED", "request_log"))
    return findings, bool(findings)


def _validate_request_paths(
    records: tuple[PitchApiRequestRecord, ...],
    budget: PitchApiRequestBudget,
    allowed_paths: set[str],
) -> tuple[list[PitchApiValidationFinding], bool]:
    findings: list[PitchApiValidationFinding] = []
    path_counts = Counter(record.path for record in records)
    for path_index, path in enumerate(sorted(path_counts)):
        if path not in allowed_paths:
            findings.append(_error("UNBUDGETED_REQUEST_PATH", f"request_path[{path_index}]"))
        if path_counts[path] > budget.max_attempts_per_path:
            findings.append(_error("REQUEST_PATH_ATTEMPTS_EXCEEDED", f"request_path[{path_index}]"))
    for missing_index, path in enumerate(sorted(allowed_paths - set(path_counts))):
        del path
        findings.append(_error("MISSING_REQUEST_EVIDENCE", f"request_path[{missing_index}]"))
    return findings, any(
        finding.code in {"UNBUDGETED_REQUEST_PATH", "REQUEST_PATH_ATTEMPTS_EXCEEDED"}
        for finding in findings
    )


def _validate_request_statuses(
    records: tuple[PitchApiRequestRecord, ...],
    budget: PitchApiRequestBudget,
    path_scopes: Mapping[str, str],
) -> tuple[list[PitchApiValidationFinding], bool, dict[str, int]]:
    allowed_paths = set(path_scopes)
    findings: list[PitchApiValidationFinding] = []
    failure_counts: Counter[str] = Counter()
    stopped = False
    rate_limits = 0
    successful_paths: set[str] = set()
    for index, record in enumerate(records):
        request_scope = f"request[{index}]"
        if record.status_code != 200 and record.path in path_scopes:
            failure_counts[path_scopes[record.path]] += 1
        if record.status_code == 200:
            successful_paths.add(record.path)
        elif record.status_code in (401, 403):
            findings.append(_error("AUTHORIZATION_FAILED", request_scope))
            stopped = True
        elif record.status_code == 429:
            rate_limits += 1
            if record.retry_after_seconds is None:
                findings.append(_error("RATE_LIMIT_WITHOUT_RETRY_AFTER", request_scope))
                stopped = True
        else:
            findings.append(_error("REQUEST_FAILED", request_scope))
    if rate_limits > budget.max_rate_limit_responses:
        findings.append(_error("REPEATED_RATE_LIMIT", "request_log"))
        stopped = True
    elif rate_limits == 1:
        findings.append(_warning("RATE_LIMIT_RETRY_OBSERVED", "request_log"))
    for missing_index, path in enumerate(sorted(allowed_paths - successful_paths)):
        del path
        findings.append(_error("MISSING_SUCCESSFUL_REQUEST", f"request_path[{missing_index}]"))
    return findings, stopped, dict(failure_counts)


def _xg_series_status(
    audit: PitchApiAuditInput,
) -> tuple[SeriesStatus, list[PitchApiValidationFinding]]:
    expected_keys = {season.scope.key for season in audit.seasons}
    evidence = audit.qualification_evidence.xg_series_by_scope
    values = [evidence.get(key) for key in sorted(expected_keys)]
    if set(evidence) != expected_keys or any(not value for value in values):
        return "UNPROVED", [_warning("CROSS_SEASON_XG_SERIES_UNPROVED", "audit")]
    if len(set(values)) != 1:
        return "FAIL", [_error("MIXED_XG_SERIES", "audit")]
    return "PASS", []


def _technical_status(
    findings: list[PitchApiValidationFinding], series_status: SeriesStatus
) -> AuditStatus:
    technical = [finding for finding in findings if finding.domain == "technical"]
    if series_status == "FAIL" or any(finding.severity == "ERROR" for finding in technical):
        return "FAIL"
    if series_status == "UNPROVED" or technical:
        return "PARTIAL"
    return "PASS"


def _evaluation_status(
    technical_status: AuditStatus,
    series_status: SeriesStatus,
    evidence: PitchApiQualificationEvidence,
) -> tuple[AuditStatus, list[PitchApiValidationFinding]]:
    if (
        technical_status == "PASS"
        and series_status == "PASS"
        and evidence.evaluation_requirements_proved
    ):
        return "PASS", []
    if not evidence.evaluation_requirements_proved:
        return "FAIL", [
            PitchApiValidationFinding(
                code="EVALUATION_PERMISSION_OR_LINEAGE_UNPROVED",
                domain="evaluation_v2",
                severity="ERROR",
                scope="audit",
            )
        ]
    return "FAIL", []


def _season_report(
    scope: PitchApiSeasonScope,
    observed_matches: int,
    counts: _SeasonCounts,
) -> PitchApiSeasonValidationReport:
    return PitchApiSeasonValidationReport(
        scope_key=scope.key,
        expected_matches=scope.expected_match_count,
        observed_matches=observed_matches,
        successful_shot_resources=counts.successful_shot_resources,
        empty_shot_resources=counts.empty_shot_resources,
        missing_shot_resources=counts.missing_shot_resources,
        malformed_shot_resources=counts.malformed_shot_resources,
        shots=counts.shots,
        penalties=counts.penalties,
        regulation_shots=counts.regulation_shots,
        invalid_xg=counts.invalid_xg,
        duplicate_shot_ids=counts.duplicate_shot_ids,
        unknown_periods=counts.unknown_periods,
        unknown_situations=counts.unknown_situations,
        missing_fields=counts.missing_fields,
        request_failures=0,
    )


def _error(code: str, scope: str, index: int | None = None) -> PitchApiValidationFinding:
    suffix = f"[{index}]" if index is not None else ""
    return PitchApiValidationFinding(code, "technical", "ERROR", f"{scope}{suffix}")


def _warning(code: str, scope: str) -> PitchApiValidationFinding:
    return PitchApiValidationFinding(code, "technical", "WARNING", scope)


def _valid_id(value: object, kind: str) -> bool:
    return isinstance(value, str) and _ID_PATTERNS[kind].fullmatch(value) is not None


def _nested_id(value: object, kind: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    identifier = value.get("id")
    return str(identifier) if _valid_id(identifier, kind) else None


def _valid_xg(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    )


def _parse_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return _timezone_aware(parsed)


def _timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _is_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
