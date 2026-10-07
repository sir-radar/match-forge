"""Development-only residualized H2H prequential evaluation."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from football.forecasting.h2h_residual import (
    ContextualGoalAdjustmentV1,
    H2HMeeting,
    H2HResidualStatus,
    H2HResidualV1,
    H2HTarget,
    SecondaryMatchupPriorV1,
)
from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ModelParametersV2,
    PredictionV2,
    ResearchObservationV2,
    ResearchRowV2,
    fit_model,
    predict_row,
    research_rows,
)

RESEARCH_ID = "MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1"
SNAPSHOT_NAME = "MATCHFORGE_H2H_DEVELOPMENT_HISTORY_QUALIFIED_V1"
SNAPSHOT_ID = "fcb43dd0-5910-55c0-8922-4c1c1e77246a"
SNAPSHOT_SHA256 = "be0b5fb6a0dcc097649d5bfd413cda59b3cafcaaa3188c80fa63f2c13c1e9352"
HISTORY_MANIFEST_SHA256 = "90f9e5343aa1e07ccc2df721d39e4deaee99295615046f806cdadda101c656c4"
FIREWALL_MANIFEST_SHA256 = "67ddb78e950de95058e8f278087afe44ceafa53455f5f600a6793d41448ef22c"
MAPPING_MANIFEST_SHA256 = "fa05ab357f3742871e2cedd904471c0e52f87951b27a795c601a42f352eccfa7"
COMPLETENESS_MANIFEST_SHA256 = "1b34e922b6076e346252509ca6dc60abc254644c34d191184755729211022d8c"
TARGET_FIREWALL_SHA256 = "8b67bb05d52768b8163ce205db2fbc127f22ff879206b1f9fd11ff46b9c87704"
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20_260_921
BLOCK_LENGTH = 10
MINIMUM_H2H_TRAINING_TARGETS = 100
BASELINE_REFIT_INTERVAL = 100
BASELINE_REGULARIZATION = (25.0, 25.0, 100.0)
METRICS = (
    "joint_score_log_loss",
    "one_x_two_log_loss",
    "one_x_two_brier",
    "one_x_two_rps",
    "total_goal_crps",
)


class H2HResearchError(RuntimeError):
    """The frozen H2H research protocol cannot continue."""


@dataclass(frozen=True, slots=True)
class TargetForecast:
    row: ResearchRowV2
    feature: SecondaryMatchupPriorV1
    lambda_home: float
    lambda_away: float


@dataclass(frozen=True, slots=True)
class ScoredTarget:
    fixture_id: str
    competition: str
    scope_key: str
    kickoff_at: str
    kickoff_batch: int
    beta_h2h: float
    feature: SecondaryMatchupPriorV1
    baseline: Mapping[str, float]
    candidate: Mapping[str, float]
    baseline_probabilities: tuple[float, float, float]
    candidate_probabilities: tuple[float, float, float]
    outcome: int


def verify_firewall(payload: Mapping[str, object]) -> None:
    nested = payload.get("intersections")
    if nested is not None:
        if not isinstance(nested, Mapping):
            raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")
        counts = list(nested.values())
    else:
        counts = [
            value for key, value in payload.items() if "intersection" in str(key)
        ]
    if payload.get("status") != "PASS":
        raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")
    if not counts or any(value != 0 for value in counts):
        raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")


def kickoff_batches(rows: Sequence[ResearchRowV2]) -> tuple[tuple[ResearchRowV2, ...], ...]:
    ordered = sorted(rows, key=lambda row: (row.kickoff_at, str(row.match_id)))
    grouped: list[list[ResearchRowV2]] = []
    for row in ordered:
        if not grouped or grouped[-1][0].kickoff_at != row.kickoff_at:
            grouped.append([])
        grouped[-1].append(row)
    return tuple(tuple(batch) for batch in grouped)


def independent_poisson_prediction(lambda_home: float, lambda_away: float) -> PredictionV2:
    if any(not math.isfinite(value) or value <= 0.0 for value in (lambda_home, lambda_away)):
        raise H2HResearchError("invalid goal rate")
    home = [float(poisson.pmf(value, lambda_home)) for value in range(10)]
    away = [float(poisson.pmf(value, lambda_away)) for value in range(10)]
    home.append(1.0 - sum(home))
    away.append(1.0 - sum(away))
    matrix = tuple(tuple(x * y for y in away) for x in home)
    total = sum(sum(row) for row in matrix)
    if abs(total - 1.0) > 1e-12 or any(value < 0.0 for row in matrix for value in row):
        raise H2HResearchError("invalid score distribution")
    home_win = sum(matrix[x][y] for x in range(11) for y in range(11) if x > y)
    draw = sum(matrix[x][x] for x in range(11))
    away_win = 1.0 - home_win - draw
    return PredictionV2(lambda_home, lambda_away, 0.0, matrix, (home_win, draw, away_win))


def fit_beta(rows: Sequence[TargetForecast]) -> float:
    if len(rows) < MINIMUM_H2H_TRAINING_TARGETS:
        raise H2HResearchError("MODEL_FIT_UNAVAILABLE")

    def objective(values: np.ndarray) -> tuple[float, np.ndarray]:
        beta = float(values[0])
        loss = 0.0
        gradient = 0.0
        for item in rows:
            prior = item.feature.secondary_matchup_prior
            home = item.lambda_home * math.exp(beta * prior)
            away = item.lambda_away * math.exp(-beta * prior)
            loss += (
                home - item.row.home_goals * math.log(home) + math.lgamma(item.row.home_goals + 1)
            )
            loss += (
                away - item.row.away_goals * math.log(away) + math.lgamma(item.row.away_goals + 1)
            )
            gradient += prior * (home - item.row.home_goals - away + item.row.away_goals)
        return loss / len(rows), np.asarray([gradient / len(rows)])

    result = minimize(
        objective,
        np.asarray([0.05]),
        method="L-BFGS-B",
        jac=True,
        bounds=((0.0, 0.25),),
    )
    if not result.success or not math.isfinite(float(result.fun)):
        raise H2HResearchError("MODEL_FIT_UNAVAILABLE")
    return float(result.x[0])


def execute(
    *,
    snapshot_root: Path,
    target_root: Path,
    snapshot_result_path: Path,
    source_commit: str,
) -> dict[str, object]:
    from scripts.run_transferable_npxg_dixon_coles_v2_research import load_development

    primary = snapshot_root / "primary"
    snapshot_result = _json_file(snapshot_result_path)
    _verify_snapshot(snapshot_result, primary)
    verify_firewall(_hashed_json(primary, "manifests", FIREWALL_MANIFEST_SHA256))
    verify_firewall(_hashed_json(target_root, "manifests", TARGET_FIREWALL_SHA256))
    target_observations = load_development(target_root)
    target_rows = research_rows(target_observations)
    if len(target_rows) != 1_270:
        raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")
    history_payload = _hashed_json(primary, "manifests", HISTORY_MANIFEST_SHA256)
    history_observations = tuple(
        _history_observation(item)
        for item in cast(Sequence[Mapping[str, object]], history_payload["matches"])
    )
    history_rows = research_rows(history_observations)
    all_rows = _unique_rows((*history_rows, *target_rows))
    baseline_by_fixture = _prequential_baselines(all_rows)
    incomplete_pair = _incomplete_pair(primary)
    all_observations = (*history_observations, *target_observations)
    meetings = _meetings(all_observations, baseline_by_fixture, incomplete_pair)
    targets = _target_forecasts(target_rows, baseline_by_fixture, meetings)
    scored, warmup_count, beta_values = _prequential_score(targets)
    if not scored:
        return _deferred_result(source_commit, targets, warmup_count)
    metrics = _metric_evidence(scored)
    calibration = _calibration_evidence(scored)
    checks = _gate_checks(metrics, calibration)
    disposition = (
        "DEVELOPMENT_ACCEPTED_FOR_CONFIRMATION" if all(checks.values()) else "DEVELOPMENT_REJECTED"
    )
    coverage = _coverage(targets)
    return {
        "contract": "MatchForgeH2HIncrementalSignalDevelopmentResultV1",
        "research_id": RESEARCH_ID,
        "source_commit": source_commit,
        "snapshot": {
            "name": SNAPSHOT_NAME,
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_sha256": SNAPSHOT_SHA256,
            "history_manifest_sha256": HISTORY_MANIFEST_SHA256,
        },
        "firewall": {"status": "PASS", "protected_or_spent_intersections": 0},
        "coverage": coverage,
        "warmup_targets": warmup_count,
        "scored_targets": len(scored),
        "beta_h2h": {
            "initial": 0.05,
            "bounds": [0.0, 0.25],
            "minimum": min(beta_values),
            "maximum": max(beta_values),
            "mean": sum(beta_values) / len(beta_values),
            "final": beta_values[-1],
            "fit_count": len(beta_values),
        },
        "metrics": metrics,
        "calibration": calibration,
        "gate_results": checks,
        "final_disposition": disposition,
        "production_champion_changed": False,
        "confirmation_evaluation_performed": False,
        "protected_evaluation_performed": False,
        "v6_created": False,
    }


def _prequential_baselines(
    rows: Sequence[ResearchRowV2],
) -> dict[UUID, tuple[float, float]]:
    fitted: ModelParametersV2 | None = None
    training: list[ResearchRowV2] = []
    last_fit_count = 0
    predictions: dict[UUID, tuple[float, float]] = {}
    for batch in kickoff_batches(rows):
        if len(training) >= MINIMUM_H2H_TRAINING_TARGETS and (
            fitted is None or len(training) - last_fit_count >= BASELINE_REFIT_INTERVAL
        ):
            fitted = fit_model(
                training,
                model_role="poisson_candidate",
                regularization=BASELINE_REGULARIZATION,
            )
            last_fit_count = len(training)
        if fitted is not None:
            for row in batch:
                prediction = predict_row(fitted, row)
                predictions[row.match_id] = (prediction.lambda_home, prediction.lambda_away)
        training.extend(batch)
    return predictions


def _target_forecasts(
    rows: Sequence[ResearchRowV2],
    baselines: Mapping[UUID, tuple[float, float]],
    meetings: Sequence[H2HMeeting],
) -> tuple[TargetForecast, ...]:
    feature_builder = H2HResidualV1()
    output: list[TargetForecast] = []
    for row in sorted(rows, key=lambda item: (item.kickoff_at, str(item.match_id))):
        baseline = baselines.get(row.match_id)
        if baseline is None:
            raise H2HResearchError("MODEL_FIT_UNAVAILABLE")
        target = H2HTarget(
            row.match_id,
            row.competition,
            _season_label(row.scope_key),
            row.kickoff_at,
            row.kickoff_at,
            row.home_team_id,
            row.away_team_id,
        )
        output.append(TargetForecast(row, feature_builder.build(target, meetings), *baseline))
    return tuple(output)


def _prequential_score(
    targets: Sequence[TargetForecast],
) -> tuple[tuple[ScoredTarget, ...], int, tuple[float, ...]]:
    batches: list[list[TargetForecast]] = []
    for target in targets:
        if not batches or batches[-1][0].row.kickoff_at != target.row.kickoff_at:
            batches.append([])
        batches[-1].append(target)
    training: list[TargetForecast] = []
    scored: list[ScoredTarget] = []
    beta_values: list[float] = []
    warmup_count = 0
    for batch_number, batch in enumerate(batches):
        eligible_batch = [
            item for item in batch if item.feature.status is H2HResidualStatus.AVAILABLE
        ]
        if len(training) < MINIMUM_H2H_TRAINING_TARGETS:
            warmup_count += len(eligible_batch)
        else:
            beta = fit_beta(training)
            beta_values.append(beta)
            for item in eligible_batch:
                scored.append(_score_target(item, beta, batch_number))
        training.extend(eligible_batch)
    return tuple(scored), warmup_count, tuple(beta_values)


def _score_target(item: TargetForecast, beta: float, batch_number: int) -> ScoredTarget:
    baseline_prediction = independent_poisson_prediction(item.lambda_home, item.lambda_away)
    candidate_rates = ContextualGoalAdjustmentV1(beta).adjust(
        item.lambda_home,
        item.lambda_away,
        item.feature.secondary_matchup_prior,
    )
    candidate_prediction = independent_poisson_prediction(*candidate_rates)
    outcome = (
        0
        if item.row.home_goals > item.row.away_goals
        else 1
        if item.row.home_goals == item.row.away_goals
        else 2
    )
    return ScoredTarget(
        str(item.row.match_id),
        item.row.competition,
        item.row.scope_key,
        item.row.kickoff_at.isoformat(),
        batch_number,
        beta,
        item.feature,
        _losses(baseline_prediction, item.row),
        _losses(candidate_prediction, item.row),
        baseline_prediction.one_x_two,
        candidate_prediction.one_x_two,
        outcome,
    )


def _losses(prediction: PredictionV2, row: ResearchRowV2) -> dict[str, float]:
    home = min(row.home_goals, 10)
    away = min(row.away_goals, 10)
    outcome = 0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2
    actual = tuple(float(index == outcome) for index in range(3))
    probabilities = prediction.one_x_two
    total_distribution = [0.0] * 21
    for x in range(11):
        for y in range(11):
            total_distribution[x + y] += prediction.score_matrix[x][y]
    observed_total = min(row.home_goals + row.away_goals, 20)
    cumulative = 0.0
    crps = 0.0
    for goals, probability in enumerate(total_distribution):
        cumulative += probability
        crps += (cumulative - float(goals >= observed_total)) ** 2
    return {
        "joint_score_log_loss": -math.log(max(prediction.score_matrix[home][away], 1e-15)),
        "one_x_two_log_loss": -math.log(max(probabilities[outcome], 1e-15)),
        "one_x_two_brier": sum(
            (probability - target) ** 2
            for probability, target in zip(probabilities, actual, strict=True)
        ),
        "one_x_two_rps": (
            (probabilities[0] - actual[0]) ** 2
            + (probabilities[0] + probabilities[1] - actual[0] - actual[1]) ** 2
        )
        / 2.0,
        "total_goal_crps": crps,
    }


def _metric_evidence(rows: Sequence[ScoredTarget]) -> dict[str, object]:
    result: dict[str, object] = {"weighted": _metric_summary(rows)}
    for competition in sorted({row.competition for row in rows}):
        result.setdefault("by_domain", {})[competition] = _metric_summary(  # type: ignore[index]
            [row for row in rows if row.competition == competition]
        )
    leave_domain_out: dict[str, object] = {}
    for competition in sorted({row.competition for row in rows}):
        leave_domain_out[competition] = _metric_summary(
            [row for row in rows if row.competition != competition]
        )["joint_score_log_loss"]
    result["leave_domain_out"] = leave_domain_out
    return result


def _metric_summary(rows: Sequence[ScoredTarget]) -> dict[str, object]:
    result: dict[str, object] = {"target_count": len(rows)}
    for metric in METRICS:
        baseline = [float(row.baseline[metric]) for row in rows]
        candidate = [float(row.candidate[metric]) for row in rows]
        result[metric] = {
            "baseline": sum(baseline) / len(baseline),
            "candidate": sum(candidate) / len(candidate),
            "candidate_minus_baseline": sum(c - b for b, c in zip(baseline, candidate, strict=True))
            / len(rows),
            "candidate_minus_baseline_95_interval": _paired_interval(rows, baseline, candidate),
        }
    return result


def _paired_interval(
    rows: Sequence[ScoredTarget], baseline: Sequence[float], candidate: Sequence[float]
) -> list[float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for row, base, challenger in zip(rows, baseline, candidate, strict=True):
        grouped[row.kickoff_batch].append(challenger - base)
    ordered = [grouped[key] for key in sorted(grouped)]
    if len(ordered) < BLOCK_LENGTH:
        point = sum(
            challenger - base for base, challenger in zip(baseline, candidate, strict=True)
        ) / len(rows)
        return [point, point]
    rng = random.Random(BOOTSTRAP_SEED)
    starts = list(range(len(ordered) - BLOCK_LENGTH + 1))
    values: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample: list[float] = []
        while len(sample) < len(rows):
            start = rng.choice(starts)
            sample.extend(
                value for block in ordered[start : start + BLOCK_LENGTH] for value in block
            )
        values.append(sum(sample[: len(rows)]) / len(rows))
    values.sort()
    return [values[49], values[1949]]


def _calibration_evidence(rows: Sequence[ScoredTarget]) -> dict[str, object]:
    output: dict[str, object] = {}
    for index, outcome in enumerate(("home", "draw", "away")):
        actual = [int(row.outcome == index) for row in rows]
        output[outcome] = {
            "baseline": _binary_calibration(
                [row.baseline_probabilities[index] for row in rows], actual
            ),
            "candidate": _binary_calibration(
                [row.candidate_probabilities[index] for row in rows], actual
            ),
        }
    return output


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
        raise H2HResearchError("MODEL_FIT_UNAVAILABLE")
    linear = result.x[0] + result.x[1] * logits
    fitted = 1.0 / (1.0 + np.exp(-linear))
    weights = fitted * (1.0 - fitted)
    design = np.column_stack((np.ones(len(logits)), logits))
    covariance = np.linalg.inv(design.T @ (weights[:, None] * design))
    standard_errors = np.sqrt(np.diag(covariance))
    return {
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
        "absolute_error": abs(float(result.x[0])) + abs(float(result.x[1]) - 1.0),
    }


def _gate_checks(
    metrics: Mapping[str, object], calibration: Mapping[str, object]
) -> dict[str, bool]:
    weighted = cast(Mapping[str, object], metrics["weighted"])
    joint = cast(Mapping[str, object], weighted["joint_score_log_loss"])
    one_x_two = cast(Mapping[str, object], weighted["one_x_two_log_loss"])
    checks = {
        "joint_delta_at_most_minus_0_003": cast(float, joint["candidate_minus_baseline"]) <= -0.003,
        "joint_delta_interval_upper_below_zero": cast(
            Sequence[float], joint["candidate_minus_baseline_95_interval"]
        )[1]
        < 0.0,
        "one_x_two_interval_upper_at_most_zero": cast(
            Sequence[float], one_x_two["candidate_minus_baseline_95_interval"]
        )[1]
        <= 0.0,
    }
    limits = {"one_x_two_brier": 0.01, "one_x_two_rps": 0.01, "total_goal_crps": 0.02}
    for metric, limit in limits.items():
        values = cast(Mapping[str, object], weighted[metric])
        checks[f"{metric}_interval_upper_at_most_{limit}"] = (
            cast(Sequence[float], values["candidate_minus_baseline_95_interval"])[1] <= limit
        )
    domains = cast(Mapping[str, Mapping[str, object]], metrics["by_domain"])
    domain_deltas = [
        cast(
            float,
            cast(Mapping[str, object], values["joint_score_log_loss"])["candidate_minus_baseline"],
        )
        for values in domains.values()
    ]
    checks["at_least_three_domains_negative_joint_delta"] = (
        sum(value < 0 for value in domain_deltas) >= 3
    )
    checks["no_domain_joint_delta_above_0_02"] = max(domain_deltas) <= 0.02
    leave_out = cast(Mapping[str, Mapping[str, object]], metrics["leave_domain_out"])
    checks["leave_domain_out_joint_interval_upper_at_most_0_05"] = all(
        cast(Sequence[float], values["candidate_minus_baseline_95_interval"])[1] <= 0.05
        for values in leave_out.values()
    )
    for outcome, roles_value in calibration.items():
        roles = cast(Mapping[str, Mapping[str, object]], roles_value)
        candidate = roles["candidate"]
        baseline = roles["baseline"]
        slope_interval = cast(Sequence[float], candidate["slope_95_interval"])
        intercept_interval = cast(Sequence[float], candidate["intercept_95_interval"])
        checks[f"{outcome}_calibration"] = (
            0.8 <= cast(float, candidate["slope"]) <= 1.2
            and abs(cast(float, candidate["intercept"])) <= 0.25
            and slope_interval[1] - slope_interval[0] <= 0.4
            and intercept_interval[1] - intercept_interval[0] <= 0.3
            and cast(float, candidate["absolute_error"]) <= cast(float, baseline["absolute_error"])
        )
    return checks


def _coverage(targets: Sequence[TargetForecast]) -> dict[str, object]:
    eligible = [item for item in targets if item.feature.status is H2HResidualStatus.AVAILABLE]
    by_competition: dict[str, int] = defaultdict(int)
    for item in eligible:
        by_competition[item.row.competition] += 1
    return {
        "all_targets": len(targets),
        "eligible_targets": len(eligible),
        "neutral_insufficient_h2h_targets": len(targets) - len(eligible),
        "eligible_by_competition": dict(sorted(by_competition.items())),
    }


def _meetings(
    observations: Sequence[ResearchObservationV2],
    baselines: Mapping[UUID, tuple[float, float]],
    incomplete_pair: frozenset[UUID],
) -> tuple[H2HMeeting, ...]:
    output = []
    for item in observations:
        baseline = baselines.get(item.match_id)
        if baseline is None:
            continue
        pair = frozenset((item.home_team_id, item.away_team_id))
        output.append(
            H2HMeeting(
                item.match_id,
                item.competition,
                _season_label(item.scope_key),
                item.kickoff_at,
                item.kickoff_at + timedelta(hours=3),
                item.home_team_id,
                item.away_team_id,
                item.home_npxg,
                item.away_npxg,
                baseline[0],
                baseline[1],
                not (item.scope_key == "la_liga_2023_24" and pair == incomplete_pair),
            )
        )
    return tuple(output)


def _incomplete_pair(primary: Path) -> frozenset[UUID]:
    completeness = _hashed_json(primary, "manifests", COMPLETENESS_MANIFEST_SHA256)
    mappings = _hashed_json(primary, "manifests", MAPPING_MANIFEST_SHA256)
    aliases = {
        (str(item["entity_type"]), str(item["provider_entity_id"])): UUID(str(item["canonical_id"]))
        for item in cast(Sequence[Mapping[str, object]], mappings["mappings"])
    }
    missing = cast(Sequence[Mapping[str, object]], completeness["missing_directed_fixtures"])
    if len(missing) != 1:
        raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")
    return frozenset(
        (
            aliases[("team", str(missing[0]["home_team_id"]))],
            aliases[("team", str(missing[0]["away_team_id"]))],
        )
    )


def _history_observation(item: Mapping[str, object]) -> ResearchObservationV2:
    return ResearchObservationV2(
        UUID(str(item["canonical_fixture_id"])),
        str(item["scope_key"]),
        str(item["competition"]),
        datetime.fromisoformat(str(item["kickoff_at"])),
        UUID(str(item["home_team_id"])),
        UUID(str(item["away_team_id"])),
        cast(int, item["home_goals"]),
        cast(int, item["away_goals"]),
        float(cast(float, item["home_npxg"])),
        float(cast(float, item["away_npxg"])),
    )


def _unique_rows(rows: Sequence[ResearchRowV2]) -> tuple[ResearchRowV2, ...]:
    by_id: dict[UUID, ResearchRowV2] = {}
    for row in rows:
        existing = by_id.get(row.match_id)
        if existing is not None and existing != row:
            raise H2HResearchError("FAIL_CLOSED_PROTOCOL_VIOLATION")
        by_id[row.match_id] = row
    return tuple(sorted(by_id.values(), key=lambda item: (item.kickoff_at, str(item.match_id))))


def _season_label(scope_key: str) -> str:
    parts = scope_key.rsplit("_", 2)
    if len(parts) != 3 or not parts[-2].isdigit() or not parts[-1].isdigit():
        raise H2HResearchError(f"invalid scope season: {scope_key}")
    return f"{parts[-2]}/{str(int(parts[-2]) + 1)}"


def _verify_snapshot(result: Mapping[str, object], primary: Path) -> None:
    required = {
        "snapshot_name": SNAPSHOT_NAME,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "history_manifest_sha256": HISTORY_MANIFEST_SHA256,
        "firewall_manifest_sha256": FIREWALL_MANIFEST_SHA256,
    }
    if any(result.get(key) != value for key, value in required.items()):
        raise H2HResearchError("FAIL_CLOSED_SNAPSHOT_IDENTITY_MISMATCH")
    for digest in (
        HISTORY_MANIFEST_SHA256,
        FIREWALL_MANIFEST_SHA256,
        MAPPING_MANIFEST_SHA256,
        COMPLETENESS_MANIFEST_SHA256,
    ):
        _hashed_json(primary, "manifests", digest)


def _hashed_json(root: Path, kind: str, digest: str) -> Mapping[str, Any]:
    path = root / kind / "sha256" / digest[:2] / f"{digest}.json"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise H2HResearchError("FAIL_CLOSED_SNAPSHOT_IDENTITY_MISMATCH")
    return cast(Mapping[str, Any], json.loads(path.read_text()))


def _json_file(path: Path) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], json.loads(path.read_text()))


def _deferred_result(
    source_commit: str, targets: Sequence[TargetForecast], warmup_count: int
) -> dict[str, object]:
    return {
        "contract": "MatchForgeH2HIncrementalSignalDevelopmentResultV1",
        "research_id": RESEARCH_ID,
        "source_commit": source_commit,
        "coverage": _coverage(targets),
        "warmup_targets": warmup_count,
        "scored_targets": 0,
        "final_disposition": "DEFER_INSUFFICIENT_ELIGIBLE_TARGETS",
        "production_champion_changed": False,
    }


def result_markdown(result: Mapping[str, object]) -> str:
    coverage = cast(Mapping[str, object], result["coverage"])
    lines = [
        "# MatchForge residualized H2H development result",
        "",
        f"Disposition: `{result['final_disposition']}`",
        "",
        f"Snapshot: `{SNAPSHOT_NAME}` (`{SNAPSHOT_ID}`)",
        f"Snapshot SHA-256: `{SNAPSHOT_SHA256}`",
        f"History manifest SHA-256: `{HISTORY_MANIFEST_SHA256}`",
        "",
        f"Eligible targets: {coverage['eligible_targets']}",
        f"Warmup targets: {result['warmup_targets']}",
        f"Scored targets: {result['scored_targets']}",
    ]
    if "beta_h2h" in result:
        beta = cast(Mapping[str, object], result["beta_h2h"])
        weighted = cast(
            Mapping[str, object], cast(Mapping[str, object], result["metrics"])["weighted"]
        )
        lines.extend(
            [
                f"Final beta_h2h: {beta['final']}",
                "",
                "## Weighted metrics",
                "",
            ]
        )
        for metric in METRICS:
            values = cast(Mapping[str, object], weighted[metric])
            lines.append(
                f"- {metric}: baseline {values['baseline']}; candidate {values['candidate']}; "
                f"delta {values['candidate_minus_baseline']}; 95% CI "
                f"{values['candidate_minus_baseline_95_interval']}"
            )
    lines.extend(["", "Production champion changed: **NO**", ""])
    return "\n".join(lines)


def serializable_scored(row: ScoredTarget) -> dict[str, object]:
    return asdict(row)
