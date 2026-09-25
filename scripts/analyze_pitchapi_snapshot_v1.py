#!/usr/bin/env python3
"""Verify and assess the sealed PitchAPI snapshot without running evaluation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from itertools import combinations
from pathlib import Path
from typing import Any, cast

import numpy as np
from football.contracts.source import canonical_json_bytes
from football.validation.pitchapi_compatibility import (
    PitchApiXgCompatibilityPolicyV1,
    PitchApiXgDistributionComparisonV1,
    PitchApiXgScopeDiagnosticsV1,
    evaluate_pitchapi_xg_compatibility,
)
from scipy.stats import ks_2samp

_ROOT = Path(".local/pitchapi-snapshot-v1")
_OUTPUT = Path(".local/pitchapi-snapshot-v1-analysis")
_POLICY_PATH = Path("docs/evaluation/pitchapi-retrospective-evaluation-v1-policy-proposal.json")
_PERIODS = frozenset(("FirstHalf", "SecondHalf"))
_SITUATIONS = frozenset(
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
_EVENT_TYPES = frozenset(("AttemptSaved", "Goal", "Miss", "Post"))


def analyze(root: Path = _ROOT, output: Path = _OUTPUT) -> dict[str, object]:
    if output.exists():
        raise RuntimeError("analysis output already exists")
    output.mkdir(parents=True)
    primary = root / "primary"
    backup = root / "backup"
    primary_inventory = _inventory(primary)
    backup_inventory = _inventory(backup)
    backup_status = "PASS" if primary_inventory == backup_inventory else "FAIL"
    if backup_status != "PASS":
        raise RuntimeError("snapshot backup inventory mismatch")
    snapshot = _snapshot_manifest(primary)
    _verify_snapshot_resources(primary, snapshot)
    policy = _policy()
    rows = _shot_rows(primary, snapshot)
    diagnostics = tuple(_diagnostic(scope, values, clip=1e-6) for scope, values in rows.items())
    comparisons = _comparisons(rows, minimum_situation_shots=100, exclude_penalties=False)
    scope_keys = tuple(sorted(rows))
    primary_report = evaluate_pitchapi_xg_compatibility(
        policy, diagnostics, comparisons, required_scope_keys=scope_keys
    )
    sensitivity = _sensitivity(policy, rows, scope_keys)
    report: dict[str, object] = {
        "contract": "PitchApiSnapshotV1ReadinessReportV1",
        "evaluation_protocol_id": "PITCHAPI_RETROSPECTIVE_EVALUATION_V1",
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "snapshot_document_sha256": _sha256_bytes(canonical_json_bytes(snapshot)),
        "configuration_sha256": snapshot["configuration_sha256"],
        "backup_status": backup_status,
        "backup_inventory_sha256": _sha256_bytes(canonical_json_bytes(primary_inventory)),
        "resource_count": len(snapshot["resources"]),
        "diagnostics": [asdict(item) for item in diagnostics],
        "comparisons": [asdict(item) for item in comparisons],
        "compatibility": asdict(primary_report),
        "sensitivity": sensitivity,
        "observational_compatibility_only": True,
        "evaluation_executed": False,
    }
    payload = canonical_json_bytes(report)
    report_sha = _sha256_bytes(payload)
    report["report_sha256"] = report_sha
    (output / "readiness-report.json").write_bytes(canonical_json_bytes(report) + b"\n")
    return report


def _policy() -> PitchApiXgCompatibilityPolicyV1:
    document = json.loads(_POLICY_PATH.read_text())
    values = document["proposed_compatibility"]
    return PitchApiXgCompatibilityPolicyV1(**values)


def _snapshot_manifest(primary: Path) -> dict[str, Any]:
    result = json.loads((_ROOT / "RESULT.json").read_text())
    path = primary / result["snapshot_manifest"]
    document = json.loads(path.read_text())
    if _sha256_bytes(canonical_json_bytes(document)) != result["snapshot_document_sha256"]:
        raise RuntimeError("snapshot document hash mismatch")
    if document["snapshot_sha256"] != result["snapshot_sha256"]:
        raise RuntimeError("snapshot identity mismatch")
    return cast(dict[str, Any], document)


def _verify_snapshot_resources(primary: Path, snapshot: dict[str, Any]) -> None:
    refs: set[str] = set()
    for resource in snapshot["resources"]:
        ref = str(resource["resource_ref"])
        if ref in refs:
            raise RuntimeError("duplicate snapshot resource")
        refs.add(ref)
        for prefix in ("raw", "normalized"):
            path = primary / resource[f"{prefix}_relative_path"]
            if _sha256_file(path) != resource[f"{prefix}_sha256"]:
                raise RuntimeError(f"{prefix} resource hash mismatch")


def _shot_rows(primary: Path, snapshot: dict[str, Any]) -> dict[str, list[dict[str, object]]]:
    rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for resource in snapshot["resources"]:
        if resource["kind"] != "match_shots":
            continue
        scope = str(resource["scope_key"])
        payload = json.loads((primary / resource["normalized_relative_path"]).read_text())
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("periods"), list):
            raise RuntimeError("malformed retained shot resource")
        for period in data["periods"]:
            period_name = period.get("period")
            if period_name not in _PERIODS or not isinstance(period.get("shots"), list):
                raise RuntimeError("unknown period semantics")
            for shot in period["shots"]:
                row = _normalized_shot(shot, str(period_name))
                rows[scope].append(row)
    return dict(rows)


def _normalized_shot(shot: object, period: str) -> dict[str, object]:
    if not isinstance(shot, dict):
        raise RuntimeError("malformed shot")
    required = ("id", "team_id", "expected_goals", "situation", "event_type")
    if any(field not in shot or shot[field] is None for field in required):
        raise RuntimeError("required shot field missing")
    xg = shot["expected_goals"]
    situation = shot["situation"]
    event_type = shot["event_type"]
    if (
        isinstance(xg, bool)
        or not isinstance(xg, (int, float))
        or not math.isfinite(float(xg))
        or not 0 <= float(xg) <= 1
    ):
        raise RuntimeError("invalid xG")
    if situation not in _SITUATIONS:
        raise RuntimeError("unknown shot situation")
    if event_type not in _EVENT_TYPES:
        raise RuntimeError("unknown shot outcome semantics")
    return {
        "shot_id": str(shot["id"]),
        "team_id": str(shot["team_id"]),
        "period": period,
        "xg": float(xg),
        "situation": str(situation),
        "goal": event_type == "Goal",
    }


def _diagnostic(
    scope: str, rows: list[dict[str, object]], *, clip: float
) -> PitchApiXgScopeDiagnosticsV1:
    xg = np.asarray([_xg(row) for row in rows])
    situations = Counter(str(row["situation"]) for row in rows)
    penalties = np.asarray([_xg(row) for row in rows if row["situation"] == "Penalty"])
    calibration_rows = [row for row in rows if row["situation"] != "Penalty"]
    calibration_xg = np.asarray([_xg(row) for row in calibration_rows])
    goals = np.asarray([1.0 if row["goal"] else 0.0 for row in calibration_rows])
    fit = _logistic_fit(calibration_xg, goals, clip=clip)
    quantiles = np.quantile(xg, (0.1, 0.5, 0.9))
    penalty_quantiles = np.quantile(penalties, (0.25, 0.5, 0.75))
    return PitchApiXgScopeDiagnosticsV1(
        scope_key=scope,
        shot_count=len(rows),
        missing_xg_count=0,
        invalid_xg_count=0,
        schema_consistent=True,
        penalty_semantics_consistent=True,
        shot_situation_semantics_consistent=True,
        period_semantics_consistent=True,
        xg_mean=float(np.mean(xg)),
        xg_standard_deviation=float(np.std(xg)),
        xg_quantiles=cast(tuple[float, float, float], tuple(float(value) for value in quantiles)),
        penalty_shot_count=len(penalties),
        penalty_xg_minimum=float(np.min(penalties)) if len(penalties) else None,
        penalty_xg_maximum=float(np.max(penalties)) if len(penalties) else None,
        penalty_xg_median=float(penalty_quantiles[1]) if len(penalties) else None,
        penalty_xg_iqr=float(penalty_quantiles[2] - penalty_quantiles[0])
        if len(penalties)
        else None,
        calibration_shot_count=len(calibration_rows),
        calibration_intercept=fit[0] if fit is not None else None,
        calibration_slope=fit[1] if fit is not None else None,
        situation_shot_counts=tuple(sorted(situations.items())),
    )


def _logistic_fit(
    xg: np.ndarray[Any, Any], goals: np.ndarray[Any, Any], *, clip: float
) -> tuple[float, float] | None:
    predictor = np.log(np.clip(xg, clip, 1 - clip) / (1 - np.clip(xg, clip, 1 - clip)))
    design = np.column_stack((np.ones(len(predictor)), predictor))
    beta = np.asarray((0.0, 1.0))
    for _iteration in range(100):
        linear = np.clip(design @ beta, -40, 40)
        probabilities = 1.0 / (1.0 + np.exp(-linear))
        weights = probabilities * (1 - probabilities)
        information = design.T @ (weights[:, None] * design)
        score = design.T @ (goals - probabilities)
        try:
            step = np.linalg.solve(information, score)
        except np.linalg.LinAlgError:
            return None
        beta += step
        if float(np.max(np.abs(step))) < 1e-10:
            return float(beta[0]), float(beta[1])
    return None


def _comparisons(
    rows: dict[str, list[dict[str, object]]],
    *,
    minimum_situation_shots: int,
    exclude_penalties: bool,
) -> tuple[PitchApiXgDistributionComparisonV1, ...]:
    result: list[PitchApiXgDistributionComparisonV1] = []
    for left, right in combinations(sorted(rows), 2):
        left_rows = [
            row for row in rows[left] if not exclude_penalties or row["situation"] != "Penalty"
        ]
        right_rows = [
            row for row in rows[right] if not exclude_penalties or row["situation"] != "Penalty"
        ]
        result.append(_ks(left, right, "ALL_SHOTS", left_rows, right_rows))
        situations = {str(row["situation"]) for row in left_rows} & {
            str(row["situation"]) for row in right_rows
        }
        for situation in sorted(situations):
            left_situation = [row for row in left_rows if row["situation"] == situation]
            right_situation = [row for row in right_rows if row["situation"] == situation]
            if (
                len(left_situation) >= minimum_situation_shots
                and len(right_situation) >= minimum_situation_shots
            ):
                result.append(_ks(left, right, situation, left_situation, right_situation))
    return tuple(result)


def _ks(
    left: str,
    right: str,
    situation: str,
    left_rows: list[dict[str, object]],
    right_rows: list[dict[str, object]],
) -> PitchApiXgDistributionComparisonV1:
    measurement = ks_2samp(
        [_xg(row) for row in left_rows],
        [_xg(row) for row in right_rows],
        method="auto",
    )
    return PitchApiXgDistributionComparisonV1(
        left,
        right,
        float(measurement.statistic),
        float(measurement.pvalue),
        len(left_rows),
        len(right_rows),
        situation,
    )


def _sensitivity(
    policy: PitchApiXgCompatibilityPolicyV1,
    rows: dict[str, list[dict[str, object]]],
    scope_keys: tuple[str, ...],
) -> dict[str, object]:
    clipping = {
        str(clip): [
            {
                "scope_key": scope,
                "intercept": diagnostic.calibration_intercept,
                "slope": diagnostic.calibration_slope,
            }
            for scope in scope_keys
            for diagnostic in (_diagnostic(scope, rows[scope], clip=clip),)
        ]
        for clip in (1e-5, 1e-4)
    }
    with_penalties = {
        scope: _logistic_fit(
            np.asarray([_xg(row) for row in rows[scope]]),
            np.asarray([1.0 if row["goal"] else 0.0 for row in rows[scope]]),
            clip=1e-6,
        )
        for scope in scope_keys
    }
    ks_without_penalties = _comparisons(rows, minimum_situation_shots=100, exclude_penalties=True)
    floors = {
        str(floor): len(_comparisons(rows, minimum_situation_shots=floor, exclude_penalties=False))
        for floor in (75, 100, 150)
    }
    threshold_reports: dict[str, object] = {}
    primary_diagnostics = tuple(_diagnostic(scope, rows[scope], clip=1e-6) for scope in scope_keys)
    primary_comparisons = _comparisons(rows, minimum_situation_shots=100, exclude_penalties=False)
    for label, factor in (("80_percent", 0.8), ("120_percent", 1.2)):
        varied = replace(
            policy,
            maximum_penalty_iqr=policy.maximum_penalty_iqr * factor,
            maximum_penalty_median_difference=(policy.maximum_penalty_median_difference * factor),
            maximum_absolute_calibration_intercept=(
                policy.maximum_absolute_calibration_intercept * factor
            ),
            minimum_calibration_slope=1 - (1 - policy.minimum_calibration_slope) * factor,
            maximum_calibration_slope=1 + (policy.maximum_calibration_slope - 1) * factor,
            maximum_distribution_discontinuity=(policy.maximum_distribution_discontinuity * factor),
        )
        varied_report = evaluate_pitchapi_xg_compatibility(
            varied,
            primary_diagnostics,
            primary_comparisons,
            required_scope_keys=scope_keys,
        )
        threshold_reports[label] = asdict(varied_report)
    leave_one_out: dict[str, object] = {}
    for omitted in scope_keys:
        retained = tuple(scope for scope in scope_keys if scope != omitted)
        retained_diagnostics = tuple(
            diagnostic for diagnostic in primary_diagnostics if diagnostic.scope_key in retained
        )
        retained_comparisons = tuple(
            comparison
            for comparison in primary_comparisons
            if comparison.left_scope_key in retained and comparison.right_scope_key in retained
        )
        leave_one_out[omitted] = asdict(
            evaluate_pitchapi_xg_compatibility(
                policy,
                retained_diagnostics,
                retained_comparisons,
                required_scope_keys=retained,
            )
        )
    return {
        "calibration_clipping": clipping,
        "calibration_with_penalties": with_penalties,
        "ks_without_penalties": [asdict(item) for item in ks_without_penalties],
        "situation_floor_comparison_counts": floors,
        "threshold_variants": threshold_reports,
        "leave_one_scope_out": leave_one_out,
    }


def _inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _xg(row: dict[str, object]) -> float:
    value = row["xg"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError("normalized xG type is invalid")
    return float(value)


def main() -> int:
    report = analyze()
    compatibility = cast(dict[str, object], report["compatibility"])
    summary = {
        "status": compatibility["status"],
        "snapshot_sha256": report["snapshot_sha256"],
        "report_sha256": report["report_sha256"],
        "findings": compatibility["findings"],
        "warnings": compatibility["warnings"],
    }
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
