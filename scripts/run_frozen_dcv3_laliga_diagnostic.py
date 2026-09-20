#!/usr/bin/env python3
"""Run the authorized frozen-DCv3 La Liga diagnostic without fitting a challenger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import UUID

import psycopg
from football.contracts.source import canonical_json_bytes
from football.forecasting.artifacts import serialize_dixon_coles_fit
from football.forecasting.dataset import (
    CompletedMatchV1,
    PointInTimeMatchDatasetProvider,
    WalkForwardDatasetSpecV1,
    WalkForwardTargetPlanV1,
)
from football.forecasting.dixon_coles import DixonColesModel, GoalMatch
from football.forecasting.execution import Sprint2ExecutionPolicyV1

_DATASET_ID = UUID("670662d6-6ed7-5fa1-ba3c-1cfd561e524f")
_SOURCE_SNAPSHOT_ID = UUID("01a08471-f763-7787-80ca-4293316b7e44")
_COMPETITION_ID = UUID("01a051db-552e-782d-b2ac-b3f0ec58441b")
_SEASON_ID = UUID("01a051db-553a-754a-9560-d79eceeb72b6")
_DATASET_IDENTITY_SHA256 = "5516752680f5863a0efbada19b3208fac3c64efb12fbeaa2c1894767c291d5e4"
_KNOWLEDGE_CUTOFF = datetime(2026, 9, 10, tzinfo=UTC)
_BOOTSTRAP_REPLICATES = 2_000
_BOOTSTRAP_BLOCK_SIZE = 10
_BOOTSTRAP_SEED = 20260909
_MEAN_BUCKETS = 3
_CHRONOLOGICAL_BLOCKS = 4
_TEAM_MINIMUM = 12


class DiagnosticError(RuntimeError):
    """The bounded diagnostic could not establish its frozen protocol."""


@dataclass(frozen=True, slots=True)
class FrozenForecast:
    batch_index: int
    match_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    training_cutoff: datetime
    training_count: int
    training_sha256: str
    model_state_sha256: str
    lambda_home: float
    lambda_away: float
    rho: float
    joint_state: dict[str, object]
    joint_state_sha256: str
    total_goal_probabilities: dict[str, float]
    forecast_freeze_sha256: str


@dataclass(frozen=True, slots=True)
class ScoredForecast:
    frozen: FrozenForecast
    home_goals: int
    away_goals: int

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals


def main() -> int:
    arguments = _arguments()
    database_url = arguments.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise DiagnosticError("database URL is required")
    output = arguments.output.resolve()
    report = _run(database_url)
    payload = canonical_json_bytes(report) + b"\n"
    if output.exists() and output.read_bytes() != payload:
        raise DiagnosticError("diagnostic output already exists with different bytes")
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_bytes(payload)
    print(json.dumps({"output": str(output), "sha256": _sha256(payload)}, sort_keys=True))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _run(database_url: str) -> dict[str, object]:
    with psycopg.connect(database_url) as connection:
        provider = PointInTimeMatchDatasetProvider(connection)
        _verify_entry_gate(connection)
        spec = _specification()
        plan = provider.walk_forward_plan(spec, _COMPETITION_ID, _SEASON_ID)
        _verify_frozen_plan(plan)
        forecasts = _freeze_forecasts(provider, plan)
        scored = _attach_goals(connection, provider, spec, plan, forecasts)
    diagnostics = _diagnostics(scored)
    return {
        "contract": "FrozenDCv3IndependentLaLigaDiagnosticV1",
        "entry_gate": {
            "dataset_version_id": str(_DATASET_ID),
            "source_snapshot_id": str(_SOURCE_SNAPSHOT_ID),
            "dataset_identity_sha256": _DATASET_IDENTITY_SHA256,
            "competition_id": str(_COMPETITION_ID),
            "season_id": str(_SEASON_ID),
            "lifecycle_claims": 380,
            "kickoff_claims": 380,
            "corner_labels": 380,
        },
        "protocol": {
            "prior_history_available": False,
            "warmup_rule": "first 100 chronological matches are WARMUP_ONLY",
            "diagnostic_target_rule": "prior competition history >= 100 and each team >= 10",
            "knowledge_mode": spec.knowledge_mode,
            "knowledge_cutoff": _utc(_KNOWLEDGE_CUTOFF),
            "fit_refit_frequency": "one frozen DCv3 fit per diagnostic kickoff batch",
            "dixon_coles_config": Sprint2ExecutionPolicyV1().dixon_coles_config.to_dict(),
            "bootstrap": {
                "method": "chronological-moving-block-bootstrap",
                "seed": _BOOTSTRAP_SEED,
                "replicates": _BOOTSTRAP_REPLICATES,
                "block_size_batches": _BOOTSTRAP_BLOCK_SIZE,
                "interval": "percentile-95",
            },
            "mean_bucket_rule": "three deterministic equal-count buckets ranked by forecast mean",
            "team_minimum_appearances": _TEAM_MINIMUM,
            "chronological_blocks": _CHRONOLOGICAL_BLOCKS,
        },
        "target_plan": {
            "corpus_match_count": plan.corpus_match_count,
            "warmup_match_count": plan.excluded_target_count,
            "diagnostic_target_count": plan.target_count,
            "diagnostic_target_sha256": plan.target_set_sha256,
            "football_time_start": _utc(plan.batches[0].kickoff_at),
            "football_time_end": _utc(plan.batches[-1].kickoff_at),
            "kickoff_batch_count": len(plan.batches),
        },
        "forecasts": [_forecast_dict(record) for record in scored],
        "diagnostics": diagnostics,
        "reproducibility": {
            "code_git_sha": _git_sha(),
            "dependency_lock_sha256": _sha256(Path("uv.lock").read_bytes()),
            "python_version": sys.version.split()[0],
            "scipy_version": _scipy_version(),
            "diagnostic_script_sha256": _sha256(Path(__file__).read_bytes()),
        },
    }


def _specification() -> WalkForwardDatasetSpecV1:
    return WalkForwardDatasetSpecV1(
        dataset_version_id=_DATASET_ID,
        source_snapshot_id=_SOURCE_SNAPSHOT_ID,
        feature_set_version="sprint2-team-counts-v1",
        knowledge_cutoff=_KNOWLEDGE_CUTOFF,
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256=_sha256(
            Path("schemas/quality/statsbomb-quality-policy-v1.json").read_bytes()
        ),
        minimum_team_history=10,
        minimum_competition_history=100,
    )


def _verify_entry_gate(connection: psycopg.Connection[Any]) -> None:
    row = connection.execute(
        """
        SELECT identity_hash, status
        FROM football.dataset_versions
        WHERE id = %s AND source_snapshot_id = %s
        """,
        (_DATASET_ID, _SOURCE_SNAPSHOT_ID),
    ).fetchone()
    if row != (_DATASET_IDENTITY_SHA256, "published"):
        raise DiagnosticError("DIAGNOSTIC_ENTRY_GATE_MISMATCH")
    counts = connection.execute(
        """
        SELECT
          count(DISTINCT lifecycle.match_id),
          count(DISTINCT kickoff.match_id),
          count(DISTINCT corner.match_id)
        FROM football.match_lifecycle_claims AS lifecycle
        LEFT JOIN football.match_kickoff_claims AS kickoff
          ON kickoff.lifecycle_claim_id = lifecycle.id
         AND kickoff.claim_version = 'statsbomb-spain-local-kickoff-v1'
         AND kickoff.timezone_name = 'Europe/Madrid'
        LEFT JOIN football.match_corner_labels AS corner
          ON corner.lifecycle_claim_id = lifecycle.id
         AND corner.claim_version = 'statsbomb-pass-type-61-corner-v1'
        WHERE lifecycle.dataset_version_id = %s
          AND lifecycle.source_snapshot_id = %s
          AND lifecycle.claim_version = 'statsbomb-terminal-event-score-v1'
          AND lifecycle.lifecycle = 'completed'
        """,
        (_DATASET_ID, _SOURCE_SNAPSHOT_ID),
    ).fetchone()
    if counts != (380, 380, 380):
        raise DiagnosticError("DIAGNOSTIC_ENTRY_GATE_MISMATCH")


def _verify_frozen_plan(plan: WalkForwardTargetPlanV1) -> None:
    if (
        plan.corpus_match_count != 380
        or plan.excluded_target_count != 100
        or plan.target_count != 280
        or not plan.batches
    ):
        raise DiagnosticError("DIAGNOSTIC_POPULATION_MISMATCH")
    first = plan.batches[0]
    if any(
        target.competition_history_matches != 100
        or target.home_history_matches < 10
        or target.away_history_matches < 10
        for target in first.targets
    ):
        raise DiagnosticError("DIAGNOSTIC_WARMUP_HISTORY_REQUIRED")


def _freeze_forecasts(
    provider: PointInTimeMatchDatasetProvider,
    plan: WalkForwardTargetPlanV1,
) -> tuple[FrozenForecast, ...]:
    model = DixonColesModel(Sprint2ExecutionPolicyV1().dixon_coles_config)
    forecasts: list[FrozenForecast] = []
    for batch_index, batch in enumerate(plan.batches):
        scope = plan.scope_for(batch)
        history = provider.completed_history(scope, _COMPETITION_ID, _SEASON_ID)
        contexts = provider.forecast_batch(scope, _COMPETITION_ID, _SEASON_ID).matches
        expected_ids = tuple(target.context.match_id for target in batch.targets)
        if tuple(context.match_id for context in contexts) != expected_ids:
            raise DiagnosticError("PIT_FORECAST_INTEGRITY_FAILURE")
        fit = model.fit(tuple(_goal_match(match) for match in history))
        state = serialize_dixon_coles_fit(fit)
        model_sha256 = _sha256(canonical_json_bytes(state))
        for context in contexts:
            if fit.training_cutoff >= context.kickoff_at:
                raise DiagnosticError("PIT_FORECAST_INTEGRITY_FAILURE")
            goal = model.forecast(fit.parameters, context.home_team_id, context.away_team_id)
            joint_state: dict[str, object] = {
                "labels": list(goal.score_matrix.labels),
                "probabilities": [list(row) for row in goal.score_matrix.probabilities],
            }
            joint_sha256 = _sha256(canonical_json_bytes(joint_state))
            total_goal_probabilities = _total_goal_probabilities(goal)
            freeze = {
                "match_id": str(context.match_id),
                "kickoff_at": _utc(context.kickoff_at),
                "training_cutoff": _utc(fit.training_cutoff),
                "training_sha256": fit.training_sha256,
                "model_state_sha256": model_sha256,
                "joint_state_sha256": joint_sha256,
                "knowledge_cutoff": _utc(scope.knowledge_cutoff),
            }
            forecasts.append(
                FrozenForecast(
                    batch_index=batch_index,
                    match_id=context.match_id,
                    kickoff_at=context.kickoff_at,
                    home_team_id=context.home_team_id,
                    away_team_id=context.away_team_id,
                    training_cutoff=fit.training_cutoff,
                    training_count=fit.training_match_count,
                    training_sha256=fit.training_sha256,
                    model_state_sha256=model_sha256,
                    lambda_home=goal.lambda_home,
                    lambda_away=goal.lambda_away,
                    rho=goal.low_score_correlation,
                    joint_state=joint_state,
                    joint_state_sha256=joint_sha256,
                    total_goal_probabilities=total_goal_probabilities,
                    forecast_freeze_sha256=_sha256(canonical_json_bytes(freeze)),
                )
            )
    return tuple(forecasts)


def _attach_goals(
    connection: psycopg.Connection[Any],
    provider: PointInTimeMatchDatasetProvider,
    spec: WalkForwardDatasetSpecV1,
    plan: WalkForwardTargetPlanV1,
    forecasts: tuple[FrozenForecast, ...],
) -> tuple[ScoredForecast, ...]:
    if len(forecasts) != plan.target_count:
        raise DiagnosticError("PIT_FORECAST_INTEGRITY_FAILURE")
    policy = provider._kickoff_policy(
        spec.dataset_version_id,
        spec.source_snapshot_id,
        spec.knowledge_cutoff,
        _COMPETITION_ID,
        _SEASON_ID,
    )
    rows = connection.execute(
        """
        SELECT match.id, observation.home_score, observation.away_score
        FROM football.matches AS match
        JOIN football.match_kickoff_claims AS kickoff ON kickoff.match_id = match.id
        JOIN football.match_lifecycle_claims AS lifecycle
          ON lifecycle.id = kickoff.lifecycle_claim_id
        JOIN football.match_observations AS observation
          ON observation.id = lifecycle.match_observation_id
        WHERE match.id = ANY(%s)
          AND kickoff.claim_version = %s
          AND kickoff.timezone_name = %s
          AND kickoff.tzdata_version = '2026.3'
          AND kickoff.known_from <= %s
          AND lifecycle.dataset_version_id = %s
          AND lifecycle.source_snapshot_id = %s
          AND lifecycle.claim_version = 'statsbomb-terminal-event-score-v1'
          AND lifecycle.lifecycle = 'completed'
          AND lifecycle.known_from <= %s
          AND observation.home_score IS NOT NULL
          AND observation.away_score IS NOT NULL
        ORDER BY match.id
        """,
        (
            [record.match_id for record in forecasts],
            policy.claim_version,
            policy.timezone_name,
            spec.knowledge_cutoff,
            spec.dataset_version_id,
            spec.source_snapshot_id,
            spec.knowledge_cutoff,
        ),
    ).fetchall()
    outcomes = {UUID(str(match_id)): (int(home), int(away)) for match_id, home, away in rows}
    if len(outcomes) != len(forecasts):
        raise DiagnosticError("PIT_FORECAST_INTEGRITY_FAILURE")
    return tuple(ScoredForecast(record, *outcomes[record.match_id]) for record in forecasts)


def _diagnostics(records: tuple[ScoredForecast, ...]) -> dict[str, object]:
    if len(records) != 280:
        raise DiagnosticError("DIAGNOSTIC_POPULATION_MISMATCH")
    components = {
        "home": (lambda item: item.frozen.lambda_home, lambda item: item.home_goals),
        "away": (lambda item: item.frozen.lambda_away, lambda item: item.away_goals),
        "total": (
            lambda item: item.frozen.lambda_home + item.frozen.lambda_away,
            lambda item: item.total_goals,
        ),
    }
    conditional = {
        name: _conditional_buckets(records, predicted, observed, index)
        for index, (name, (predicted, observed)) in enumerate(components.items())
    }
    covariance = _covariance(records)
    attack = _persistence(records, "attack")
    defence = _persistence(records, "defence")
    heterogeneity = {
        "attack": _team_heterogeneity(records, "attack"),
        "defence": _team_heterogeneity(records, "defence"),
    }
    total_shape = _total_shape(records)
    chronological = _chronological_blocks(records)
    classification = _classify(conditional, covariance, attack, defence, heterogeneity)
    return {
        "conditional_variance": conditional,
        "home_away_residual_covariance": covariance,
        "attack_residual_persistence": attack,
        "defence_residual_persistence": defence,
        "static_team_heterogeneity": heterogeneity,
        "total_goal_shape": total_shape,
        "chronological_diagnostics": chronological,
        "competition_heterogeneity": "COMPETITION_HETEROGENEITY_NOT_IDENTIFIABLE",
        "classification": classification,
    }


def _conditional_buckets(
    records: tuple[ScoredForecast, ...],
    predicted: Callable[[ScoredForecast], float],
    observed: Callable[[ScoredForecast], int],
    seed_offset: int,
) -> list[dict[str, object]]:
    ordered = sorted(records, key=lambda item: (predicted(item), str(item.frozen.match_id)))
    buckets = _equal_count_groups(ordered, _MEAN_BUCKETS)
    results: list[dict[str, object]] = []
    for index, bucket in enumerate(buckets):
        values = [float(observed(item)) for item in bucket]
        means = [predicted(item) for item in bucket]
        variance = _sample_variance(values)
        expected = fmean(means)
        results.append(
            {
                "bucket": index + 1,
                "sample_count": len(bucket),
                "mean_predicted_goals": expected,
                "mean_observed_goals": fmean(values),
                "mean_bias": fmean(value - mean for value, mean in zip(values, means, strict=True)),
                "observed_variance": variance,
                "poisson_expected_variance": expected,
                "variance_minus_mean": variance - expected,
                "variance_to_mean": variance / expected,
                "variance_minus_mean_interval": _batch_bootstrap_interval(
                    bucket,
                    lambda sample: (
                        _sample_variance([float(observed(item)) for item in sample])
                        - fmean([predicted(item) for item in sample])
                    ),
                    seed_offset * 100 + index,
                ),
                "mean_bias_interval": _batch_bootstrap_interval(
                    bucket,
                    lambda sample: fmean(
                        float(observed(item)) - predicted(item) for item in sample
                    ),
                    seed_offset * 100 + index + 50,
                ),
            }
        )
    return results


def _covariance(records: tuple[ScoredForecast, ...]) -> dict[str, object]:
    def residual_pairs(sample: Sequence[ScoredForecast]) -> tuple[list[float], list[float]]:
        return (
            [item.home_goals - item.frozen.lambda_home for item in sample],
            [item.away_goals - item.frozen.lambda_away for item in sample],
        )

    home, away = residual_pairs(records)
    return {
        "sample_count": len(records),
        "covariance": _covariance_value(home, away),
        "correlation": _correlation(home, away),
        "covariance_interval": _batch_bootstrap_interval(
            records,
            lambda sample: _covariance_value(*residual_pairs(sample)),
            301,
        ),
        "correlation_interval": _batch_bootstrap_interval(
            records,
            lambda sample: _correlation(*residual_pairs(sample)),
            302,
        ),
    }


def _persistence(records: tuple[ScoredForecast, ...], role: str) -> dict[str, object]:
    series = _team_series(records, role)
    metrics = _persistence_metrics(series)
    lag_seed = 401 if role == "attack" else 501
    sign_seed = 402 if role == "attack" else 502
    return {
        **metrics,
        "lag_1_correlation_interval": _team_bootstrap_interval(
            series,
            lambda sample: _persistence_metrics(sample)["lag_1_correlation"],
            lag_seed,
        ),
        "sign_persistence_interval": _team_bootstrap_interval(
            series,
            lambda sample: _persistence_metrics(sample)["sign_persistence"],
            sign_seed,
        ),
    }


def _team_heterogeneity(records: tuple[ScoredForecast, ...], role: str) -> list[dict[str, object]]:
    series = _team_series(records, role)
    rows: list[dict[str, object]] = []
    for team_id, values in sorted(series.items(), key=lambda item: str(item[0])):
        if len(values) < _TEAM_MINIMUM:
            continue
        residuals = [value for _kickoff, value in values]
        rows.append(
            {
                "team_id": str(team_id),
                "appearances": len(residuals),
                "mean_residual": fmean(residuals),
                "residual_variance": _sample_variance(residuals),
                "lag_1_correlation": _correlation(residuals[:-1], residuals[1:]),
                "mean_residual_interval": _series_bootstrap_interval(
                    residuals, len(rows) + (601 if role == "attack" else 701)
                ),
            }
        )
    return rows


def _total_shape(records: tuple[ScoredForecast, ...]) -> list[dict[str, object]]:
    categories = (*range(6), "6+")
    rows: list[dict[str, object]] = []
    for index, category in enumerate(categories):

        def observed(item: ScoredForecast, category: int | str = category) -> int:
            return int(
                item.total_goals == category if isinstance(category, int) else item.total_goals >= 6
            )

        def expected(item: ScoredForecast, category: int | str = category) -> float:
            return _total_probability(item.frozen, category)

        def difference(sample: Sequence[ScoredForecast]) -> float:
            return fmean(float(observed(item)) - expected(item) for item in sample)

        rows.append(
            {
                "total_goals": str(category),
                "predicted_frequency": fmean(expected(item) for item in records),
                "observed_frequency": fmean(float(observed(item)) for item in records),
                "difference": fmean(float(observed(item)) - expected(item) for item in records),
                "difference_interval": _batch_bootstrap_interval(
                    records,
                    difference,
                    801 + index,
                ),
            }
        )
    return rows


def _chronological_blocks(records: tuple[ScoredForecast, ...]) -> list[dict[str, object]]:
    batches: dict[int, list[ScoredForecast]] = defaultdict(list)
    for record in records:
        batches[record.frozen.batch_index].append(record)
    groups = _equal_count_groups([batches[key] for key in sorted(batches)], _CHRONOLOGICAL_BLOCKS)
    rows: list[dict[str, object]] = []
    for index, group in enumerate(groups):
        flattened = tuple(item for batch in group for item in batch)
        residuals = [
            item.total_goals - item.frozen.lambda_home - item.frozen.lambda_away
            for item in flattened
        ]
        shape_error = sum(
            abs(
                fmean(float(item.total_goals == goal) for item in flattened)
                - fmean(_total_probability(item.frozen, goal) for item in flattened)
            )
            for goal in (*range(6), "6+")
        )
        rows.append(
            {
                "block": index + 1,
                "sample_count": len(flattened),
                "football_time_start": _utc(flattened[0].frozen.kickoff_at),
                "football_time_end": _utc(flattened[-1].frozen.kickoff_at),
                "mean_residual": fmean(residuals),
                "residual_variance": _sample_variance(residuals),
                "total_goal_shape_error": shape_error,
                "mean_residual_interval": _batch_bootstrap_interval(
                    flattened,
                    lambda sample: fmean(
                        item.total_goals - item.frozen.lambda_home - item.frozen.lambda_away
                        for item in sample
                    ),
                    901 + index,
                ),
            }
        )
    return rows


def _classify(
    conditional: dict[str, list[dict[str, object]]],
    covariance: dict[str, object],
    attack: dict[str, object],
    defence: dict[str, object],
    heterogeneity: dict[str, list[dict[str, object]]],
) -> dict[str, object]:
    variance_support = sum(
        any(_interval_lower(bucket["variance_minus_mean_interval"]) > 0.0 for bucket in buckets)
        for buckets in conditional.values()
    )
    mean_bias = any(
        any(not _contains_zero(bucket["mean_bias_interval"]) for bucket in buckets)
        for buckets in conditional.values()
    )
    shared_intensity = _interval_lower(covariance["correlation_interval"]) >= 0.1
    dynamic_strength = (
        max(
            _interval_lower(attack["lag_1_correlation_interval"]),
            _interval_lower(defence["lag_1_correlation_interval"]),
        )
        >= 0.1
    )
    static_teams = sum(
        not _contains_zero(row["mean_residual_interval"])
        for rows in heterogeneity.values()
        for row in rows
    )
    static_heterogeneity = static_teams >= 3 and not dynamic_strength
    supported = []
    if variance_support >= 2 and not mean_bias and not shared_intensity and not dynamic_strength:
        supported.append("A. INDEPENDENT_OVERDISPERSION_SUPPORTED")
    if variance_support >= 2 and not mean_bias and shared_intensity:
        supported.append("B. SHARED_INTENSITY_SUPPORTED")
    if dynamic_strength:
        supported.append("C. DYNAMIC_STRENGTH_SUPPORTED")
    if static_heterogeneity:
        supported.append("D. STATIC_HETEROGENEITY_SUPPORTED")
    if len(supported) > 1:
        conclusion = "E. MULTIPLE_MECHANISMS_SUPPORTED"
    elif supported:
        conclusion = supported[0]
    else:
        conclusion = "F. NO_CLEAR_MODEL_FAMILY_SIGNAL"
    if conclusion == "F. NO_CLEAR_MODEL_FAMILY_SIGNAL":
        recommendation = "NO_CHALLENGER_YET"
    else:
        recommendation = "AUTHORIZE_CONTRACT_RESEARCH_FOR_" + conclusion.split(". ", 1)[1]
    return {
        "frozen_rule": {
            "conditional_variance_components_required": 2,
            "material_correlation_lower_bound": 0.1,
            "dynamic_lag_1_correlation_lower_bound": 0.1,
            "static_team_offsets_required": 3,
            "mean_bias_blocks_dispersion_classification": True,
        },
        "signals": {
            "conditional_variance_components": variance_support,
            "mean_bias_present": mean_bias,
            "shared_intensity": shared_intensity,
            "dynamic_strength": dynamic_strength,
            "static_heterogeneity": static_heterogeneity,
        },
        "conclusion": conclusion,
        "recommendation": recommendation,
    }


def _team_series(
    records: Iterable[ScoredForecast], role: str
) -> dict[UUID, list[tuple[datetime, float]]]:
    series: dict[UUID, list[tuple[datetime, float]]] = defaultdict(list)
    for item in records:
        if role == "attack":
            series[item.frozen.home_team_id].append(
                (item.frozen.kickoff_at, item.home_goals - item.frozen.lambda_home)
            )
            series[item.frozen.away_team_id].append(
                (item.frozen.kickoff_at, item.away_goals - item.frozen.lambda_away)
            )
        else:
            series[item.frozen.home_team_id].append(
                (item.frozen.kickoff_at, item.away_goals - item.frozen.lambda_away)
            )
            series[item.frozen.away_team_id].append(
                (item.frozen.kickoff_at, item.home_goals - item.frozen.lambda_home)
            )
    return {team: sorted(values) for team, values in series.items()}


def _persistence_metrics(series: dict[UUID, list[tuple[datetime, float]]]) -> dict[str, object]:
    lag_pairs = [
        (values[index - 1][1], values[index][1])
        for values in series.values()
        for index in range(1, len(values))
    ]
    rolling_pairs = [
        (fmean(value for _time, value in values[index - 3 : index]), values[index][1])
        for values in series.values()
        for index in range(3, len(values))
    ]
    same_sign = [
        previous * current > 0.0 for previous, current in lag_pairs if previous * current != 0.0
    ]
    under = [current < 0.0 for previous, current in lag_pairs if previous < 0.0]
    over = [current > 0.0 for previous, current in lag_pairs if previous > 0.0]
    return {
        "lag_1_pair_count": len(lag_pairs),
        "lag_1_correlation": _correlation(*zip(*lag_pairs, strict=True)),
        "rolling_3_pair_count": len(rolling_pairs),
        "rolling_3_correlation": _correlation(*zip(*rolling_pairs, strict=True)),
        "sign_persistence": fmean(same_sign) if same_sign else None,
        "directional_underprediction_persistence": fmean(under) if under else None,
        "directional_overprediction_persistence": fmean(over) if over else None,
    }


def _batch_bootstrap_interval(
    records: Sequence[ScoredForecast],
    statistic: Callable[[Sequence[ScoredForecast]], float],
    seed: int,
) -> list[float | None]:
    groups: dict[int, list[ScoredForecast]] = defaultdict(list)
    for record in records:
        groups[record.frozen.batch_index].append(record)
    batches = [groups[key] for key in sorted(groups)]
    values: list[float] = []
    random_source = random.Random(_BOOTSTRAP_SEED + seed)
    for _ in range(_BOOTSTRAP_REPLICATES):
        sample: list[ScoredForecast] = []
        while len(sample) < len(records):
            start = random_source.randrange(len(batches))
            for offset in range(_BOOTSTRAP_BLOCK_SIZE):
                sample.extend(batches[(start + offset) % len(batches)])
                if len(sample) >= len(records):
                    break
        value = statistic(sample[: len(records)])
        if math.isfinite(value):
            values.append(value)
    return _interval(values)


def _team_bootstrap_interval(
    series: dict[UUID, list[tuple[datetime, float]]],
    statistic: Callable[[dict[UUID, list[tuple[datetime, float]]]], object],
    seed: int,
) -> list[float | None]:
    team_ids = tuple(sorted(series, key=str))
    values: list[float] = []
    random_source = random.Random(_BOOTSTRAP_SEED + seed)
    for _ in range(_BOOTSTRAP_REPLICATES):
        sample = {
            UUID(int=index + 1): series[random_source.choice(team_ids)]
            for index in range(len(team_ids))
        }
        value = statistic(sample)
        if isinstance(value, (int, float)) and math.isfinite(value):
            values.append(float(value))
    return _interval(values)


def _series_bootstrap_interval(values: Sequence[float], seed: int) -> list[float | None]:
    random_source = random.Random(_BOOTSTRAP_SEED + seed)
    samples: list[float] = []
    for _ in range(_BOOTSTRAP_REPLICATES):
        sample: list[float] = []
        while len(sample) < len(values):
            start = random_source.randrange(len(values))
            sample.extend(values[(start + offset) % len(values)] for offset in range(3))
        samples.append(fmean(sample[: len(values)]))
    return _interval(samples)


def _equal_count_groups(values: Sequence[Any], count: int) -> list[Sequence[Any]]:
    return [
        values[index * len(values) // count : (index + 1) * len(values) // count]
        for index in range(count)
    ]


def _total_probability(forecast: FrozenForecast, category: int | str) -> float:
    return forecast.total_goal_probabilities[str(category)]


def _total_goal_probabilities(goal: Any) -> dict[str, float]:
    values: dict[str, float] = {}
    for total in range(6):
        values[str(total)] = sum(
            goal.exact_score_probability(home_goals, total - home_goals)
            for home_goals in range(total + 1)
        )
    tail = 1.0 - sum(values.values())
    if tail < -1e-12:
        raise DiagnosticError("PIT_FORECAST_INTEGRITY_FAILURE")
    values["6+"] = max(tail, 0.0)
    return values


def _forecast_dict(item: ScoredForecast) -> dict[str, object]:
    frozen = item.frozen
    return {
        "canonical_match_id": str(frozen.match_id),
        "kickoff_at": _utc(frozen.kickoff_at),
        "home_team_id": str(frozen.home_team_id),
        "away_team_id": str(frozen.away_team_id),
        "training_cutoff": _utc(frozen.training_cutoff),
        "knowledge_cutoff": _utc(_KNOWLEDGE_CUTOFF),
        "training_population_count": frozen.training_count,
        "training_population_sha256": frozen.training_sha256,
        "dcv3_logical_model_sha256": frozen.model_state_sha256,
        "lambda_home": frozen.lambda_home,
        "lambda_away": frozen.lambda_away,
        "rho": frozen.rho,
        "expected_total_goals": frozen.lambda_home + frozen.lambda_away,
        "joint_probability_state": frozen.joint_state,
        "joint_probability_state_sha256": frozen.joint_state_sha256,
        "forecast_freeze_sha256": frozen.forecast_freeze_sha256,
        "observed_home_goals": item.home_goals,
        "observed_away_goals": item.away_goals,
        "observed_total_goals": item.total_goals,
        "home_residual": item.home_goals - frozen.lambda_home,
        "away_residual": item.away_goals - frozen.lambda_away,
        "total_residual": item.total_goals - frozen.lambda_home - frozen.lambda_away,
    }


def _goal_match(match: CompletedMatchV1) -> GoalMatch:
    return GoalMatch(
        match_id=match.match_id,
        kickoff_at=match.kickoff_at,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_goals=match.home_score,
        away_goals=match.away_score,
    )


def _sample_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.nan
    mean = fmean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _covariance_value(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) < 2 or len(left) != len(right):
        return math.nan
    left_mean = fmean(left)
    right_mean = fmean(right)
    return sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)) / (
        len(left) - 1
    )


def _correlation(left: Sequence[float], right: Sequence[float]) -> float:
    covariance = _covariance_value(left, right)
    denominator = math.sqrt(_sample_variance(left) * _sample_variance(right))
    return covariance / denominator if denominator > 0.0 else math.nan


def _interval(values: Sequence[float]) -> list[float | None]:
    if not values:
        return [None, None]
    ordered = sorted(values)
    return [ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))]]


def _interval_lower(value: object) -> float:
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], (int, float)):
        return math.nan
    return float(value[0])


def _contains_zero(value: object) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return True
    return (
        isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
        and value[0] <= 0 <= value[1]
    )


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _scipy_version() -> str:
    import scipy

    return str(scipy.__version__)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DiagnosticError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
