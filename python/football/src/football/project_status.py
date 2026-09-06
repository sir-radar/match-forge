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

_CONTRACT = "ProjectStatusV1"
_PHASE_STATUSES = frozenset(("PASS", "PASS_WITH_WARNINGS", "FAIL", "NOT_RUN"))
_PHASE_3_STATUSES = frozenset(("BLOCKED", "PASS", "FAIL", "NOT_RUN"))
_SPRINT_STATUS_PATTERN = re.compile(
    r"^Status:\s+\*{0,2}(PASS|PASS_WITH_WARNINGS|FAIL|NOT_RUN)\*{0,2}\s*$",
    re.MULTILINE,
)


class ProjectStatusError(ValueError):
    """A ProjectStatusV1 record does not match its evidence or progression rules."""


def validate_project_status(status_path: Path, repository_root: Path | None = None) -> None:
    """Fail when ProjectStatusV1 is malformed or disagrees with repository evidence."""
    root = (repository_root or status_path.resolve().parents[1]).resolve()
    status = _load_json(status_path, "project status")
    _require_contract(status)
    _require_utc_timestamp(status)

    phase_1b = _require_section(status, "phase_1b")
    phase_2b = _require_section(status, "phase_2b")
    sprint_2 = _require_section(status, "sprint_2")
    phase_3 = _require_section(status, "phase_3")

    _validate_phase(status_name="phase_1b", section=phase_1b, root=root)
    _validate_phase(status_name="phase_2b", section=phase_2b, root=root)
    _validate_sprint_2(sprint_2, root)
    _validate_phase_3(phase_3, sprint_2)


def main(argv: Sequence[str] | None = None, *, stderr: TextIO | None = None) -> int:
    """Run ProjectStatusV1 validation for the supplied repository status file."""
    parser = argparse.ArgumentParser(description="validate ProjectStatusV1")
    parser.add_argument("status_path", type=Path)
    arguments = parser.parse_args(argv)
    errors = sys.stderr if stderr is None else stderr
    try:
        validate_project_status(arguments.status_path)
    except ProjectStatusError as error:
        print(f"ProjectStatusV1 invalid: {error}", file=errors)
        return 1
    print("ProjectStatusV1 valid")
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
    value = status.get("updated_at")
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProjectStatusError("updated_at must be a UTC ISO-8601 timestamp ending in Z")
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ProjectStatusError(
            "updated_at must be a UTC ISO-8601 timestamp ending in Z"
        ) from error


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


def _validate_phase_3(section: Mapping[str, object], sprint_2: Mapping[str, object]) -> None:
    status = _require_status(section, "phase_3", _PHASE_3_STATUSES)
    blocked_by = section.get("blocked_by")
    if not isinstance(blocked_by, list) or not all(isinstance(value, str) for value in blocked_by):
        raise ProjectStatusError("phase_3.blocked_by must be a list of strings")
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
