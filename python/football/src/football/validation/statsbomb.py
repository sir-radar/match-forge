from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

Severity = Literal["FATAL", "QUARANTINE", "WARNING", "INFO"]

_TIMESTAMP = re.compile(r"^([0-9]+):([0-5][0-9]):([0-5][0-9](?:\.[0-9]+)?)$")


@dataclass(frozen=True)
class QualityRule:
    severity: Severity
    action: str


@dataclass(frozen=True)
class QualityPolicy:
    version: str
    sha256: str
    rules: Mapping[str, QualityRule]

    @classmethod
    def from_path(cls, path: Path) -> QualityPolicy:
        try:
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"quality policy is not valid UTF-8 JSON: {path}") from error
        if not isinstance(document, dict) or document.get("contract") != "QualityPolicyV1":
            raise ValueError("quality policy must use QualityPolicyV1")
        version = document.get("version")
        raw_rules = document.get("rules")
        if not isinstance(version, str) or not version:
            raise ValueError("quality policy version must be a non-empty string")
        if not isinstance(raw_rules, dict) or not raw_rules:
            raise ValueError("quality policy rules must be a non-empty object")
        rules = {str(code): _parse_rule(str(code), value) for code, value in raw_rules.items()}
        return cls(version=version, sha256=hashlib.sha256(payload).hexdigest(), rules=rules)

    def rule(self, code: str) -> QualityRule:
        try:
            return self.rules[code]
        except KeyError as error:
            raise ValueError(f"quality policy is missing required rule {code}") from error


@dataclass(frozen=True)
class MatchValidationContext:
    canonical_match_id: UUID
    provider_match_id: str
    home_team_id: UUID
    away_team_id: UUID
    home_score: int | None
    away_score: int | None
    lineup_players: Mapping[UUID, frozenset[UUID]]
    position_stints: tuple[PositionStintValidationContext, ...] = ()


@dataclass(frozen=True)
class PositionStintValidationContext:
    canonical_player_id: UUID
    sequence: int
    period_from: int
    clock_from: timedelta
    period_to: int | None
    clock_to: timedelta | None


@dataclass(frozen=True)
class EventFileValidationInput:
    dataset_file_id: UUID
    source_resource_id: UUID | None
    relative_path: str
    match: MatchValidationContext
    rows: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class ValidationFinding:
    rule_code: str
    severity: Severity
    action: str
    scope_type: str
    message: str
    evidence: dict[str, Any]
    dataset_file_id: UUID | None = None
    source_resource_id: UUID | None = None
    provider_entity_id: str | None = None
    field_path: str | None = None


def validate_statsbomb_dataset(
    files: Sequence[EventFileValidationInput],
    policy: QualityPolicy,
) -> tuple[ValidationFinding, ...]:
    findings = _duplicate_match_findings(files, policy)
    findings.extend(_duplicate_event_findings(files, policy))
    for file in files:
        findings.extend(_validate_file(file, policy))
    return tuple(sorted(findings, key=_finding_sort_key))


def make_finding(
    policy: QualityPolicy,
    rule_code: str,
    scope_type: str,
    message: str,
    evidence: dict[str, Any],
    *,
    dataset_file_id: UUID | None = None,
    source_resource_id: UUID | None = None,
    provider_entity_id: str | None = None,
    field_path: str | None = None,
) -> ValidationFinding:
    rule = policy.rule(rule_code)
    return ValidationFinding(
        rule_code=rule_code,
        severity=rule.severity,
        action=rule.action,
        scope_type=scope_type,
        message=message,
        evidence=evidence,
        dataset_file_id=dataset_file_id,
        source_resource_id=source_resource_id,
        provider_entity_id=provider_entity_id,
        field_path=field_path,
    )


def _parse_rule(code: str, value: object) -> QualityRule:
    if not isinstance(value, dict) or set(value) != {"severity", "action"}:
        raise ValueError(f"quality rule {code} must define only severity and action")
    severity = value["severity"]
    action = value["action"]
    parsed_severity = _severity(severity, code)
    if not isinstance(action, str) or not action:
        raise ValueError(f"quality rule {code} action must be a non-empty string")
    return QualityRule(severity=parsed_severity, action=action)


def _severity(value: object, code: str) -> Severity:
    if value == "FATAL":
        return "FATAL"
    if value == "QUARANTINE":
        return "QUARANTINE"
    if value == "WARNING":
        return "WARNING"
    if value == "INFO":
        return "INFO"
    raise ValueError(f"quality rule {code} has invalid severity")


def _duplicate_match_findings(
    files: Sequence[EventFileValidationInput], policy: QualityPolicy
) -> list[ValidationFinding]:
    grouped: dict[UUID, list[EventFileValidationInput]] = defaultdict(list)
    for file in files:
        grouped[file.match.canonical_match_id].append(file)
    return [
        make_finding(
            policy,
            "SB_DUPLICATE_MATCH",
            "match",
            f"match {match_id} appears in multiple dataset files",
            {
                "canonical_match_id": str(match_id),
                "files": sorted(item.relative_path for item in group),
            },
            provider_entity_id=group[0].match.provider_match_id,
        )
        for match_id, group in grouped.items()
        if len(group) > 1
    ]


def _duplicate_event_findings(
    files: Sequence[EventFileValidationInput], policy: QualityPolicy
) -> list[ValidationFinding]:
    identities: dict[tuple[str, str], list[EventFileValidationInput]] = defaultdict(list)
    indexes: dict[tuple[str, int], list[EventFileValidationInput]] = defaultdict(list)
    for file in files:
        for row in file.rows:
            identities[("canonical", str(row.get("canonical_event_id")))].append(file)
            identities[("provider", str(row.get("provider_event_id")))].append(file)
            index = row.get("event_index")
            if isinstance(index, int) and not isinstance(index, bool):
                indexes[(str(row.get("provider_match_id")), index)].append(file)
    findings: list[ValidationFinding] = []
    for (identity_kind, event_id), occurrences in identities.items():
        if len(occurrences) > 1:
            findings.append(
                make_finding(
                    policy,
                    "SB_DUPLICATE_EVENT",
                    "event",
                    f"duplicate {identity_kind} event identifier {event_id}",
                    {
                        "identity_kind": identity_kind,
                        "event_id": event_id,
                        "count": len(occurrences),
                    },
                    dataset_file_id=occurrences[0].dataset_file_id,
                    source_resource_id=occurrences[0].source_resource_id,
                    provider_entity_id=event_id,
                )
            )
    for (match_id, event_index), occurrences in indexes.items():
        if len(occurrences) > 1:
            findings.append(
                make_finding(
                    policy,
                    "SB_DUPLICATE_EVENT_INDEX",
                    "event",
                    f"duplicate event index {event_index} for match {match_id}",
                    {
                        "provider_match_id": match_id,
                        "event_index": event_index,
                        "count": len(occurrences),
                    },
                    dataset_file_id=occurrences[0].dataset_file_id,
                    source_resource_id=occurrences[0].source_resource_id,
                    provider_entity_id=match_id,
                    field_path="index",
                )
            )
    return findings


def _validate_file(
    file: EventFileValidationInput, policy: QualityPolicy
) -> list[ValidationFinding]:
    findings = _lineup_shape_findings(file, policy)
    parsed_payloads: list[tuple[Mapping[str, Any], dict[str, object]]] = []
    for row in file.rows:
        payload = _provider_payload(row)
        if payload is None:
            findings.append(
                _row_finding(
                    file,
                    row,
                    policy,
                    "SB_MALFORMED_EVENTS_JSON",
                    "provider payload is not a valid StatsBomb event object",
                    "provider_payload_json",
                )
            )
        else:
            parsed_payloads.append((row, payload))
        findings.extend(_row_findings(file, row, policy))
    findings.extend(_sequence_timestamp_findings(file, policy))
    if len(parsed_payloads) == len(file.rows):
        findings.extend(_score_findings(file, parsed_payloads, policy))
    return findings


def _lineup_shape_findings(
    file: EventFileValidationInput, policy: QualityPolicy
) -> list[ValidationFinding]:
    match = file.match
    expected_teams = {match.home_team_id, match.away_team_id}
    actual_teams = set(match.lineup_players)
    findings: list[ValidationFinding] = []
    if actual_teams != expected_teams:
        findings.append(
            make_finding(
                policy,
                "SB_LINEUP_INCONSISTENCY",
                "lineup",
                f"lineup teams do not match participants for match {match.provider_match_id}",
                {
                    "expected_team_ids": sorted(map(str, expected_teams)),
                    "actual_team_ids": sorted(map(str, actual_teams)),
                },
                dataset_file_id=file.dataset_file_id,
                source_resource_id=file.source_resource_id,
                provider_entity_id=match.provider_match_id,
            )
        )
    shared = match.lineup_players.get(match.home_team_id, frozenset()) & match.lineup_players.get(
        match.away_team_id, frozenset()
    )
    if shared:
        findings.append(
            make_finding(
                policy,
                "SB_LINEUP_INCONSISTENCY",
                "lineup",
                f"players appear for both teams in match {match.provider_match_id}",
                {"canonical_player_ids": sorted(map(str, shared))},
                dataset_file_id=file.dataset_file_id,
                source_resource_id=file.source_resource_id,
                provider_entity_id=match.provider_match_id,
            )
        )
    for position in match.position_stints:
        if _position_is_monotonic(position):
            continue
        findings.append(
            make_finding(
                policy,
                "SB_NONMONOTONIC_POSITION_STINT",
                "lineup",
                "provider position stint ends before it starts",
                {
                    "canonical_player_id": str(position.canonical_player_id),
                    "sequence": position.sequence,
                    "period_from": position.period_from,
                    "clock_from_seconds": position.clock_from.total_seconds(),
                    "period_to": position.period_to,
                    "clock_to_seconds": (
                        position.clock_to.total_seconds() if position.clock_to else None
                    ),
                },
                dataset_file_id=file.dataset_file_id,
                provider_entity_id=str(position.canonical_player_id),
                field_path="positions",
            )
        )
    return findings


def _position_is_monotonic(position: PositionStintValidationContext) -> bool:
    if position.period_to is None or position.clock_to is None:
        return True
    return position.period_to > position.period_from or (
        position.period_to == position.period_from and position.clock_to > position.clock_from
    )


def _row_findings(
    file: EventFileValidationInput,
    row: Mapping[str, Any],
    policy: QualityPolicy,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if row.get("canonical_event_type_id") is None:
        findings.append(
            _row_finding(
                file,
                row,
                policy,
                "SB_UNKNOWN_EVENT_TYPE",
                "provider event type has no canonical mapping",
                "type",
            )
        )
    findings.extend(_player_findings(file, row, policy))
    timestamp_error = _timestamp_error(row)
    if timestamp_error is not None:
        findings.append(
            _row_finding(
                file, row, policy, "SB_IMPOSSIBLE_EVENT_TIMESTAMP", timestamp_error, "timestamp"
            )
        )
    coordinate_code, coordinate_message = _coordinate_issue(row)
    if coordinate_code is not None:
        findings.append(
            _row_finding(file, row, policy, coordinate_code, coordinate_message, "location")
        )
    return findings


def _player_findings(
    file: EventFileValidationInput,
    row: Mapping[str, Any],
    policy: QualityPolicy,
) -> list[ValidationFinding]:
    provider_player = row.get("provider_player_id")
    canonical_player = _uuid(row.get("canonical_player_id"))
    findings: list[ValidationFinding] = []
    if (provider_player is None) != (canonical_player is None):
        findings.append(
            _row_finding(
                file,
                row,
                policy,
                "SB_MISSING_PLAYER",
                "event player lacks a complete provider-to-canonical identity",
                "player",
            )
        )
    if canonical_player is None:
        return findings
    team_id = _uuid(row.get("canonical_team_id"))
    lineup = file.match.lineup_players.get(team_id, frozenset()) if team_id else frozenset()
    if team_id is None or canonical_player not in lineup:
        findings.append(
            _row_finding(
                file,
                row,
                policy,
                "SB_LINEUP_INCONSISTENCY",
                "event player does not belong to the event team's match lineup",
                "player",
            )
        )
    return findings


def _timestamp_error(row: Mapping[str, Any]) -> str | None:
    timestamp = row.get("timestamp")
    period = row.get("period")
    minute = row.get("minute")
    second = row.get("second")
    if not isinstance(timestamp, str) or (match := _TIMESTAMP.fullmatch(timestamp)) is None:
        return "event timestamp is outside the StatsBomb clock contract"
    if isinstance(period, bool) or not isinstance(period, int) or not 1 <= period <= 5:
        return "event period must be between 1 and 5"
    if isinstance(minute, bool) or not isinstance(minute, int) or minute < 0:
        return "event minute must be non-negative"
    if isinstance(second, bool) or not isinstance(second, int) or not 0 <= second <= 59:
        return "event second must be between 0 and 59"
    try:
        timestamp_second = int(Decimal(match.group(3)))
    except InvalidOperation:
        return "event timestamp seconds are invalid"
    if timestamp_second != second:
        return "event second conflicts with timestamp"
    return None


def _sequence_timestamp_findings(
    file: EventFileValidationInput,
    policy: QualityPolicy,
) -> list[ValidationFinding]:
    previous: dict[int, Decimal] = {}
    findings: list[ValidationFinding] = []
    ordered = sorted(file.rows, key=_event_index)
    for row in ordered:
        period = row.get("period")
        clock = _timestamp_seconds(row.get("timestamp"))
        if isinstance(period, bool) or not isinstance(period, int) or clock is None:
            continue
        if period in previous and clock < previous[period]:
            findings.append(
                _row_finding(
                    file,
                    row,
                    policy,
                    "SB_IMPOSSIBLE_EVENT_TIMESTAMP",
                    "event timestamp moves backwards within its period",
                    "timestamp",
                )
            )
        previous[period] = clock
    return findings


def _event_index(row: Mapping[str, Any]) -> int:
    value = row.get("event_index")
    return value if isinstance(value, int) and not isinstance(value, bool) else -1


def _timestamp_seconds(value: object) -> Decimal | None:
    if not isinstance(value, str) or (match := _TIMESTAMP.fullmatch(value)) is None:
        return None
    try:
        return (
            Decimal(match.group(1)) * 3600 + Decimal(match.group(2)) * 60 + Decimal(match.group(3))
        )
    except InvalidOperation:
        return None


def _coordinate_issue(row: Mapping[str, Any]) -> tuple[str | None, str]:
    quality = row.get("location_quality")
    source_x = _finite_number(row.get("source_x"))
    source_y = _finite_number(row.get("source_y"))
    x_norm = _finite_number(row.get("x_norm"))
    y_norm = _finite_number(row.get("y_norm"))
    if quality == "missing" and all(
        value is None for value in (source_x, source_y, x_norm, y_norm)
    ):
        return None, ""
    if quality == "valid" and source_x is not None and source_y is not None:
        valid = 0 <= source_x <= 120 and 0 <= source_y <= 80
        normalized = (
            x_norm is not None
            and y_norm is not None
            and math.isclose(x_norm, source_x / 120)
            and math.isclose(y_norm, source_y / 80)
        )
        if valid and normalized:
            return None, ""
    if quality == "out_of_bounds" and source_x is not None and source_y is not None:
        out_of_bounds = not 0 <= source_x <= 120 or not 0 <= source_y <= 80
        if out_of_bounds and x_norm is None and y_norm is None:
            return (
                "SB_EVENT_LOCATION_OUT_OF_BOUNDS",
                "event coordinates are outside StatsBomb 120x80 bounds",
            )
    return (
        "SB_INVALID_EVENT_COORDINATES",
        "event coordinates conflict with normalized location quality",
    )


def _score_findings(
    file: EventFileValidationInput,
    rows: Sequence[tuple[Mapping[str, Any], dict[str, object]]],
    policy: QualityPolicy,
) -> list[ValidationFinding]:
    match = file.match
    if match.home_score is None or match.away_score is None:
        return []
    goals = {match.home_team_id: 0, match.away_team_id: 0}
    unassigned = 0
    for row, payload in rows:
        scoring_team = _scoring_team(row, payload, match)
        if scoring_team is None:
            continue
        if scoring_team in goals:
            goals[scoring_team] += 1
        else:
            unassigned += 1
    observed = (goals[match.home_team_id], goals[match.away_team_id])
    expected = (match.home_score, match.away_score)
    if observed == expected and unassigned == 0:
        return []
    return [
        make_finding(
            policy,
            "SB_SCORE_INCONSISTENCY",
            "match",
            f"event goals do not reconcile with score for match {match.provider_match_id}",
            {
                "expected_home_score": expected[0],
                "expected_away_score": expected[1],
                "event_home_goals": observed[0],
                "event_away_goals": observed[1],
                "unassigned_goals": unassigned,
            },
            dataset_file_id=file.dataset_file_id,
            source_resource_id=file.source_resource_id,
            provider_entity_id=match.provider_match_id,
        )
    ]


def _scoring_team(
    row: Mapping[str, Any],
    payload: Mapping[str, object],
    match: MatchValidationContext,
) -> UUID | None:
    if row.get("period") == 5:
        return None
    event_type = row.get("provider_event_type_name")
    team_id = _uuid(row.get("canonical_team_id"))
    if event_type == "Shot" and _nested_name(payload, "shot", "outcome") == "Goal":
        return team_id
    if event_type == "Own Goal For":
        return team_id
    # StatsBomb emits paired Own Goal For/Against events for one goal. The
    # beneficiary-side Own Goal For event is the single scoring observation.
    return None


def _provider_payload(row: Mapping[str, Any]) -> dict[str, object] | None:
    value = row.get("provider_payload_json")
    if not isinstance(value, str):
        return None
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        return None
    event_type = payload.get("type")
    required = ("id", "index", "period", "timestamp", "minute", "second")
    if any(field not in payload for field in required) or not isinstance(event_type, dict):
        return None
    if payload.get("id") != row.get("provider_event_id") or payload.get("index") != row.get(
        "event_index"
    ):
        return None
    return payload


def _nested_name(payload: Mapping[str, object], *path: str) -> str | None:
    value: object = payload
    for component in path:
        if not isinstance(value, dict):
            return None
        value = value.get(component)
    return (
        value.get("name")
        if isinstance(value, dict) and isinstance(value.get("name"), str)
        else None
    )


def _row_finding(
    file: EventFileValidationInput,
    row: Mapping[str, Any],
    policy: QualityPolicy,
    rule_code: str,
    message: str,
    field_path: str,
) -> ValidationFinding:
    event_id = str(row.get("provider_event_id"))
    return make_finding(
        policy,
        rule_code,
        "event",
        message,
        {"provider_event_id": event_id, "event_index": row.get("event_index")},
        dataset_file_id=file.dataset_file_id,
        source_resource_id=file.source_resource_id,
        provider_entity_id=event_id,
        field_path=field_path,
    )


def _uuid(value: object) -> UUID | None:
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _finding_sort_key(finding: ValidationFinding) -> tuple[str, str, str, str, str]:
    return (
        finding.rule_code,
        finding.provider_entity_id or "",
        str(finding.dataset_file_id or ""),
        finding.field_path or "",
        json.dumps(finding.evidence, sort_keys=True, separators=(",", ":")),
    )
