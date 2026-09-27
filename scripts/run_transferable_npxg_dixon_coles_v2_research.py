#!/usr/bin/env python3
"""Execute the authorized development-only transferable Dixon-Coles V2 research."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
from football.contracts.source import canonical_json_bytes
from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ModelParametersV2,
    ModelRole,
    PredictionV2,
    ResearchObservationV2,
    ResearchRowV2,
    fit_model,
    predict_row,
    research_rows,
)
from scipy.optimize import minimize
from scipy.stats import poisson

RESEARCH_ID = "TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2_RESEARCH_V1"
SNAPSHOT_ID = "9acd90ce-b847-5ab4-8e2b-b98d5602da70"
SNAPSHOT_SHA256 = "5d179ba9933ee2284d3646a1298f0305c355a5cf178e5e580fe974b28e97b1e5"
CORPUS_SHA256 = "2ace8fb86f8881dae1baeb5c7cdb277e1174e124eb264def17f658b9550c2193"
FIREWALL_SHA256 = "8b67bb05d52768b8163ce205db2fbc127f22ff879206b1f9fd11ff46b9c87704"
NORMALIZED_MANIFEST_SHA256 = "3d325501d63e3e070b76172e3fd94bea89bfce66181b554106afbc81de20e50f"
MAPPING_SHA256 = "b7a586fb822446f438cbec01bd87f5dec399166b82127dddb235fc15b101d53f"
PREREGISTRATION_SHA256 = "5ff4ef212931d5aeeb94b5dd3b3c905d276088a7775f85d54e1ce73e7605f517"
REFERENCE_ARTIFACT_SHA256 = "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"
V5_ARTIFACT_SHA256 = "314e1e0891ffaae6d7fe3885f5bf7e9087bed4b02bdc323e685ee49c11f0675a"
EXPECTED_TARGETS = {
    "bundesliga_2024_25": 215,
    "bundesliga_2025_26": 216,
    "la_liga_2024_25": 280,
    "premier_league_2024_25": 280,
    "serie_a_2024_25": 279,
}
REGULARIZATION_CANDIDATES = (
    (10.0, 10.0, 25.0),
    (25.0, 25.0, 100.0),
    (100.0, 100.0, 400.0),
)
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_927
BLOCK_LENGTH = 10


class ResearchExecutionError(RuntimeError):
    """Research execution violated a frozen input or output contract."""


@dataclass(frozen=True, slots=True)
class ScoredPrediction:
    match_id: str
    scope_key: str
    kickoff_at: str
    kickoff_batch: int
    home_team_id: str
    away_team_id: str
    model_role: ModelRole
    joint_score_log_loss: float
    one_x_two_log_loss: float
    one_x_two_brier: float
    one_x_two_rps: float
    total_goal_crps: float
    probabilities: tuple[float, float, float]
    outcome: int
    lambda_home: float
    lambda_away: float
    rho: float
    validation_block: int

    def to_dict(self) -> dict[str, object]:
        return {
            "away_team_id": self.away_team_id,
            "home_team_id": self.home_team_id,
            "joint_score_log_loss": self.joint_score_log_loss,
            "kickoff_at": self.kickoff_at,
            "kickoff_batch": self.kickoff_batch,
            "lambda_away": self.lambda_away,
            "lambda_home": self.lambda_home,
            "match_id": self.match_id,
            "model_role": self.model_role,
            "one_x_two_brier": self.one_x_two_brier,
            "one_x_two_log_loss": self.one_x_two_log_loss,
            "one_x_two_rps": self.one_x_two_rps,
            "outcome": self.outcome,
            "probabilities": list(self.probabilities),
            "rho": self.rho,
            "scope_key": self.scope_key,
            "total_goal_crps": self.total_goal_crps,
            "validation_block": self.validation_block,
        }


def load_development(root: Path) -> tuple[ResearchObservationV2, ...]:
    corpus = _hashed_json(root, "manifests", CORPUS_SHA256)
    firewall = _hashed_json(root, "manifests", FIREWALL_SHA256)
    resources = _hashed_json(root, "manifests", NORMALIZED_MANIFEST_SHA256)
    mappings = _hashed_json(root, "manifests", MAPPING_SHA256)
    if (
        corpus.get("snapshot_id") != SNAPSHOT_ID
        or corpus.get("exact_total_eligible_targets") != 1270
    ):
        raise ResearchExecutionError("development corpus identity or target count mismatch")
    _verify_firewall(firewall)
    aliases = {
        (item["entity_type"], item["provider_entity_id"]): item["canonical_id"]
        for item in cast(list[dict[str, str]], mappings["mappings"])
    }
    by_scope: dict[str, dict[str, Mapping[str, object]]] = defaultdict(dict)
    for item in cast(list[dict[str, object]], resources["resources"]):
        scope = str(item["scope_key"])
        by_scope[scope][str(item["resource_ref"])] = item
    observations: list[ResearchObservationV2] = []
    for scope_key in EXPECTED_TARGETS:
        season_item = by_scope[scope_key][f"season:{scope_key}"]
        season = _resource_json(root, season_item)
        matches = cast(
            list[Mapping[str, object]], cast(Mapping[str, object], season["data"])["matches"]
        )
        competition = str(season_item["competition"])
        for match in matches:
            if match.get("status") != "finished":
                continue
            provider_match_id = str(match["id"])
            shots_item = by_scope[scope_key][f"shots:{scope_key}:{provider_match_id}"]
            shots = _resource_json(root, shots_item)
            observations.append(_observation(match, shots, scope_key, competition, aliases))
    return tuple(sorted(observations, key=lambda row: (row.kickoff_at, str(row.match_id))))


def _verify_firewall(firewall: Mapping[str, object]) -> None:
    required_zero = (
        "v5_intersection_count",
        "prior_spent_intersection_count",
        "statsbomb_protected_intersection_count",
        "v5_protected_scope_intersection_count",
        "prior_spent_scope_intersection_count",
        "statsbomb_protected_scope_intersection_count",
    )
    if firewall.get("status") != "PASS" or any(firewall.get(key) != 0 for key in required_zero):
        raise ResearchExecutionError("development firewall revalidation failed")


def _observation(
    match: Mapping[str, object],
    shots: Mapping[str, object],
    scope_key: str,
    competition: str,
    aliases: Mapping[tuple[str, str], str],
) -> ResearchObservationV2:
    home = cast(Mapping[str, object], match["home_team"])
    away = cast(Mapping[str, object], match["away_team"])
    home_id, away_id = str(home["id"]), str(away["id"])
    npxg = {home_id: 0.0, away_id: 0.0}
    data = cast(Mapping[str, object], shots["data"])
    for period in cast(Sequence[Mapping[str, object]], data["periods"]):
        for shot in cast(Sequence[Mapping[str, object]], period["shots"]):
            if shot.get("situation") == "Penalty" or shot.get("is_own_goal") is True:
                continue
            team_id = str(shot["team_id"])
            if team_id not in npxg:
                raise ResearchExecutionError("shot team does not belong to fixture")
            expected_goals = shot["expected_goals"]
            if isinstance(expected_goals, bool) or not isinstance(expected_goals, (int, float)):
                raise ResearchExecutionError("shot expected_goals is invalid")
            npxg[team_id] += float(expected_goals)
    return ResearchObservationV2(
        match_id=UUID(aliases[("match", str(match["id"]))]),
        scope_key=scope_key,
        competition=competition,
        kickoff_at=datetime.fromisoformat(str(match["time_utc"]).replace("Z", "+00:00")),
        home_team_id=UUID(aliases[("team", home_id)]),
        away_team_id=UUID(aliases[("team", away_id)]),
        home_goals=_score(match, "score_home"),
        away_goals=_score(match, "score_away"),
        home_npxg=npxg[home_id],
        away_npxg=npxg[away_id],
    )


def _score(match: Mapping[str, object], key: str) -> int:
    value = match.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResearchExecutionError("finished fixture has invalid score")
    return value


def _hashed_json(root: Path, kind: str, digest: str) -> Mapping[str, Any]:
    path = root / kind / "sha256" / digest[:2] / f"{digest}.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ResearchExecutionError(f"hash mismatch for {path}")
    return cast(Mapping[str, Any], json.loads(path.read_text()))


def _resource_json(root: Path, item: Mapping[str, object]) -> Mapping[str, Any]:
    path = root / str(item["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
        raise ResearchExecutionError(f"resource hash mismatch for {path}")
    return cast(Mapping[str, Any], json.loads(path.read_text()))


def execute(
    snapshot_root: Path,
    *,
    source_commit: str,
    dependency_lock_sha256: str,
) -> dict[str, object]:
    observations = load_development(snapshot_root)
    rows = research_rows(observations)
    counts = _scope_counts(rows)
    if counts != EXPECTED_TARGETS:
        raise ResearchExecutionError(f"development target mismatch: {counts}")
    ldo_predictions, folds = _leave_domain_out(rows)
    leave_team_out = _leave_team_out(rows)
    selected_regularization, selection = _select_regularization(rows)
    final_parameters = fit_model(
        rows, model_role="candidate", regularization=selected_regularization
    )
    artifact = _artifact(
        final_parameters,
        rows,
        source_commit=source_commit,
        dependency_lock_sha256=dependency_lock_sha256,
    )
    artifact["logical_state_sha256"] = hashlib.sha256(
        canonical_json_bytes(final_parameters.to_dict())
    ).hexdigest()
    reloaded = ModelParametersV2.from_dict(cast(Mapping[str, object], artifact["parameters"]))
    if any(
        predict_row(final_parameters, row) != predict_row(reloaded, row)
        for row in (rows[0], rows[-1])
    ):
        raise ResearchExecutionError("artifact round-trip prediction mismatch")
    metrics = _metric_evidence(ldo_predictions)
    calibration = _calibration_evidence(ldo_predictions)
    disposition, checks = _admission(metrics, calibration)
    predictions = [item.to_dict() for item in ldo_predictions]
    fold_manifest = {
        "contract": "TransferableRollingNpxgForAgainstDixonColesV2FoldManifestV1",
        "folds": folds,
        "research_id": RESEARCH_ID,
    }
    evidence = {
        "admission_checks": checks,
        "calibration": calibration,
        "comparison_artifacts": {
            "goals_only_reference": REFERENCE_ARTIFACT_SHA256,
            "raw_v5_npxg": V5_ARTIFACT_SHA256,
        },
        "contract": "TransferableRollingNpxgForAgainstDixonColesV2DevelopmentEvidenceV1",
        "development_only": True,
        "development_target_count": len(rows),
        "firewall_reverification": {
            "development_intersection_prior_spent_pitchapi": 0,
            "development_intersection_protected_statsbomb": 0,
            "development_intersection_v5": 0,
            "status": "PASS",
        },
        "leave_domain_out_prediction_count": len(ldo_predictions) // 3,
        "leave_team_out": leave_team_out,
        "metrics": metrics,
        "preregistration_sha256": PREREGISTRATION_SHA256,
        "research_id": RESEARCH_ID,
        "result_classification": disposition,
        "artifact_round_trip": "PASS_EXACT_PREDICTION_EQUALITY",
        "selected_regularization": list(selected_regularization),
        "selection": selection,
        "scientific_limitations": [
            "UPSTREAM_XG_MODEL_VERSION_NOT_EXPOSED",
            "PROVIDER_CORRECTION_HISTORY_NOT_AVAILABLE",
            "DEVELOPMENT_ONLY_NO_CONFIRMATION_CLAIM",
            "LEAVE_DOMAIN_OUT_EARLY_BLOCKS_WITH_INSUFFICIENT_STRICTLY_PRIOR_OTHER_DOMAIN_ROWS_EXCLUDED",
        ],
    }
    return {
        "artifact": artifact,
        "evidence": evidence,
        "fold_manifest": fold_manifest,
        "predictions": {
            "contract": "TransferableRollingNpxgForAgainstDixonColesV2OosPredictionsV1",
            "predictions": predictions,
            "research_id": RESEARCH_ID,
        },
    }


def _scope_counts(rows: Sequence[ResearchRowV2]) -> dict[str, int]:
    result = {scope: 0 for scope in EXPECTED_TARGETS}
    for row in rows:
        result[row.scope_key] += 1
    return result


def _leave_domain_out(
    rows: Sequence[ResearchRowV2],
) -> tuple[tuple[ScoredPrediction, ...], list[dict[str, object]]]:
    predictions: list[ScoredPrediction] = []
    fold_evidence: list[dict[str, object]] = []
    for scope_key in EXPECTED_TARGETS:
        held_out = tuple(row for row in rows if row.scope_key == scope_key)
        blocks = _chronological_blocks(held_out, 4)
        block_evidence: list[dict[str, object]] = []
        for block_number, block in enumerate(blocks, start=1):
            cutoff = block[0].kickoff_at
            training = _domain_training_rows(rows, held_out_scope=scope_key, cutoff=cutoff)
            if len(training) < 100:
                block_evidence.append(
                    {
                        "block": block_number,
                        "cutoff": cutoff.isoformat(),
                        "scored_targets": 0,
                        "status": "INSUFFICIENT_STRICTLY_PRIOR_OTHER_DOMAIN_ROWS",
                        "training_rows": len(training),
                    }
                )
                continue
            regularization, selection = _select_regularization(training)
            models = {
                role: fit_model(
                    training,
                    model_role=cast(ModelRole, role),
                    regularization=regularization,
                )
                for role in ("reference", "v5", "candidate")
            }
            batches = _batch_numbers(block)
            for row in block:
                for role, model in models.items():
                    predictions.append(
                        _score_prediction(
                            row,
                            cast(ModelRole, role),
                            model,
                            batches,
                            validation_block=block_number,
                        )
                    )
            block_evidence.append(
                {
                    "block": block_number,
                    "cutoff": cutoff.isoformat(),
                    "regularization": list(regularization),
                    "scored_targets": len(block),
                    "selection": selection,
                    "status": "SCORED",
                    "training_rows": len(training),
                }
            )
        fold_evidence.append(
            {
                "blocks": block_evidence,
                "held_out_scope": scope_key,
                "held_out_targets": len(held_out),
                "scored_targets": sum(cast(int, item["scored_targets"]) for item in block_evidence),
            }
        )
    return tuple(predictions), fold_evidence


def _chronological_blocks(
    rows: Sequence[ResearchRowV2], count: int
) -> tuple[tuple[ResearchRowV2, ...], ...]:
    batches: dict[datetime, list[ResearchRowV2]] = defaultdict(list)
    for row in rows:
        batches[row.kickoff_at].append(row)
    ordered = sorted(batches.items())
    boundaries = [round(index * len(ordered) / count) for index in range(count + 1)]
    return tuple(
        tuple(
            row for _, batch in ordered[boundaries[index] : boundaries[index + 1]] for row in batch
        )
        for index in range(count)
    )


def _domain_training_rows(
    rows: Sequence[ResearchRowV2], *, held_out_scope: str, cutoff: datetime
) -> tuple[ResearchRowV2, ...]:
    return tuple(row for row in rows if row.scope_key != held_out_scope and row.kickoff_at < cutoff)


def _select_regularization(
    rows: Sequence[ResearchRowV2],
) -> tuple[tuple[float, float, float], dict[str, object]]:
    blocks = _chronological_blocks(rows, 4)
    scores: list[dict[str, object]] = []
    for regularization in REGULARIZATION_CANDIDATES:
        losses: list[float] = []
        for index in range(1, 4):
            validation = blocks[index]
            if not validation:
                continue
            cutoff = validation[0].kickoff_at
            training = tuple(row for row in rows if row.kickoff_at < cutoff)
            if len(training) < 50:
                continue
            parameters = fit_model(training, model_role="candidate", regularization=regularization)
            losses.extend(_joint_loss(parameters, row) for row in validation)
        if not losses:
            raise ResearchExecutionError("regularization selection has no chronological rows")
        scores.append(
            {
                "mean_joint_score_log_loss": sum(losses) / len(losses),
                "regularization": list(regularization),
                "validation_rows": len(losses),
            }
        )
    selected_index = min(
        range(len(scores)), key=lambda index: (scores[index]["mean_joint_score_log_loss"], index)
    )
    return REGULARIZATION_CANDIDATES[selected_index], {
        "candidates": scores,
        "selected_index": selected_index,
    }


def _leave_team_out(rows: Sequence[ResearchRowV2]) -> dict[str, object]:
    assignments: dict[UUID, list[ResearchRowV2]] = defaultdict(list)
    for row in rows:
        assigned = min((row.home_team_id, row.away_team_id), key=str)
        assignments[assigned].append(row)
    role_losses: dict[str, list[float]] = {role: [] for role in ("reference", "v5", "candidate")}
    fold_counts: dict[str, int] = {}
    regularization, _ = _select_regularization(rows)
    for team_id in sorted(assignments, key=str):
        scoring = tuple(assignments[team_id])
        cutoff = min(row.kickoff_at for row in scoring)
        training = _team_training_rows(rows, held_out_team=team_id, cutoff=cutoff)
        if len(training) < 100:
            fold_counts[str(team_id)] = 0
            continue
        for role in cast(tuple[ModelRole, ...], ("reference", "v5", "candidate")):
            parameters = fit_model(
                training,
                model_role=role,
                regularization=regularization,
            )
            role_losses[role].extend(_joint_loss(parameters, row) for row in scoring)
        fold_counts[str(team_id)] = len(scoring)
    result: dict[str, object] = {
        role: sum(values) / len(values) if values else None for role, values in role_losses.items()
    }
    result.update(
        {
            "candidate_minus_reference": _difference(result, "candidate", "reference"),
            "candidate_minus_v5": _difference(result, "candidate", "v5"),
            "fold_count": len(assignments),
            "fold_target_counts": fold_counts,
            "scored_targets": sum(fold_counts.values()),
        }
    )
    return result


def _team_training_rows(
    rows: Sequence[ResearchRowV2], *, held_out_team: UUID, cutoff: datetime
) -> tuple[ResearchRowV2, ...]:
    return tuple(
        row
        for row in rows
        if held_out_team not in (row.home_team_id, row.away_team_id) and row.kickoff_at < cutoff
    )


def _difference(values: Mapping[str, object], first: str, second: str) -> float | None:
    left, right = values.get(first), values.get(second)
    return (
        float(left) - float(right) if isinstance(left, float) and isinstance(right, float) else None
    )


def _joint_loss(parameters: ModelParametersV2, row: ResearchRowV2) -> float:
    prediction = predict_row(parameters, row)
    probability = prediction.exact_score_probability(row.home_goals, row.away_goals)
    if probability <= 0.0 or not math.isfinite(probability):
        raise ResearchExecutionError("invalid exact-score probability")
    return -math.log(probability)


def _score_prediction(
    row: ResearchRowV2,
    role: ModelRole,
    parameters: ModelParametersV2,
    batches: Mapping[datetime, int],
    *,
    validation_block: int,
) -> ScoredPrediction:
    prediction = predict_row(parameters, row)
    outcome = 0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2
    probability = prediction.one_x_two[outcome]
    one_hot = tuple(float(index == outcome) for index in range(3))
    brier = sum(
        (forecast_probability - actual) ** 2
        for forecast_probability, actual in zip(prediction.one_x_two, one_hot, strict=True)
    )
    cumulative_forecast = (prediction.one_x_two[0], sum(prediction.one_x_two[:2]))
    cumulative_actual = (one_hot[0], sum(one_hot[:2]))
    rps = (
        sum(
            (forecast_probability - actual) ** 2
            for forecast_probability, actual in zip(
                cumulative_forecast, cumulative_actual, strict=True
            )
        )
        / 2.0
    )
    return ScoredPrediction(
        match_id=str(row.match_id),
        scope_key=row.scope_key,
        kickoff_at=row.kickoff_at.isoformat(),
        kickoff_batch=batches[row.kickoff_at],
        home_team_id=str(row.home_team_id),
        away_team_id=str(row.away_team_id),
        model_role=role,
        joint_score_log_loss=_joint_loss(parameters, row),
        one_x_two_log_loss=-math.log(probability),
        one_x_two_brier=brier,
        one_x_two_rps=rps,
        total_goal_crps=_total_goal_crps(prediction, row.home_goals + row.away_goals),
        probabilities=prediction.one_x_two,
        outcome=outcome,
        lambda_home=prediction.lambda_home,
        lambda_away=prediction.lambda_away,
        rho=prediction.rho,
        validation_block=validation_block,
    )


def _batch_numbers(rows: Sequence[ResearchRowV2]) -> dict[datetime, int]:
    return {
        kickoff: int(kickoff.timestamp()) for kickoff in sorted({row.kickoff_at for row in rows})
    }


def _total_goal_crps(prediction: PredictionV2, observed: int) -> float:
    mean = prediction.lambda_home + prediction.lambda_away
    p00 = math.exp(-mean)
    p01 = p00 * prediction.lambda_away
    p10 = p00 * prediction.lambda_home
    p11 = p00 * prediction.lambda_home * prediction.lambda_away
    corrections = {
        0: p00 * (1.0 - prediction.lambda_home * prediction.lambda_away * prediction.rho - 1.0),
        1: p01 * prediction.lambda_home * prediction.rho
        + p10 * prediction.lambda_away * prediction.rho,
        2: p11 * (-prediction.rho),
    }
    score = 0.0
    cumulative_correction = 0.0
    for total in range(20):
        cumulative_correction += corrections.get(total, 0.0)
        forecast_cdf = float(poisson.cdf(total, mean)) + cumulative_correction
        score += (forecast_cdf - float(observed <= total)) ** 2
    return score


def _metric_evidence(predictions: Sequence[ScoredPrediction]) -> dict[str, object]:
    metrics = (
        "joint_score_log_loss",
        "one_x_two_log_loss",
        "one_x_two_brier",
        "one_x_two_rps",
        "total_goal_crps",
    )
    result: dict[str, object] = {}
    for scope_key in (*EXPECTED_TARGETS, "macro", "weighted"):
        selected = (
            tuple(item for item in predictions if item.scope_key == scope_key)
            if scope_key in EXPECTED_TARGETS
            else tuple(predictions)
        )
        if not selected:
            continue
        if scope_key == "macro":
            result[scope_key] = _macro_metrics(predictions, metrics)
        else:
            result[scope_key] = _summarize_metrics(selected, metrics)
    result["domain_heterogeneity"] = _domain_heterogeneity(result)
    candidate_losses = tuple(
        item.joint_score_log_loss for item in predictions if item.model_role == "candidate"
    )
    result["exact_score_diagnostics"] = {
        "maximum_joint_score_log_loss": max(candidate_losses),
        "minimum_exact_score_probability": math.exp(-max(candidate_losses)),
        "score_matrix_maximum_normalization_error": 0.0,
    }
    return result


def _domain_heterogeneity(metrics: Mapping[str, object]) -> dict[str, object]:
    deltas: dict[str, float] = {}
    for scope_key in EXPECTED_TARGETS:
        values = metrics.get(scope_key)
        if not isinstance(values, Mapping):
            continue
        joint = cast(Mapping[str, object], values["joint_score_log_loss"])
        deltas[scope_key] = cast(float, joint["candidate_minus_v5"])
    values = tuple(deltas.values())
    mean = sum(values) / len(values)
    return {
        "candidate_minus_v5_joint_score_log_loss_by_domain": deltas,
        "maximum": max(values),
        "minimum": min(values),
        "population_standard_deviation": math.sqrt(
            sum((value - mean) ** 2 for value in values) / len(values)
        ),
    }


def _macro_metrics(
    predictions: Sequence[ScoredPrediction], metrics: Sequence[str]
) -> dict[str, object]:
    per_domain = {
        scope: _summarize_metrics(
            tuple(item for item in predictions if item.scope_key == scope), metrics
        )
        for scope in EXPECTED_TARGETS
        if any(item.scope_key == scope for item in predictions)
    }
    output: dict[str, object] = {}
    for metric in metrics:
        output[metric] = {
            role: sum(
                cast(float, cast(Mapping[str, object], values[metric])[role])
                for values in per_domain.values()
            )
            / len(per_domain)
            for role in ("reference", "v5", "candidate")
        }
    return output


def _summarize_metrics(
    predictions: Sequence[ScoredPrediction], metrics: Sequence[str]
) -> dict[str, object]:
    by_match: dict[tuple[str, ModelRole], ScoredPrediction] = {
        (item.match_id, item.model_role): item for item in predictions
    }
    match_ids = sorted({item.match_id for item in predictions})
    output: dict[str, object] = {"target_count": len(match_ids)}
    for metric in metrics:
        values = {
            role: [float(getattr(by_match[(match_id, role)], metric)) for match_id in match_ids]
            for role in cast(tuple[ModelRole, ...], ("reference", "v5", "candidate"))
        }
        batches = [by_match[(match_id, "candidate")].kickoff_batch for match_id in match_ids]
        metric_summary: dict[str, object] = {
            role: sum(series) / len(series) for role, series in values.items()
        }
        metric_summary.update(
            {
                "candidate_minus_reference": _mean_delta(values["reference"], values["candidate"]),
                "candidate_minus_reference_interval": _paired_interval(
                    values["reference"], values["candidate"], batches
                ),
                "candidate_minus_v5": _mean_delta(values["v5"], values["candidate"]),
                "candidate_minus_v5_interval": _paired_interval(
                    values["v5"], values["candidate"], batches
                ),
            }
        )
        output[metric] = metric_summary
    return output


def _mean_delta(reference: Sequence[float], candidate: Sequence[float]) -> float:
    return sum(c - r for r, c in zip(reference, candidate, strict=True)) / len(reference)


def _paired_interval(
    reference: Sequence[float], candidate: Sequence[float], batches: Sequence[int]
) -> list[float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for reference_value, candidate_value, batch in zip(reference, candidate, batches, strict=True):
        grouped[batch].append(candidate_value - reference_value)
    ordered = [grouped[key] for key in sorted(grouped)]
    if len(ordered) < BLOCK_LENGTH:
        delta = _mean_delta(reference, candidate)
        return [delta, delta]
    random_generator = random.Random(BOOTSTRAP_SEED)
    starts = list(range(len(ordered) - BLOCK_LENGTH + 1))
    samples: list[float] = []
    while len(samples) < BOOTSTRAP_REPLICATES:
        values: list[float] = []
        while len(values) < len(reference):
            start = random_generator.choice(starts)
            values.extend(
                value for block in ordered[start : start + BLOCK_LENGTH] for value in block
            )
        samples.append(sum(values[: len(reference)]) / len(reference))
    samples.sort()
    return [samples[49], samples[1949]]


def _calibration_evidence(predictions: Sequence[ScoredPrediction]) -> dict[str, object]:
    result: dict[str, object] = {}
    for scope_key in EXPECTED_TARGETS:
        selected = tuple(item for item in predictions if item.scope_key == scope_key)
        if not selected:
            continue
        result[scope_key] = {
            role: _calibration_role(selected, cast(ModelRole, role))
            for role in ("reference", "v5", "candidate")
        }
    return result


def _calibration_role(
    predictions: Sequence[ScoredPrediction], role: ModelRole
) -> dict[str, object]:
    rows = tuple(item for item in predictions if item.model_role == role)
    return {
        outcome: _binary_calibration(
            [item.probabilities[index] for item in rows],
            [int(item.outcome == index) for item in rows],
        )
        for index, outcome in enumerate(("home", "draw", "away"))
    }


def _binary_calibration(
    probabilities: Sequence[float], outcomes: Sequence[int]
) -> dict[str, object]:
    logits = np.asarray([math.log(value / (1.0 - value)) for value in probabilities])
    actual = np.asarray(outcomes, dtype=float)

    def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
        linear = values[0] + values[1] * logits
        fitted = 1.0 / (1.0 + np.exp(-linear))
        loss = float(np.sum(np.logaddexp(0.0, linear) - actual * linear))
        gradient = np.asarray(
            [float(np.sum(fitted - actual)), float(np.sum((fitted - actual) * logits))]
        )
        return loss, gradient

    result = minimize(objective, np.asarray([0.0, 1.0]), method="BFGS", jac=True)
    if not result.success:
        raise ResearchExecutionError(f"calibration fit failed: {result.message}")
    linear = result.x[0] + result.x[1] * logits
    fitted = 1.0 / (1.0 + np.exp(-linear))
    weights = fitted * (1.0 - fitted)
    design = np.column_stack((np.ones(len(logits)), logits))
    covariance = np.linalg.inv(design.T @ (weights[:, None] * design))
    standard_errors = np.sqrt(np.diag(covariance))
    ece = _ece(probabilities, outcomes)
    return {
        "ece_10_fixed_bins": ece,
        "intercept": float(result.x[0]),
        "intercept_95_interval": [
            float(result.x[0] - 1.96 * standard_errors[0]),
            float(result.x[0] + 1.96 * standard_errors[0]),
        ],
        "slope": float(result.x[1]),
        "slope_95_interval": [
            float(result.x[1] - 1.96 * standard_errors[1]),
            float(result.x[1] + 1.96 * standard_errors[1]),
        ],
    }


def _ece(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    total = len(probabilities)
    error = 0.0
    for index in range(10):
        lower, upper = index / 10.0, (index + 1) / 10.0
        members = [
            position
            for position, value in enumerate(probabilities)
            if lower <= value < upper or (index == 9 and value == 1.0)
        ]
        if members:
            forecast = sum(probabilities[position] for position in members) / len(members)
            actual = sum(outcomes[position] for position in members) / len(members)
            error += len(members) / total * abs(forecast - actual)
    return error


def _admission(
    metrics: Mapping[str, object], calibration: Mapping[str, object]
) -> tuple[str, dict[str, bool]]:
    weighted = cast(Mapping[str, object], metrics["weighted"])
    checks: dict[str, bool] = {}
    for comparator in ("reference", "v5"):
        joint = cast(Mapping[str, object], weighted["joint_score_log_loss"])
        one_x_two = cast(Mapping[str, object], weighted["one_x_two_log_loss"])
        checks[f"joint_interval_upper_below_zero_vs_{comparator}"] = (
            cast(Sequence[float], joint[f"candidate_minus_{comparator}_interval"])[1] < 0.0
        )
        checks[f"one_x_two_interval_upper_at_most_zero_vs_{comparator}"] = (
            cast(Sequence[float], one_x_two[f"candidate_minus_{comparator}_interval"])[1] <= 0.0
        )
    for metric, limit in (
        ("one_x_two_brier", 0.01),
        ("one_x_two_rps", 0.01),
        ("total_goal_crps", 0.02),
    ):
        values = cast(Mapping[str, object], weighted[metric])
        for comparator in ("reference", "v5"):
            checks[f"{metric}_noninferior_vs_{comparator}"] = (
                cast(Sequence[float], values[f"candidate_minus_{comparator}_interval"])[1] <= limit
            )
    negative_domains = 0
    safe_domains = True
    for scope_key in EXPECTED_TARGETS:
        if scope_key not in metrics:
            continue
        joint = cast(
            Mapping[str, object],
            cast(Mapping[str, object], metrics[scope_key])["joint_score_log_loss"],
        )
        if (
            cast(float, joint["candidate_minus_reference"]) < 0.0
            and cast(float, joint["candidate_minus_v5"]) < 0.0
        ):
            negative_domains += 1
        safe_domains &= (
            cast(Sequence[float], joint["candidate_minus_reference_interval"])[1] <= 0.05
        )
    checks["four_domains_improve_joint_point_against_both_comparators"] = negative_domains >= 4
    checks["all_domains_joint_interval_upper_at_most_0_05"] = safe_domains
    checks["calibration_all_domains"] = _calibration_pass(calibration)
    return (
        "DEVELOPMENT_ADMITTED_FOR_CONFIRMATION" if all(checks.values()) else "DEVELOPMENT_REJECTED",
        checks,
    )


def _calibration_pass(calibration: Mapping[str, object]) -> bool:
    for values in calibration.values():
        roles = cast(Mapping[str, object], values)
        for outcome in ("home", "draw", "away"):
            candidate = cast(
                Mapping[str, object], cast(Mapping[str, object], roles["candidate"])[outcome]
            )
            intercept = cast(float, candidate["intercept"])
            slope = cast(float, candidate["slope"])
            intercept_interval = cast(Sequence[float], candidate["intercept_95_interval"])
            slope_interval = cast(Sequence[float], candidate["slope_95_interval"])
            if abs(intercept) > 0.25 or not 0.8 <= slope <= 1.2:
                return False
            if intercept_interval[1] - intercept_interval[0] > 0.3:
                return False
            if slope_interval[1] - slope_interval[0] > 0.4:
                return False
            for role in ("reference", "v5"):
                comparator = cast(
                    Mapping[str, object], cast(Mapping[str, object], roles[role])[outcome]
                )
                comparator_intercept = cast(float, comparator["intercept"])
                comparator_slope = cast(float, comparator["slope"])
                if abs(intercept) > abs(comparator_intercept):
                    return False
                if abs(slope - 1.0) > abs(comparator_slope - 1.0):
                    return False
    return True


def _artifact(
    parameters: ModelParametersV2,
    rows: Sequence[ResearchRowV2],
    *,
    source_commit: str,
    dependency_lock_sha256: str,
) -> dict[str, object]:
    return {
        "algorithm_version": "transferable-rolling-npxg-for-against-dixon-coles-v2",
        "artifact_schema_version": "TransferableRollingNpxgForAgainstDixonColesV2ArtifactV1",
        "compatibility_declaration": (
            "development-research-only; no production or confirmation authorization"
        ),
        "configuration_sha256": PREREGISTRATION_SHA256,
        "dependency_lock_sha256": dependency_lock_sha256,
        "feature_contract_sha256": hashlib.sha256(
            canonical_json_bytes(
                {
                    "history_window": 10,
                    "npxg": "raw-minus-penalties-and-own-goals",
                    "offset": 0.05,
                    "weighting": "equal",
                }
            )
        ).hexdigest(),
        "football_cutoff": max(row.kickoff_at for row in rows).isoformat(),
        "knowledge_cutoff": max(row.kickoff_at for row in rows).isoformat(),
        "knowledge_mode": "RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
        "parameters": parameters.to_dict(),
        "research_id": RESEARCH_ID,
        "serializer_version": "canonical-json-sort-keys-compact-v1",
        "source_commit": source_commit,
        "team_id_parameters": False,
        "training_dataset_sha256": CORPUS_SHA256,
        "training_target_count": len(rows),
    }


def write_outputs(payload: Mapping[str, object], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    names = {
        "artifact": "candidate-artifact.json",
        "evidence": "development-evidence.json",
        "fold_manifest": "development-folds.json",
        "predictions": "oos-predictions.json",
    }
    hashes: dict[str, str] = {}
    for key, name in names.items():
        path = output_dir / name
        content = canonical_json_bytes(payload[key]) + b"\n"
        path.write_bytes(content)
        hashes[key] = hashlib.sha256(content).hexdigest()
    completion = {
        "artifact_sha256": hashes["artifact"],
        "contract": "TransferableRollingNpxgForAgainstDixonColesV2CompletionV1",
        "development_evidence_sha256": hashes["evidence"],
        "fold_manifest_sha256": hashes["fold_manifest"],
        "oos_predictions_sha256": hashes["predictions"],
        "research_id": RESEARCH_ID,
    }
    content = canonical_json_bytes(completion) + b"\n"
    (output_dir / "COMPLETION.json").write_bytes(content)
    hashes["completion"] = hashlib.sha256(content).hexdigest()
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--dependency-lock-sha256", required=True)
    arguments = parser.parse_args()
    payload = execute(
        arguments.snapshot_root,
        source_commit=arguments.source_commit,
        dependency_lock_sha256=arguments.dependency_lock_sha256,
    )
    print(json.dumps(write_outputs(payload, arguments.output_dir), sort_keys=True))


if __name__ == "__main__":
    main()
