"""Validate the repository's current execution-state record."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TextIO, cast

_CONTRACT = "ProjectStatusV2"
_PHASE_STATUSES = frozenset(("PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"))
_PHASE_3_STATUSES = frozenset(("BLOCKED", "PASS", "FAIL", "NOT_RUN"))
_CLOSED_ROUTE_OUTCOMES = frozenset(("TERMINAL_ROUTE_FAIL", "CLOSED"))
_DECISION_RECORD_GLOB = "owner-decision-*.json"
_SPRINT_STATUS_PATTERN = re.compile(
    r"^Status:\s+\*{0,2}(PASS|PASS_WITH_WARNINGS|FAIL|NOT_RUN)\*{0,2}\s*$",
    re.MULTILINE,
)


class ProjectStatusError(ValueError):
    """A ProjectStatusV2 record does not match its evidence or progression rules."""


def validate_project_status(status_path: Path, repository_root: Path | None = None) -> None:
    """Fail when ProjectStatusV2 is malformed or disagrees with repository evidence."""
    root = (repository_root or status_path.resolve().parents[1]).resolve()
    status = _load_json(status_path, "project status")
    _require_contract(status)
    _require_utc_timestamp(status)

    phase_1b = _require_section(status, "phase_1b")
    phase_2b = _require_section(status, "phase_2b")
    sprint_2 = _require_section(status, "sprint_2")
    phase_3 = _require_section(status, "phase_3")

    owner_decisions = _validate_owner_decisions(status, root)
    _validate_phase(status_name="phase_1b", section=phase_1b, root=root)
    _validate_phase(status_name="phase_2b", section=phase_2b, root=root)
    _validate_sprint_2(sprint_2, root)
    _validate_phase_3(phase_3, sprint_2, owner_decisions, root)
    _validate_closed_routes(status, root)
    _validate_evaluation_tracks(status, root)


def main(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None) -> int:
    """Run ProjectStatusV2 validation for the supplied repository status file."""
    parser = argparse.ArgumentParser(description="validate ProjectStatusV2")
    parser.add_argument("status_path", type=Path)
    arguments = parser.parse_args(argv)
    errors = sys.stderr if stderr is None else stderr
    try:
        validate_project_status(arguments.status_path)
    except ProjectStatusError as error:
        print(f"ProjectStatusV2 invalid: {error}", file=errors)
        return 1
    print("ProjectStatusV2 valid")
    return 0


def _load_json(path: Path, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ProjectStatusError(f"{description} file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise ProjectStatusError(f"malformed JSON {description}: {path}") from error
    if not isinstance(payload, dict):
        raise ProjectStatusError(f"{description} must be a JSON object: {path}")
    return cast(dict[str, object], payload)


def _require_contract(status: Mapping[str, object]) -> None:
    if status.get("contract") != _CONTRACT:
        raise ProjectStatusError(f"unsupported contract: {status.get('contract')!r}")


def _require_utc_timestamp(status: Mapping[str, object]) -> None:
    try:
        _utc_timestamp(status.get("updated_at"))
    except ValueError as error:
        raise ProjectStatusError(
            "updated_at must be a UTC ISO-8601 timestamp ending in Z"
        ) from error


def _utc_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(value)
    datetime.fromisoformat(value)
    return value


def _require_section(status: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = status.get(name)
    if not isinstance(value, dict):
        raise ProjectStatusError(f"{name} must be an object")
    return cast(Mapping[str, object], value)


def _validate_phase(*, status_name: str, section: Mapping[str, object], root: Path) -> None:
    expected_status = _require_status(section, status_name, _PHASE_STATUSES)
    evidence_path = _evidence_path(section, status_name, root)
    evidence = _load_json(evidence_path, "evidence")
    evidence_status = evidence.get(f"{status_name}_status")
    if evidence_status not in _PHASE_STATUSES:
        raise ProjectStatusError(
            f"{evidence_path.relative_to(root)} has no valid {status_name}_status"
        )
    if expected_status != evidence_status:
        raise ProjectStatusError(
            f"{status_name}.status={expected_status} disagrees with "
            f"{evidence_path.relative_to(root)} {status_name}_status={evidence_status}"
        )


def _validate_sprint_2(section: Mapping[str, object], root: Path) -> None:
    status = _require_status(section, "sprint_2", _PHASE_STATUSES)
    evidence_path = _evidence_path(section, "sprint_2", root)
    evidence_status = _markdown_status(evidence_path)
    if status != evidence_status:
        raise ProjectStatusError(
            f"sprint_2.status={status} disagrees with "
            f"{evidence_path.relative_to(root)} status={evidence_status}"
        )
    if status != "FAIL":
        return
    if section.get("owner_decision") != "RETAIN_FAIL_AND_STOP":
        raise ProjectStatusError(
            "sprint_2.status=FAIL requires owner_decision=RETAIN_FAIL_AND_STOP"
        )
    if section.get("challenger_authorized") is not False:
        raise ProjectStatusError("sprint_2.status=FAIL requires challenger_authorized=false")
    if section.get("model_promoted") is not False:
        raise ProjectStatusError("sprint_2.status=FAIL requires model_promoted=false")
    if "RETAIN_FAIL_AND_STOP" not in evidence_path.read_text(encoding="utf-8"):
        raise ProjectStatusError(
            f"{evidence_path.relative_to(root)} does not record RETAIN_FAIL_AND_STOP"
        )


def _validate_owner_decisions(status: Mapping[str, object], root: Path) -> list[str]:
    decisions = status.get("owner_decisions")
    if not isinstance(decisions, list) or not all(
        isinstance(value, str) and value for value in decisions
    ):
        raise ProjectStatusError("owner_decisions must be a list of decision-id strings")
    if len(set(decisions)) != len(decisions):
        raise ProjectStatusError("owner_decisions contains duplicate decision ids")
    recorded: set[str] = set()
    for path in sorted((root / "docs" / "evidence").glob(_DECISION_RECORD_GLOB)):
        record = _load_json(path, "owner decision")
        decision_id = record.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id:
            raise ProjectStatusError(f"{path.relative_to(root)} has no decision_id")
        try:
            _utc_timestamp(record.get("recorded_at"))
        except ValueError as error:
            raise ProjectStatusError(
                f"{path.relative_to(root)} recorded_at must be a UTC ISO-8601 timestamp ending in Z"
            ) from error
        recorded.add(decision_id)
    unreconciled = recorded.difference(decisions)
    if unreconciled:
        raise ProjectStatusError(
            "owner decision records not reconciled in owner_decisions: "
            + ", ".join(sorted(unreconciled))
        )
    unknown = set(decisions).difference(recorded)
    if unknown:
        raise ProjectStatusError(
            "owner_decisions entries have no decision record: " + ", ".join(sorted(unknown))
        )
    return decisions


def _validate_closed_routes(status: Mapping[str, object], root: Path) -> None:
    routes = status.get("closed_routes")
    if routes is None:
        return
    if not isinstance(routes, list):
        raise ProjectStatusError("closed_routes must be a list")
    seen: set[str] = set()
    for entry in routes:
        if not isinstance(entry, Mapping):
            raise ProjectStatusError("closed_routes entries must be objects")
        route = entry.get("route")
        if not isinstance(route, str) or not route:
            raise ProjectStatusError("closed_routes entries require a non-empty route")
        if route in seen:
            raise ProjectStatusError(f"closed_routes contains duplicate route: {route}")
        seen.add(route)
        if entry.get("outcome") not in _CLOSED_ROUTE_OUTCOMES:
            raise ProjectStatusError(
                f"closed_routes outcome for {route} has unsupported value: {entry.get('outcome')!r}"
            )
        evidence_path = _evidence_path(entry, f"closed_routes[{route}]", root)
        if route not in evidence_path.read_text(encoding="utf-8"):
            raise ProjectStatusError(
                f"{evidence_path.relative_to(root)} does not mention route {route}"
            )


def _validate_evaluation_tracks(status: Mapping[str, object], root: Path) -> None:
    tracks = status.get("evaluation_tracks")
    if not isinstance(tracks, list):
        raise ProjectStatusError("evaluation_tracks must be a list")
    expected = {
        ("EVALUATION_V2", "STATSBOMB"),
        ("PITCHAPI_RETROSPECTIVE_EVALUATION_V1", "PITCHAPI"),
    }
    observed: set[tuple[str, str]] = set()
    for track in tracks:
        if not isinstance(track, Mapping):
            raise ProjectStatusError("evaluation_tracks entries must be objects")
        protocol_id = track.get("evaluation_protocol_id")
        provider = track.get("provider")
        route_status = track.get("status")
        identity_fields = (protocol_id, provider, route_status)
        if not all(isinstance(value, str) and value for value in identity_fields):
            raise ProjectStatusError("evaluation track identity and status fields are required")
        identity = (cast(str, protocol_id), cast(str, provider))
        if identity in observed:
            raise ProjectStatusError(f"duplicate evaluation track: {identity[0]} / {identity[1]}")
        observed.add(identity)
        _evidence_path(track, f"evaluation_tracks[{identity[0]}]", root)
    if observed != expected:
        raise ProjectStatusError(
            "evaluation_tracks must contain the isolated StatsBomb and PitchAPI tracks"
        )


def _validate_phase_3(
    section: Mapping[str, object],
    sprint_2: Mapping[str, object],
    owner_decisions: Sequence[str],
    root: Path,
) -> None:
    status = _require_status(section, "phase_3", _PHASE_3_STATUSES)
    blocked_by = section.get("blocked_by")
    if not isinstance(blocked_by, list) or not all(isinstance(value, str) for value in blocked_by):
        raise ProjectStatusError("phase_3.blocked_by must be a list of strings")
    _validate_phase_3_research(section, owner_decisions, root)
    if sprint_2.get("status") != "FAIL":
        return
    if section.get("authorized") is not False:
        raise ProjectStatusError("sprint_2.status=FAIL requires phase_3.authorized=false")
    if status != "BLOCKED":
        raise ProjectStatusError("sprint_2.status=FAIL requires phase_3.status=BLOCKED")
    if "sprint_2" not in blocked_by:
        raise ProjectStatusError(
            "sprint_2.status=FAIL requires phase_3.blocked_by to include sprint_2"
        )


def _validate_phase_3_research(
    section: Mapping[str, object], owner_decisions: Sequence[str], root: Path
) -> None:
    research = section.get("research")
    if research is None:
        return
    if not isinstance(research, Mapping):
        raise ProjectStatusError("phase_3.research must be an object")
    if not isinstance(research.get("authorized"), bool):
        raise ProjectStatusError("phase_3.research.authorized must be a boolean")
    if research.get("authorized") is not True:
        return
    decision = research.get("decision")
    if not isinstance(decision, str) or not decision:
        raise ProjectStatusError("phase_3.research.authorized=true requires a decision")
    if decision not in owner_decisions:
        raise ProjectStatusError(
            f"phase_3.research.decision={decision} is not reconciled in owner_decisions"
        )
    reference = research.get("decision_ref")
    if not isinstance(reference, str) or not reference:
        raise ProjectStatusError("phase_3.research.authorized=true requires a decision_ref")
    path = _resolve_repository_path(reference, "phase_3.research.decision_ref", root)
    if decision not in path.read_text(encoding="utf-8"):
        raise ProjectStatusError(f"decision_ref does not record decision {decision}")


def _resolve_repository_path(reference: str, description: str, root: Path) -> Path:
    relative_path = Path(reference)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ProjectStatusError(f"{description} must be a repository-relative path")
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ProjectStatusError(f"{description} escapes the repository")
    if not path.is_file():
        raise ProjectStatusError(f"referenced file does not exist: {reference}")
    return path


def _require_status(
    section: Mapping[str, object], section_name: str, allowed: frozenset[str]
) -> str:
    value = section.get("status")
    if not isinstance(value, str) or value not in allowed:
        raise ProjectStatusError(f"{section_name}.status has unsupported value: {value!r}")
    return value


def _evidence_path(section: Mapping[str, object], section_name: str, root: Path) -> Path:
    reference = section.get("evidence_ref")
    if not isinstance(reference, str) or not reference:
        raise ProjectStatusError(f"{section_name}.evidence_ref must be a repository-relative path")
    relative_path = Path(reference)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ProjectStatusError(f"{section_name}.evidence_ref must be a repository-relative path")
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ProjectStatusError(f"{section_name}.evidence_ref escapes the repository")
    if not path.is_file():
        raise ProjectStatusError(f"evidence file does not exist: {reference}")
    return path


def _markdown_status(path: Path) -> str:
    if path.suffix != ".md":
        raise ProjectStatusError(f"sprint_2 evidence must be Markdown: {path}")
    match = _SPRINT_STATUS_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ProjectStatusError(f"sprint_2 evidence has no recognized status: {path}")
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())
