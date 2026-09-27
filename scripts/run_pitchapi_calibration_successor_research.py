"""Run the authorized development-only PitchAPI calibration successor research."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_calibration_successor import (
    ALGORITHM_VERSION,
    DEVELOPMENT_MANIFEST_SHA256,
    FORECAST_WARMUP_TARGETS,
    OOS_BLOCK_TARGETS,
    RESEARCH_ID,
    SENSITIVITY_STRENGTHS,
    SHRINKAGE_STRENGTH,
    TARGET_COUNT,
    V5_CHALLENGER_SHA256,
    CalibrationRowV1,
    GlobalVectorScalingV1,
    calibration_summary,
    fit_global_vector_scaling,
    paired_moving_block_interval,
    probability_scores,
    reliability_summary,
    rows_sha256,
)
from football.forecasting.pitchapi_v3 import (
    HistoryObservationV1,
    TransferableGoalModelV1,
    TransferableTrainingRowV1,
    build_training_rows,
    fit_transferable_parameters,
)
from football.forecasting.pitchapi_v3_evaluation import exact_distribution, score_target
from prepare_pitchapi_v3_transferable_models import load_development

SNAPSHOT_SHA256 = "435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea"
REFERENCE_ARTIFACT_SHA256 = "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"
PREREGISTRATION_PATH = Path(
    "docs/evaluation/pitchapi-v5-calibration-successor-preregistration.json"
)


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    calibration: CalibrationRowV1
    reference_probabilities: tuple[float, float, float]
    reference_scores: dict[str, float]
    challenger_scores: dict[str, float]
    fold: int


def execute(
    snapshot_root: Path,
    *,
    source_commit: str,
    dependency_lock_sha256: str,
    preregistration_sha256: str,
) -> dict[str, object]:
    observations = load_development(snapshot_root)
    rows = build_training_rows(observations, scope_key="bundesliga_2021_22")
    if len(rows) != TARGET_COUNT:
        raise RuntimeError(f"expected {TARGET_COUNT} development targets, got {len(rows)}")
    _verify_chronology(rows)
    records = _generate_oos_records(rows, observations)
    if len(records) != 4 * OOS_BLOCK_TARGETS:
        raise RuntimeError("unexpected OOS prediction count")
    validation, folds = _calibrate_validation(records)
    final_calibrator = fit_global_vector_scaling(
        tuple(record.calibration for record in records),
        shrinkage_strength=SHRINKAGE_STRENGTH,
    )
    coverage = _coverage(rows)
    oos_manifest = _oos_manifest(records)
    oos_manifest_sha256 = hashlib.sha256(canonical_json_bytes(oos_manifest) + b"\n").hexdigest()
    artifact = {
        "algorithm_version": ALGORITHM_VERSION,
        "calibration_fit": final_calibrator.to_dict(),
        "challenger_artifact_sha256": V5_CHALLENGER_SHA256,
        "contract": "PitchApiCalibrationArtifactV1",
        "dependency_lock_sha256": dependency_lock_sha256,
        "development_manifest_sha256": DEVELOPMENT_MANIFEST_SHA256,
        "development_scope": "bundesliga_2021_22",
        "development_target_count": TARGET_COUNT,
        "football_cutoff": max(row.context.kickoff_at for row in rows).isoformat(),
        "knowledge_cutoff": max(row.context.kickoff_at for row in rows).isoformat(),
        "knowledge_mode": "RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
        "oos_prediction_manifest_sha256": oos_manifest_sha256,
        "preregistration_sha256": preregistration_sha256,
        "research_id": RESEARCH_ID,
        "reference_artifact_sha256": REFERENCE_ARTIFACT_SHA256,
        "serializer_version": "canonical-json-sort-keys-compact-v1",
        "snapshot_sha256": SNAPSHOT_SHA256,
        "source_commit": source_commit,
    }
    evidence = _evidence(
        records,
        validation,
        folds,
        coverage=coverage,
        final_calibrator=final_calibrator,
        preregistration_sha256=preregistration_sha256,
    )
    return {
        "artifact": artifact,
        "coverage": coverage,
        "evidence": evidence,
        "oos_manifest": oos_manifest,
    }


def _generate_oos_records(
    rows: tuple[TransferableTrainingRowV1, ...],
    observations: Sequence[HistoryObservationV1],
) -> tuple[ForecastRecord, ...]:
    output: list[ForecastRecord] = []
    for fold in range(4):
        start = FORECAST_WARMUP_TARGETS + fold * OOS_BLOCK_TARGETS
        end = start + OOS_BLOCK_TARGETS
        validation_rows = rows[start:end]
        validation_start = validation_rows[0].context.kickoff_at
        fit_observations = tuple(
            item for item in observations if item.kickoff_at < validation_start
        )
        reference = TransferableGoalModelV1(
            fit_transferable_parameters(rows[:start], fit_observations, include_xg=False)
        )
        challenger = TransferableGoalModelV1(
            fit_transferable_parameters(rows[:start], fit_observations, include_xg=True)
        )
        for row in validation_rows:
            reference_forecast = reference.forecast_features(row.features)
            challenger_forecast = challenger.forecast_features(row.features)
            outcome = (
                0
                if row.home_goals > row.away_goals
                else 1
                if row.home_goals == row.away_goals
                else 2
            )
            raw = (
                challenger_forecast.markets.home_win,
                challenger_forecast.markets.draw,
                challenger_forecast.markets.away_win,
            )
            reference_probabilities = (
                reference_forecast.markets.home_win,
                reference_forecast.markets.draw,
                reference_forecast.markets.away_win,
            )
            reference_score = score_target(
                exact_distribution(reference_forecast),
                home_goals=row.home_goals,
                away_goals=row.away_goals,
            ).to_dict()
            challenger_score = score_target(
                exact_distribution(challenger_forecast),
                home_goals=row.home_goals,
                away_goals=row.away_goals,
            ).to_dict()
            output.append(
                ForecastRecord(
                    calibration=CalibrationRowV1(
                        match_id=str(row.context.match_id),
                        kickoff_at=row.context.kickoff_at.isoformat(),
                        kickoff_batch=_batch_number(rows, row.context.kickoff_at),
                        probabilities=raw,
                        outcome=outcome,
                    ),
                    reference_probabilities=reference_probabilities,
                    reference_scores=reference_score,
                    challenger_scores=challenger_score,
                    fold=fold + 1,
                )
            )
    return tuple(output)


def _calibrate_validation(
    records: tuple[ForecastRecord, ...],
) -> tuple[tuple[tuple[ForecastRecord, CalibrationRowV1], ...], list[dict[str, object]]]:
    validation: list[tuple[ForecastRecord, CalibrationRowV1]] = []
    folds: list[dict[str, object]] = []
    for fold in range(2, 5):
        training = tuple(record.calibration for record in records if record.fold < fold)
        scoring = tuple(record for record in records if record.fold == fold)
        calibrator = fit_global_vector_scaling(training, shrinkage_strength=SHRINKAGE_STRENGTH)
        unshrunk = fit_global_vector_scaling(training, shrinkage_strength=0.0)
        sensitivity = {
            str(strength): fit_global_vector_scaling(
                training, shrinkage_strength=strength
            ).to_dict()
            for strength in SENSITIVITY_STRENGTHS
        }
        for record in scoring:
            calibrated = calibrator.calibrate(record.calibration.probabilities)
            validation.append(
                (
                    record,
                    CalibrationRowV1(
                        record.calibration.match_id,
                        record.calibration.kickoff_at,
                        record.calibration.kickoff_batch,
                        calibrated,
                        record.calibration.outcome,
                    ),
                )
            )
        folds.append(
            {
                "calibration_fit_rows": len(training),
                "candidate": calibrator.to_dict(),
                "fold": fold,
                "sensitivity_diagnostics_not_admission_candidates": sensitivity,
                "unshrunk_diagnostic": unshrunk.to_dict(),
                "validation_rows": len(scoring),
            }
        )
    return tuple(validation), folds


def _evidence(
    records: tuple[ForecastRecord, ...],
    validation: tuple[tuple[ForecastRecord, CalibrationRowV1], ...],
    folds: list[dict[str, object]],
    *,
    coverage: dict[str, object],
    final_calibrator: GlobalVectorScalingV1,
    preregistration_sha256: str,
) -> dict[str, object]:
    raw_rows = tuple(pair[0].calibration for pair in validation)
    calibrated_rows = tuple(pair[1] for pair in validation)
    reference_rows = tuple(
        CalibrationRowV1(
            record.calibration.match_id,
            record.calibration.kickoff_at,
            record.calibration.kickoff_batch,
            record.reference_probabilities,
            record.calibration.outcome,
        )
        for record, _ in validation
    )
    metrics: dict[str, object] = {}
    for name in ("one_x_two_log_loss", "one_x_two_brier", "one_x_two_rps"):
        reference = [
            probability_scores(row.probabilities, row.outcome)[name] for row in reference_rows
        ]
        raw = [probability_scores(row.probabilities, row.outcome)[name] for row in raw_rows]
        calibrated = [
            probability_scores(row.probabilities, row.outcome)[name] for row in calibrated_rows
        ]
        metrics[name] = _metric_summary(reference, raw, calibrated, raw_rows)
    for name in ("joint_score_log_loss", "total_goal_crps"):
        reference = [record.reference_scores[name] for record, _ in validation]
        raw = [record.challenger_scores[name] for record, _ in validation]
        metrics[name] = _metric_summary(reference, raw, raw, raw_rows)
    calibration: dict[str, object] = {
        "calibrated": calibration_summary(calibrated_rows),
        "raw": calibration_summary(raw_rows),
        "reference": calibration_summary(reference_rows),
    }
    disposition, admission = _admission(metrics, calibration)
    return {
        "admission": admission,
        "calibration": calibration,
        "contract": "PitchApiCalibrationSuccessorDevelopmentEvidenceV1",
        "coverage": coverage,
        "development_manifest_sha256": DEVELOPMENT_MANIFEST_SHA256,
        "development_only": True,
        "development_target_count": TARGET_COUNT,
        "final_calibration_fit": final_calibrator.to_dict(),
        "folds": folds,
        "metrics": metrics,
        "oos_prediction_count": len(records),
        "preregistration_sha256": preregistration_sha256,
        "reliability": {
            "calibrated": reliability_summary(calibrated_rows),
            "raw": reliability_summary(raw_rows),
        },
        "research_id": RESEARCH_ID,
        "result_classification": disposition,
        "validation_target_count": len(validation),
        "v5_firewall": {
            "evaluation_manifest_loaded": False,
            "evaluation_outcome_rows_loaded": 0,
            "fitting_or_model_selection_use": False,
            "status": "PASS",
            "v5_target_rows_loaded": 0,
        },
    }


def _metric_summary(
    reference: list[float],
    raw: list[float],
    calibrated: list[float],
    rows: Sequence[CalibrationRowV1],
) -> dict[str, object]:
    batches = [row.kickoff_batch for row in rows]
    return {
        "calibrated": sum(calibrated) / len(calibrated),
        "calibrated_minus_raw": sum(c - r for c, r in zip(calibrated, raw, strict=True)) / len(raw),
        "calibrated_minus_reference": sum(c - r for c, r in zip(calibrated, reference, strict=True))
        / len(reference),
        "calibrated_minus_reference_interval": paired_moving_block_interval(
            reference, calibrated, batches
        ),
        "raw": sum(raw) / len(raw),
        "raw_minus_reference": sum(r - v for r, v in zip(raw, reference, strict=True))
        / len(reference),
        "raw_minus_reference_interval": paired_moving_block_interval(reference, raw, batches),
        "reference": sum(reference) / len(reference),
    }


def _admission(
    metrics: dict[str, object], calibration: dict[str, object]
) -> tuple[str, dict[str, object]]:
    joint = cast(dict[str, object], metrics["joint_score_log_loss"])
    checks: dict[str, bool] = {
        "primary_point_delta_at_most_minus_0_01": cast(float, joint["raw_minus_reference"])
        <= -0.01,
        "primary_interval_upper_below_zero": cast(
            Sequence[float], joint["raw_minus_reference_interval"]
        )[1]
        < 0.0,
        "domain_joint_interval_upper_at_most_0_05": cast(
            Sequence[float], joint["raw_minus_reference_interval"]
        )[1]
        <= 0.05,
    }
    limits = {
        "one_x_two_log_loss": 0.02,
        "one_x_two_brier": 0.01,
        "one_x_two_rps": 0.01,
        "total_goal_crps": 0.02,
    }
    for name, limit in limits.items():
        item = cast(dict[str, object], metrics[name])
        checks[f"{name}_interval_upper_at_most_{limit}"] = (
            cast(Sequence[float], item["calibrated_minus_reference_interval"])[1] <= limit
        )
    calibrated = cast(dict[str, dict[str, float]], calibration["calibrated"])
    reference = cast(dict[str, dict[str, float]], calibration["reference"])
    for outcome in ("home", "draw", "away"):
        checks[f"{outcome}_intercept_error_difference_at_most_0_05"] = (
            abs(calibrated[outcome]["intercept"]) - abs(reference[outcome]["intercept"]) <= 0.05
        )
        checks[f"{outcome}_slope_error_difference_at_most_0_1"] = (
            abs(calibrated[outcome]["slope"] - 1.0) - abs(reference[outcome]["slope"] - 1.0) <= 0.1
        )
    passed = all(checks.values())
    return (
        "DEVELOPMENT_ADMITTED_FOR_FUTURE_CONFIRMATION" if passed else "DEVELOPMENT_REJECTED",
        {"all_passed": passed, "checks": checks},
    )


def _coverage(rows: tuple[TransferableTrainingRowV1, ...]) -> dict[str, object]:
    output = []
    for index, row in enumerate(rows):
        role = (
            "FORECASTING_STATE_FIT"
            if index < FORECAST_WARMUP_TARGETS
            else "OOS_CALIBRATION_FIT_ONLY"
            if index < FORECAST_WARMUP_TARGETS + OOS_BLOCK_TARGETS
            else "OOS_HELD_OUT_CALIBRATION_VALIDATION"
        )
        output.append(
            {
                "kickoff_at": row.context.kickoff_at.isoformat(),
                "match_id": str(row.context.match_id),
                "role": role,
            }
        )
    return {"exact_target_count": len(output), "targets": output}


def _oos_manifest(records: tuple[ForecastRecord, ...]) -> dict[str, object]:
    return {
        "contract": "PitchApiCalibrationOosPredictionManifestV1",
        "development_manifest_sha256": DEVELOPMENT_MANIFEST_SHA256,
        "prediction_count": len(records),
        "predictions": [
            {
                "fold": record.fold,
                "kickoff_at": record.calibration.kickoff_at,
                "match_id": record.calibration.match_id,
                "outcome": record.calibration.outcome,
                "probabilities": list(record.calibration.probabilities),
                "role": "CALIBRATION_FIT_ONLY" if record.fold == 1 else "HELD_OUT_VALIDATION",
            }
            for record in records
        ],
        "rows_sha256": rows_sha256(tuple(record.calibration for record in records)),
    }


def _verify_chronology(rows: tuple[TransferableTrainingRowV1, ...]) -> None:
    if (
        tuple(sorted(rows, key=lambda row: (row.context.kickoff_at, str(row.context.match_id))))
        != rows
    ):
        raise RuntimeError("development targets are not chronological")
    for boundary in (72, 108, 144, 180):
        if rows[boundary - 1].context.kickoff_at == rows[boundary].context.kickoff_at:
            raise RuntimeError("chronological block splits a same-kickoff batch")


def _batch_number(rows: tuple[TransferableTrainingRowV1, ...], kickoff: datetime) -> int:
    return len({row.context.kickoff_at for row in rows if row.context.kickoff_at < kickoff})


def write_outputs(payload: dict[str, object], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "artifact": output_dir / "calibration-artifact.json",
        "coverage": output_dir / "development-coverage.json",
        "evidence": output_dir / "development-evidence.json",
        "oos_manifest": output_dir / "oos-prediction-manifest.json",
    }
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        content = canonical_json_bytes(payload[name]) + b"\n"
        path.write_bytes(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root", type=Path, default=Path(".local/pitchapi-snapshot-v1/primary")
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--dependency-lock-sha256", required=True)
    parser.add_argument("--preregistration", type=Path, default=PREREGISTRATION_PATH)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    preregistration_bytes = args.preregistration.read_bytes()
    preregistration = json.loads(preregistration_bytes)
    if preregistration.get("status") != "FROZEN_BEFORE_DEVELOPMENT_FIT":
        raise RuntimeError("calibration successor preregistration is not frozen")
    preregistration_sha256 = hashlib.sha256(preregistration_bytes).hexdigest()
    payload = execute(
        args.snapshot_root,
        source_commit=args.source_commit,
        dependency_lock_sha256=args.dependency_lock_sha256,
        preregistration_sha256=preregistration_sha256,
    )
    hashes = write_outputs(payload, args.output_dir)
    print(json.dumps(hashes, sort_keys=True))


if __name__ == "__main__":
    main()
