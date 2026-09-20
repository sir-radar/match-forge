from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from football.project_status import ProjectStatusError, validate_project_status

_DECISION_ID = "RETAIN_SPRINT2_FAIL_CLOSE_SHARED_PACE_AND_AUTHORIZE_PHASE3_RESEARCH_V1"


def test_phase_2b_pass_matches_gate_evidence(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)

    validate_project_status(status_path, repository_root)


def test_repository_project_status_is_valid() -> None:
    repository_root = Path(__file__).resolve().parents[3]

    validate_project_status(repository_root / "docs/project-status.json", repository_root)


def test_phase_2b_disagreement_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "phase_2b")["status"] = "FAIL"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="phase_2b.status=FAIL disagrees"):
        validate_project_status(status_path, repository_root)


def test_sprint_2_failure_requires_retain_fail_and_stop(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "sprint_2")["owner_decision"] = "PROMOTE"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="owner_decision=RETAIN_FAIL_AND_STOP"):
        validate_project_status(status_path, repository_root)


def test_sprint_2_failure_rejects_a_challenger(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "sprint_2")["challenger_authorized"] = True
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="challenger_authorized=false"):
        validate_project_status(status_path, repository_root)


def test_sprint_2_failure_rejects_model_promotion(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "sprint_2")["model_promoted"] = True
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="model_promoted=false"):
        validate_project_status(status_path, repository_root)


def test_sprint_2_failure_rejects_phase_3_authorization(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "phase_3")["authorized"] = True
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="phase_3.authorized=false"):
        validate_project_status(status_path, repository_root)


def test_phase_3_research_authorization_matches_owner_decision(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)

    validate_project_status(status_path, repository_root)


def test_phase_3_research_requires_a_recorded_decision(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    research = _section(status, "phase_3")["research"]
    assert isinstance(research, dict)
    research["decision"] = "UNRECORDED_DECISION_V1"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="not reconciled in owner_decisions"):
        validate_project_status(status_path, repository_root)


def test_phase_3_research_decision_ref_must_record_the_decision(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    (repository_root / "docs/evidence/unrelated-decision.md").write_text(
        "A decision reference that does not name its decision.\n",
        encoding="utf-8",
    )
    research = _section(status, "phase_3")["research"]
    assert isinstance(research, dict)
    research["decision_ref"] = "docs/evidence/unrelated-decision.md"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="decision_ref does not record decision"):
        validate_project_status(status_path, repository_root)


def test_unrecorded_owner_decision_evidence_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["owner_decisions"] = []
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="not reconciled in owner_decisions"):
        validate_project_status(status_path, repository_root)


def test_owner_decisions_entry_without_a_record_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["owner_decisions"] = [_DECISION_ID, "MISSING_DECISION_V1"]
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="no decision record"):
        validate_project_status(status_path, repository_root)


def test_closed_route_outcome_must_match_its_evidence(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["closed_routes"] = [
        {
            "route": "DCV3_SHARED_MATCH_PACE_MIXTURE_V1",
            "outcome": "CLOSED",
            "evidence_ref": "docs/evidence/shared-pace-admission.md",
        }
    ]
    _write_json(status_path, status)

    validate_project_status(status_path, repository_root)


def test_closed_route_with_unsupported_outcome_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["closed_routes"] = [
        {
            "route": "DCV3_SHARED_MATCH_PACE_MIXTURE_V1",
            "outcome": "RETRY_AUTHORIZED",
            "evidence_ref": "docs/evidence/shared-pace-admission.md",
        }
    ]
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="unsupported value"):
        validate_project_status(status_path, repository_root)


def test_closed_route_evidence_must_mention_the_route(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["closed_routes"] = [
        {
            "route": "OTHER_ROUTE_V1",
            "outcome": "CLOSED",
            "evidence_ref": "docs/evidence/shared-pace-admission.md",
        }
    ]
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="does not mention route"):
        validate_project_status(status_path, repository_root)


def test_missing_evidence_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "phase_1b")["evidence_ref"] = "docs/evidence/missing.json"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="evidence file does not exist"):
        validate_project_status(status_path, repository_root)


def test_malformed_json_evidence_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    (repository_root / "docs/evidence/gate.json").write_text("{", encoding="utf-8")

    with pytest.raises(ProjectStatusError, match="malformed JSON evidence"):
        validate_project_status(status_path, repository_root)


def test_unknown_status_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    _section(status, "phase_1b")["status"] = "UNKNOWN"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="phase_1b.status has unsupported value"):
        validate_project_status(status_path, repository_root)


def test_unsupported_contract_is_rejected(tmp_path: Path) -> None:
    repository_root, status_path = _write_repository(tmp_path)
    status = _read_json(status_path)
    status["contract"] = "ProjectStatusV3"
    _write_json(status_path, status)

    with pytest.raises(ProjectStatusError, match="unsupported contract"):
        validate_project_status(status_path, repository_root)


def _write_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path / "repository"
    evidence_directory = repository_root / "docs/evidence"
    evidence_directory.mkdir(parents=True)
    _write_json(
        evidence_directory / "gate.json",
        {"phase_1b_status": "PASS", "phase_2b_status": "PASS"},
    )
    (evidence_directory / "sprint-2.md").write_text(
        "Status: **FAIL**\n\nOwner decision: `RETAIN_FAIL_AND_STOP`\n",
        encoding="utf-8",
    )
    (evidence_directory / "shared-pace-admission.md").write_text(
        "Algorithm: DCV3_SHARED_MATCH_PACE_MIXTURE_V1\n"
        "Result: FROZEN_100_MATCH_TRAINING_ONLY_ADMISSION_FAIL\n",
        encoding="utf-8",
    )
    _write_json(evidence_directory / _decision_record_ref(), _decision_record())
    status_path = repository_root / "docs/project-status.json"
    _write_json(status_path, _valid_status())
    return repository_root, status_path


def _decision_record_ref() -> str:
    return "owner-decision-test-2026-09-20.json"


def _decision_record() -> dict[str, object]:
    return {
        "decision_id": _DECISION_ID,
        "recorded_at": "2026-09-20T04:58:42Z",
    }


def _valid_status() -> dict[str, object]:
    return {
        "contract": "ProjectStatusV2",
        "updated_at": "2026-09-20T05:00:00Z",
        "owner_decisions": [_DECISION_ID],
        "closed_routes": [
            {
                "route": "DCV3_SHARED_MATCH_PACE_MIXTURE_V1",
                "outcome": "TERMINAL_ROUTE_FAIL",
                "evidence_ref": "docs/evidence/shared-pace-admission.md",
            }
        ],
        "phase_1b": {"status": "PASS", "evidence_ref": "docs/evidence/gate.json"},
        "phase_2b": {"status": "PASS", "evidence_ref": "docs/evidence/gate.json"},
        "sprint_2": {
            "status": "FAIL",
            "owner_decision": "RETAIN_FAIL_AND_STOP",
            "challenger_authorized": False,
            "model_promoted": False,
            "evidence_ref": "docs/evidence/sprint-2.md",
        },
        "phase_3": {
            "status": "BLOCKED",
            "authorized": False,
            "blocked_by": ["sprint_2"],
            "research": {
                "authorized": True,
                "decision": _DECISION_ID,
                "decision_ref": "docs/evidence/" + _decision_record_ref(),
            },
        },
    }


def _read_json(path: Path) -> dict[str, object]:
    return deepcopy(json.loads(path.read_text(encoding="utf-8")))


def _section(status: dict[str, object], name: str) -> dict[str, object]:
    value = status[name]
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
