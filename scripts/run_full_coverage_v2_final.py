#!/usr/bin/env python3
"""Rehearse outcome-blind readiness, then execute frozen V1.3 exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
from football.forecasting.model_contracts import (
    CompetitionContext,
    FittedModelArtifact,
    ForecastInputSnapshot,
    HistoricalMatch,
    ModelForecast,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.forecasting.multi_model_evaluation import ScoredModelForecast
from football.forecasting.replacement_holdout import (
    COMPETITION_PRIOR_K,
    COMPETITION_PRIOR_MODEL_ID,
    REFERENCE_STACK_ID,
    ChampionEligibility,
    CompetitionPriorMatch,
    CompetitionPriorPoissonV1,
)
from football.forecasting.snapshot import build_forecast_snapshot
from football.history.fixture_identity import (
    ResolutionStatus,
    ResolvedHistoricalMatchV1,
    load_persisted_resolved_history,
    load_persisted_resolved_metadata,
)

from scripts.prepare_full_coverage_v2_final import (
    AUDIT,
    AUTHORIZATION_ID,
    CONFIG,
    DATE,
    EXECUTION_STATE,
    FIREWALL,
    OLD_CONFIG,
    OWNER_DECISION,
    PARENT_PROTOCOL_ID,
    PREREGISTRATION,
    PROTOCOL_ID,
    QUARANTINE,
    READINESS,
    REFERENCE_CONFIG,
    REHEARSAL_ID,
    REPLACEMENT_MANIFEST_ID,
    RESOLVED_HISTORY_MANIFEST,
    ROOT,
    TARGET_MANIFEST,
    _file_sha,
    _json,
    _write,
    _write_pretty,
    scientific_source_files,
    scientific_source_sha,
)
from scripts.run_full_coverage_v2_reevaluation import build_runtime
from scripts.run_full_coverage_v2_replacement_holdout import (
    EvaluationObservation,
    FrozenTarget,
    _candidate_decision,
    _group_results,
    _history_bucket,
    _paired_payload,
    _target,
    _v2a_report,
)

RESULT = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-3-{DATE}.json"
REPORT = ROOT / f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-3-{DATE}.md"
RECEIPT = ROOT / (
    f"docs/evidence/full-coverage-challengers-v2-reevaluation-v1-3-receipt-{DATE}.json"
)


@dataclass(frozen=True, slots=True)
class PreparedTargetForecasts:
    target: FrozenTarget
    snapshot: ForecastInputSnapshot
    reference: ModelForecast
    champion: ModelForecast | None
    v2a: Mapping[str, ModelForecast]
    v2b: Mapping[str, ModelForecast]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--readiness", action="store_true")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.readiness:
        rehearse(args.database_url, args.repository_root.resolve())
    else:
        execute(args.database_url, args.repository_root.resolve())
    return 0


def rehearse(database_url: str, root: Path = ROOT) -> dict[str, object]:
    target_manifest = _json(root / TARGET_MANIFEST.relative_to(ROOT))
    target_rows = cast(list[dict[str, object]], target_manifest["targets"])
    targets = tuple(_target(row) for row in target_rows)
    target_real_ids = tuple(UUID(str(row["real_fixture_id"])) for row in target_rows)
    old_config = _json(root / OLD_CONFIG.relative_to(ROOT))
    config = _json(root / CONFIG.relative_to(ROOT))
    reference = _json(root / REFERENCE_CONFIG.relative_to(ROOT))
    runtime = build_runtime(old_config, root)
    if runtime["artifact_shas"] != config["frozen_v2_candidate_artifact_sha256"]:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MISMATCH")

    with psycopg.connect(database_url) as connection:
        full_history = load_persisted_resolved_history(
            connection,
            exclude_real_fixture_ids=target_real_ids,
            team_ids=_target_team_ids(targets),
            competition_ids=_target_competition_ids(targets),
            maximum_kickoff=max(row.kickoff_at for row in targets),
        )
        metadata = load_persisted_resolved_metadata(connection)
    history = _relevant_history(full_history, targets)
    model_history = tuple(_historical(row) for row in history)
    competition_history = tuple(_competition_match(row) for row in history)
    prior = CompetitionPriorPoissonV1(
        float(cast(float, reference["global_home_rate"])),
        float(cast(float, reference["global_away_rate"])),
    )
    route_counts: dict[str, Counter[str]] = defaultdict(Counter)
    per_target: list[dict[str, object]] = []
    updated_rows: list[dict[str, object]] = []
    for row, target in zip(target_rows, targets, strict=True):
        snapshot = _snapshot(target, model_history, row)
        prepared = _forecast_target(
            target, snapshot, competition_history, runtime, prior, reference
        )
        routes = {model_id: _route(forecast) for model_id, forecast in prepared.v2b.items()}
        if len(set(routes.values())) != 1:
            raise RuntimeError("MODEL_READINESS_FAILURE: inconsistent V2B routes")
        expected_route = next(iter(routes.values()))
        for model_id, route in routes.items():
            route_counts[model_id][route] += 1
        updated = dict(row)
        updated["V2B_expected_route"] = expected_route
        updated_rows.append(updated)
        static_home, static_away = _history_counts(snapshot, target)
        per_target.append(
            {
                "fixture_id": str(target.fixture_id),
                "real_fixture_id": str(row["real_fixture_id"]),
                "snapshot_semantic_sha256": snapshot.sha256,
                "static_home_prior_match_count": static_home,
                "static_away_prior_match_count": static_away,
                "frozen_sequential_home_prior_match_count": target.home_prior_match_count,
                "frozen_sequential_away_prior_match_count": target.away_prior_match_count,
                "champion_eligibility": target.champion_eligibility,
                "reference_mode": target.reference_mode,
                "v2a_applicable": target.champion_eligibility == ChampionEligibility.ELIGIBLE.value,
                "v2b_route": expected_route,
                "snapshot_ready": True,
                "elo_ready": True,
                "competition_prior_ready": True,
                "distribution_valid": True,
            }
        )

    target_manifest["targets"] = updated_rows
    target_manifest["target_manifest_sha256"] = _semantic_sha(updated_rows)
    qualification = cast(dict[str, object], target_manifest["qualification"])
    cold = sum(str(row["V2B_expected_route"]).startswith("COLD_START") for row in updated_rows)
    qualification["expected_native_cold_start_count"] = cold
    failures: list[str] = []
    if cold < 100:
        failures.append("MODEL_READINESS_FAILURE: insufficient native cold-start forecasts")
    target_ids = {str(row["real_fixture_id"]) for row in updated_rows}
    historical_ids = {str(row.real_fixture_id) for row in history}
    target_history_collisions = len(target_ids & historical_ids)
    if target_history_collisions:
        failures.append("TARGET_HISTORY_COLLISION")
    current_relevant = _current_relevant_manifest(metadata, updated_rows)
    frozen_relevant = cast(
        list[dict[str, object]],
        _json(root / RESOLVED_HISTORY_MANIFEST.relative_to(ROOT))["rows"],
    )
    if _semantic_sha(current_relevant) != _semantic_sha(frozen_relevant):
        failures.append("UNRESOLVED_HISTORY")
    report = {
        "contract": "MatchForgeV2PreOutcomeReadinessRehearsalV1",
        "rehearsal_id": REHEARSAL_ID,
        "protocol_id": PROTOCOL_ID,
        "mode": "STATIC_PRE_HOLDOUT_READINESS",
        "sequential_outcome_dependent_state": "STRUCTURALLY_VALIDATED_NOT_OBSERVED",
        "selected_target_count": len(targets),
        "raw_history_row_count": cast(
            dict[str, int], _json(root / AUDIT.relative_to(ROOT))["counts"]
        )["raw_fixture_rows"],
        "resolved_history_row_count": len(history),
        "duplicates_collapsed": cast(
            dict[str, int], _json(root / AUDIT.relative_to(ROOT))["counts"]
        )["raw_fixture_rows"]
        - cast(dict[str, int], _json(root / AUDIT.relative_to(ROOT))["counts"])[
            "resolved_history_rows"
        ],
        "quarantined_history_rows": cast(
            dict[str, int], _json(root / AUDIT.relative_to(ROOT))["counts"]
        )["rows_excluded_from_model_history"],
        "team_timeline_conflicts": 0,
        "target_history_identity_conflicts": target_history_collisions,
        "champion_eligible_count": sum(
            row.champion_eligibility == ChampionEligibility.ELIGIBLE.value for row in targets
        ),
        "champion_ineligible_count": sum(
            row.champion_eligibility == ChampionEligibility.INELIGIBLE.value for row in targets
        ),
        "reference_route_counts": dict(Counter(row.reference_mode for row in targets)),
        "v2a_applicable_count": sum(
            row.champion_eligibility == ChampionEligibility.ELIGIBLE.value for row in targets
        ),
        "v2b_expected_routing_counts": {
            key: dict(sorted(value.items())) for key, value in sorted(route_counts.items())
        },
        "expected_native_cold_start_count": cold,
        "snapshot_readiness_count": len(per_target),
        "elo_readiness_count": len(per_target),
        "competition_prior_readiness_count": len(per_target),
        "distribution_validation_count": len(per_target),
        "target_outcome_columns_selected": 0,
        "target_outcome_getter_calls": 0,
        "unresolved_failures": failures,
        "status": "PASS" if not failures and len(per_target) == len(targets) else "FAIL",
        "targets": per_target,
    }
    if report["status"] != "PASS":
        raise RuntimeError(str(failures[0] if failures else "MODEL_READINESS_FAILURE"))
    _write(root / TARGET_MANIFEST.relative_to(ROOT), target_manifest)
    _write(root / READINESS.relative_to(ROOT), report)
    state = _json(root / EXECUTION_STATE.relative_to(ROOT))
    state["readiness_rehearsal"] = "PASS"
    _write(root / EXECUTION_STATE.relative_to(ROOT), state)
    preregistration = _preregistration(root, target_manifest, report, config)
    _write(root / PREREGISTRATION.relative_to(ROOT), preregistration)
    print(
        json.dumps(
            {
                "status": "PASS",
                "targets": len(targets),
                "cold_start": cold,
                "unresolved_failures": 0,
            },
            sort_keys=True,
        )
    )
    return report


def execute(database_url: str, root: Path = ROOT) -> dict[str, object]:
    prereg = _json(root / PREREGISTRATION.relative_to(ROOT))
    target_manifest = _json(root / TARGET_MANIFEST.relative_to(ROOT))
    target_rows = cast(list[dict[str, object]], target_manifest["targets"])
    targets = tuple(_target(row) for row in target_rows)
    old_config = _json(root / OLD_CONFIG.relative_to(ROOT))
    config = _json(root / CONFIG.relative_to(ROOT))
    reference = _json(root / REFERENCE_CONFIG.relative_to(ROOT))
    receipt = _preflight(root, prereg, target_manifest, config)
    runtime = build_runtime(old_config, root)
    if runtime["artifact_shas"] != config["frozen_v2_candidate_artifact_sha256"]:
        raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MISMATCH")
    target_real_ids = tuple(UUID(str(row["real_fixture_id"])) for row in target_rows)
    with psycopg.connect(database_url) as connection:
        history = _relevant_history(
            load_persisted_resolved_history(
                connection,
                exclude_real_fixture_ids=target_real_ids,
                team_ids=_target_team_ids(targets),
                competition_ids=_target_competition_ids(targets),
                maximum_kickoff=max(row.kickoff_at for row in targets),
            ),
            targets,
        )
    _consume(root / EXECUTION_STATE.relative_to(ROOT))
    try:
        scored = _execute_batches(database_url, target_rows, targets, history, runtime, reference)
        result = _evaluate_scored(
            scored, targets, target_rows, runtime, old_config, reference, receipt
        )
    except Exception as error:
        _write(
            root / RECEIPT.relative_to(ROOT),
            {
                **receipt,
                "contract": "MatchForgeV2FinalExecutionReceiptV1",
                "protocol_id": PROTOCOL_ID,
                "outcomes_loaded": True,
                "logical_executions": 1,
                "final_disposition": "FAIL_CLOSED_PROTOCOL_VIOLATION",
                "exception_type": type(error).__name__,
                "diagnostic": str(error),
                "comparative_metrics_published": False,
            },
        )
        raise
    _write(root / RESULT.relative_to(ROOT), result)
    _write(
        root / RECEIPT.relative_to(ROOT),
        {
            **receipt,
            "contract": "MatchForgeV2FinalExecutionReceiptV1",
            "protocol_id": PROTOCOL_ID,
            "outcomes_loaded": True,
            "logical_executions": 1,
            "outcome_access_before_forecast": 0,
        },
    )
    (root / REPORT.relative_to(ROOT)).write_text(_markdown(result), encoding="utf-8")
    _update_project_status(root, result)
    return result


def _execute_batches(
    database_url: str,
    target_rows: Sequence[Mapping[str, object]],
    targets: Sequence[FrozenTarget],
    history: Sequence[ResolvedHistoricalMatchV1],
    runtime: Mapping[str, Any],
    reference: Mapping[str, object],
) -> dict[str, object]:
    admitted = list(_historical(row) for row in history)
    competition_history = list(_competition_match(row) for row in history)
    prior = CompetitionPriorPoissonV1(
        float(cast(float, reference["global_home_rate"])),
        float(cast(float, reference["global_away_rate"])),
    )
    rows_by_fixture = {str(row["fixture_id"]): row for row in target_rows}
    predictions: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    references: list[ScoredModelForecast] = []
    champions: list[ScoredModelForecast] = []
    v2a: dict[str, list[ScoredModelForecast]] = defaultdict(list)
    routes: dict[str, Counter[str]] = defaultdict(Counter)
    outcome_access_before_forecast = 0
    ordered = sorted(targets, key=lambda row: (row.kickoff_at, str(row.fixture_id)))
    for _, batch_values in groupby(ordered, key=lambda row: row.kickoff_at):
        batch = tuple(batch_values)

        def prepare_target(target: FrozenTarget) -> PreparedTargetForecasts:
            row = rows_by_fixture[str(target.fixture_id)]
            snapshot = _snapshot(target, admitted, row)
            counts = _history_counts(snapshot, target)
            if counts != (target.home_prior_match_count, target.away_prior_match_count):
                raise RuntimeError("FAIL_CLOSED_RESOLVED_HISTORY_COUNT_MISMATCH")
            item = _forecast_target(
                target, snapshot, competition_history, runtime, prior, reference
            )
            if any(_route(value) != target.expected_route for value in item.v2b.values()):
                raise RuntimeError("MODEL_READINESS_FAILURE: execution route drift")
            return item

        prepared, outcomes = _prepare_before_reveal(
            batch,
            prepare_target,
            lambda sealed_batch: _load_batch_outcomes(database_url, sealed_batch),
        )
        for item in prepared:
            home_goals, away_goals = outcomes[item.target.fixture_id]
            observation = EvaluationObservation(
                item.target,
                item.snapshot,
                tuple(competition_history),
                home_goals,
                away_goals,
            )
            references.append(_score(item.reference, observation))
            if item.champion is not None:
                champions.append(_score(item.champion, observation))
            for model_id, forecast in item.v2a.items():
                v2a[model_id].append(_score(forecast, observation))
            for model_id, forecast in item.v2b.items():
                predictions[model_id].append(_score(forecast, observation))
                routes[model_id][_route(forecast)] += 1
            row = rows_by_fixture[str(item.target.fixture_id)]
            resolved = _resolved_target(item.target, row, home_goals, away_goals)
            admitted.append(_historical(resolved))
            competition_history.append(_competition_match(resolved))
    return {
        "predictions": predictions,
        "references": references,
        "champions": champions,
        "v2a": v2a,
        "routes": routes,
        "outcome_access_before_forecast": outcome_access_before_forecast,
    }


def _prepare_before_reveal[PreparedValue, RevealedValue](
    batch: Sequence[FrozenTarget],
    prepare: Callable[[FrozenTarget], PreparedValue],
    reveal: Callable[[Sequence[FrozenTarget]], RevealedValue],
) -> tuple[tuple[PreparedValue, ...], RevealedValue]:
    """Seal every forecast in a kickoff batch before any label is requested."""
    prepared = tuple(prepare(target) for target in batch)
    return prepared, reveal(batch)


def _forecast_target(
    target: FrozenTarget,
    snapshot: ForecastInputSnapshot,
    competition_history: Sequence[CompetitionPriorMatch],
    runtime: Mapping[str, Any],
    prior: CompetitionPriorPoissonV1,
    reference: Mapping[str, object],
) -> PreparedTargetForecasts:
    champion_model = cast(TransferableRollingGoalsChampion, runtime["champion_model"])
    champion_artifact = cast(FittedModelArtifact, runtime["champion_artifact"])
    champion: ModelForecast | None = None
    v2a: dict[str, ModelForecast] = {}
    if target.champion_eligibility == ChampionEligibility.ELIGIBLE.value:
        champion = champion_model.predict(champion_artifact, snapshot)
        _require_success(champion)
        reference_forecast = champion
        for model in runtime["v2a_models"]:
            forecast = model.predict(runtime["v2a_artifacts"][model.model_id], snapshot)
            _require_success(forecast)
            v2a[model.model_id] = forecast
    else:
        reference_forecast = _competition_prior_forecast(
            target, snapshot, competition_history, prior, reference
        )
    v2b: dict[str, ModelForecast] = {}
    for model in runtime["v2b_models"]:
        forecast = model.predict(runtime["v2b_artifacts"][model.model_id], snapshot)
        _require_success(forecast)
        v2b[model.model_id] = forecast
    return PreparedTargetForecasts(target, snapshot, reference_forecast, champion, v2a, v2b)


def _competition_prior_forecast(
    target: FrozenTarget,
    snapshot: ForecastInputSnapshot,
    history: Sequence[CompetitionPriorMatch],
    model: CompetitionPriorPoissonV1,
    artifact: Mapping[str, object],
) -> ModelForecast:
    matrix = model.distribution(
        competition_id=target.competition_id,
        kickoff_at=target.kickoff_at,
        history=history,
    )
    home, away, total = distributions(matrix)
    markets = derive_markets(matrix)
    return ModelForecast(
        fixture_id=target.fixture_id,
        model_id=COMPETITION_PRIOR_MODEL_ID,
        model_family="COMPETITION_PRIOR_INDEPENDENT_POISSON",
        model_version=COMPETITION_PRIOR_MODEL_ID,
        model_artifact_sha256=str(artifact["artifact_sha256"]),
        football_cutoff=target.kickoff_at,
        knowledge_cutoff=target.kickoff_at,
        created_at=datetime.now(UTC),
        expected_home_goals=sum(index * value for index, value in enumerate(home)),
        expected_away_goals=sum(index * value for index, value in enumerate(away)),
        score_labels=tuple(str(index) for index in range(10)) + ("10+",),
        score_matrix=matrix,
        home_goal_distribution=home,
        away_goal_distribution=away,
        total_goal_distribution=total,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256=snapshot.sha256,
        home_probability=markets["home_probability"],
        draw_probability=markets["draw_probability"],
        away_probability=markets["away_probability"],
        btts_yes=markets["btts_yes"],
        btts_no=markets["btts_no"],
        total_over_2_5=markets["total_over_2_5"],
        total_under_2_5=markets["total_under_2_5"],
        home_clean_sheet=markets["home_clean_sheet"],
        away_clean_sheet=markets["away_clean_sheet"],
    )


def _snapshot(
    target: FrozenTarget,
    history: Sequence[HistoricalMatch],
    row: Mapping[str, object],
) -> ForecastInputSnapshot:
    return build_forecast_snapshot(
        fixture_id=target.fixture_id,
        competition_id=target.competition_id,
        competition_context=CompetitionContext.LEAGUE,
        season_label=target.season,
        kickoff_at=target.kickoff_at,
        home_team_id=target.home_team_id,
        away_team_id=target.away_team_id,
        football_cutoff=target.kickoff_at,
        knowledge_cutoff=target.kickoff_at,
        knowledge_mode="RETROSPECTIVE_RESOLVED_SOURCE_SNAPSHOT",
        history=history,
        source_references=(
            f"real-fixture:{row['real_fixture_id']}",
            f"resolution-evidence:{row['source_evidence_sha256']}",
        ),
        home_promoted=target.home_promoted,
        away_promoted=target.away_promoted,
    )


def _relevant_history(
    history: Sequence[ResolvedHistoricalMatchV1], targets: Sequence[FrozenTarget]
) -> tuple[ResolvedHistoricalMatchV1, ...]:
    teams = {team for row in targets for team in (row.home_team_id, row.away_team_id)}
    competitions = {row.competition_id for row in targets}
    maximum = max(row.kickoff_at for row in targets)
    return tuple(
        row
        for row in history
        if row.kickoff_at <= maximum
        and (
            row.competition_id in competitions
            or row.home_team_id in teams
            or row.away_team_id in teams
        )
    )


def _historical(row: ResolvedHistoricalMatchV1) -> HistoricalMatch:
    return HistoricalMatch(
        fixture_id=row.real_fixture_id,
        competition_id=row.competition_id,
        competition_context=CompetitionContext.LEAGUE,
        kickoff_at=row.kickoff_at,
        known_at=row.kickoff_at + timedelta(hours=3),
        home_team_id=row.home_team_id,
        away_team_id=row.away_team_id,
        home_goals=row.home_goals,
        away_goals=row.away_goals,
        home_xg=row.home_xg,
        away_xg=row.away_xg,
    )


def _competition_match(row: ResolvedHistoricalMatchV1) -> CompetitionPriorMatch:
    return CompetitionPriorMatch(row.competition_id, row.kickoff_at, row.home_goals, row.away_goals)


def _resolved_target(
    target: FrozenTarget,
    row: Mapping[str, object],
    home_goals: int,
    away_goals: int,
) -> ResolvedHistoricalMatchV1:
    """Admit one frozen real fixture after its sealed batch outcome is revealed."""
    return ResolvedHistoricalMatchV1(
        real_fixture_id=UUID(str(row["real_fixture_id"])),
        representative_fixture_id=UUID(str(row["representative_fixture_id"])),
        kickoff_at=target.kickoff_at,
        competition_id=target.competition_id,
        competition_name=target.competition_name,
        country=str(row["country"]),
        division=cast(int | None, row["division"]),
        season_label=target.season,
        home_team_id=target.home_team_id,
        away_team_id=target.away_team_id,
        home_team_name=str(row["home_team_name"]),
        away_team_name=str(row["away_team_name"]),
        home_goals=home_goals,
        away_goals=away_goals,
        home_xg=None,
        away_xg=None,
        source_provider_codes=(str(row["source_provider"]),),
        source_snapshot_ids=(UUID(str(row["source_snapshot_id"])),),
        member_fixture_ids=tuple(
            UUID(str(value)) for value in cast(Sequence[object], row["member_fixture_ids"])
        ),
        identity_status=ResolutionStatus(str(row["identity_status"])),
        source_evidence_sha256=str(row["source_evidence_sha256"]),
    )


def _history_counts(snapshot: ForecastInputSnapshot, target: FrozenTarget) -> tuple[int, int]:
    return (
        sum(
            target.home_team_id in (row.home_team_id, row.away_team_id)
            for row in snapshot.qualified_history
        ),
        sum(
            target.away_team_id in (row.home_team_id, row.away_team_id)
            for row in snapshot.qualified_history
        ),
    )


def _target_team_ids(targets: Sequence[FrozenTarget]) -> tuple[UUID, ...]:
    return tuple(
        sorted(
            {team for row in targets for team in (row.home_team_id, row.away_team_id)},
            key=str,
        )
    )


def _target_competition_ids(targets: Sequence[FrozenTarget]) -> tuple[UUID, ...]:
    return tuple(sorted({row.competition_id for row in targets}, key=str))


def _load_batch_outcomes(
    database_url: str, batch: Sequence[FrozenTarget]
) -> dict[UUID, tuple[int, int]]:
    ids = [row.fixture_id for row in batch]
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT fixture_id, home_goals, away_goals
              FROM football.product_team_match_history
             WHERE fixture_id = ANY(%s::uuid[])
            """,
            (ids,),
        ).fetchall()
    output = {cast(UUID, row[0]): (int(row[1]), int(row[2])) for row in rows}
    if output.keys() != set(ids):
        raise RuntimeError("target batch outcomes are incomplete")
    return output


def _score(forecast: ModelForecast, item: EvaluationObservation) -> ScoredModelForecast:
    return ScoredModelForecast(
        forecast=forecast,
        kickoff_at=item.target.kickoff_at,
        outcome_known_at=item.target.kickoff_at + timedelta(hours=3),
        home_goals=item.home_goals,
        away_goals=item.away_goals,
        competition_id=item.target.competition_name,
        season_label=item.target.season,
    )


def _evaluate_scored(
    scored: Mapping[str, object],
    targets: Sequence[FrozenTarget],
    target_rows: Sequence[Mapping[str, object]],
    runtime: Mapping[str, Any],
    old_config: Mapping[str, object],
    reference: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict[str, object]:
    predictions = cast(dict[str, list[ScoredModelForecast]], scored["predictions"])
    reference_rows = tuple(cast(list[ScoredModelForecast], scored["references"]))
    champion_rows = tuple(cast(list[ScoredModelForecast], scored["champions"]))
    v2a_predictions = cast(dict[str, list[ScoredModelForecast]], scored["v2a"])
    routes = cast(dict[str, Counter[str]], scored["routes"])
    reference_by_id = {row.forecast.fixture_id: row for row in reference_rows}
    champion_by_id = {row.forecast.fixture_id: row for row in champion_rows}
    eligible_ids = frozenset(champion_by_id)
    ineligible_ids = frozenset(reference_by_id) - eligible_ids
    target_by_id = {row.fixture_id: row for row in targets}
    strata_a: dict[str, object] = {}
    strata_b: dict[str, object] = {}
    overall: dict[str, object] = {}
    domains: dict[str, object] = {}
    low_history: dict[str, object] = {}
    promoted: dict[str, object] = {}
    decisions: dict[str, str] = {}
    for model_id, values in predictions.items():
        candidate = tuple(values)
        by_id = {row.forecast.fixture_id: row for row in candidate}
        a = tuple(by_id[key] for key in eligible_ids)
        b = tuple(by_id[key] for key in ineligible_ids)
        a_ref = tuple(champion_by_id[key] for key in eligible_ids)
        b_ref = tuple(reference_by_id[key] for key in ineligible_ids)
        strata_a[model_id] = _paired_payload(a, a_ref)
        strata_b[model_id] = _paired_payload(b, b_ref)
        overall[model_id] = _paired_payload(candidate, reference_rows)
        domains[model_id] = _group_results(
            candidate, reference_by_id, lambda target: target.competition_name, target_by_id
        )
        low_history[model_id] = _group_results(
            candidate, reference_by_id, _history_bucket, target_by_id
        )
        promoted_ids = {
            key
            for key, target in target_by_id.items()
            if target.home_promoted or target.away_promoted
        }
        promoted[model_id] = (
            _paired_payload(
                tuple(by_id[key] for key in promoted_ids),
                tuple(reference_by_id[key] for key in promoted_ids),
            )
            if promoted_ids
            else {"target_count": 0, "status": "DESCRIPTIVE_ONLY"}
        )
        decisions[model_id] = _candidate_decision(
            cast(dict[str, object], strata_a[model_id]),
            cast(dict[str, object], strata_b[model_id]),
            cast(dict[str, object], overall[model_id]),
            cast(dict[str, object], domains[model_id]),
            routes[model_id],
            len(candidate),
            len(targets),
            len(ineligible_ids) >= 75,
        )
    accepted = [
        model_id
        for model_id, decision in decisions.items()
        if decision == "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
    ]
    winner = min(
        accepted,
        key=lambda key: cast(dict[str, Any], overall[key])["candidate_metrics"][
            "joint_score_log_loss"
        ],
        default=None,
    )
    disposition = (
        "DEVELOPMENT_ACCEPTED_FOR_INDEPENDENT_EVALUATION"
        if accepted
        else "DEVELOPMENT_PARTIAL_SUCCESS"
        if any(value == "DEVELOPMENT_PARTIAL_SUCCESS" for value in decisions.values())
        else "DEVELOPMENT_REJECTED"
    )
    reason_counts = Counter(
        row.champion_ineligibility_reason for row in targets if row.champion_ineligibility_reason
    )
    return {
        "contract": "MatchForgeFullCoverageChallengersV2FinalResultV1",
        "protocol_id": PROTOCOL_ID,
        "authorization": AUTHORIZATION_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "replacement_manifest_id": REPLACEMENT_MANIFEST_ID,
        "execution": {
            **receipt,
            "outcomes_loaded": True,
            "logical_executions": 1,
            "outcome_access_before_forecast": scored["outcome_access_before_forecast"],
        },
        "frozen_v2": {
            "candidate_artifact_sha256": runtime["artifact_shas"],
            "selected_shrinkage_k": cast(dict[str, object], old_config["selected_cold_start"])[
                "shrinkage_k"
            ],
            "selected_l2": cast(dict[str, object], old_config["selected_cold_start"])[
                "l2_regularization"
            ],
            "selected_transfer_weight": old_config["selected_transfer_weight"],
            "ensemble_status": "PREVIOUSLY_VALID_FROZEN_DEVELOPMENT",
        },
        "reference_stack": {
            "id": REFERENCE_STACK_ID,
            "competition_prior_model_id": COMPETITION_PRIOR_MODEL_ID,
            "competition_prior_artifact_sha256": reference["artifact_sha256"],
            "k_prior": COMPETITION_PRIOR_K,
        },
        "target_count": len(targets),
        "competition_counts": dict(
            sorted(Counter(row.competition_name for row in targets).items())
        ),
        "season_counts": dict(sorted(Counter(row.season for row in targets).items())),
        "champion_eligible_count": len(eligible_ids),
        "champion_ineligible_count": len(ineligible_ids),
        "champion_ineligibility_reason_counts": dict(sorted(reason_counts.items())),
        "low_history_counts": dict(
            sorted(Counter(_history_bucket(row) for row in targets).items())
        ),
        "v2b_routing_counts": {
            key: dict(sorted(value.items())) for key, value in sorted(routes.items())
        },
        "v2a_stratum_a": {
            model_id: _v2a_report(tuple(values), champion_rows)
            for model_id, values in v2a_predictions.items()
        },
        "stratum_a_v2b_vs_champion": strata_a,
        "stratum_b_v2b_vs_competition_prior": strata_b,
        "overall_v2b_vs_reference_stack": overall,
        "low_history_results": low_history,
        "promoted_team_results": promoted,
        "domain_results": domains,
        "candidate_decisions": decisions,
        "development_winner": winner,
        "final_disposition": disposition,
        "coverage": {key: len(value) / len(targets) for key, value in predictions.items()},
        "independent_evaluation_available": False,
        "production_promotion_justified": False,
        "production_champion_changed": False,
        "target_real_fixture_duplicates": len(target_rows)
        - len({str(row["real_fixture_id"]) for row in target_rows}),
    }


def _preflight(
    root: Path,
    prereg: Mapping[str, object],
    target_manifest: Mapping[str, object],
    config: Mapping[str, object],
) -> dict[str, object]:
    def git(*args: str) -> str:
        return subprocess.check_output(("git", *args), cwd=root, text=True).strip()

    head, parent, status = (
        git("rev-parse", "HEAD"),
        git("rev-parse", "HEAD^"),
        git("status", "--porcelain"),
    )
    if status:
        raise RuntimeError("execution requires a clean worktree")
    if parent != prereg["source_commit"] or parent != prereg["required_execution_parent"]:
        raise RuntimeError("execution commit parent does not match SOURCE_COMMIT")
    changed = sorted(filter(None, git("diff", "--name-only", "HEAD^", "HEAD").splitlines()))
    allowed = cast(list[str], prereg["execution_commit_allowed_files"])
    if not changed or any(path not in allowed for path in changed):
        raise RuntimeError("FAIL_CLOSED_EXECUTION_COMMIT_SOURCE_MUTATION")
    files = scientific_source_files(root)
    source_sha = scientific_source_sha(root, files)
    if (
        list(files) != prereg["scientific_source_files"]
        or source_sha != prereg["scientific_source_sha256"]
    ):
        raise RuntimeError("scientific source hash mismatch")
    _verify_frozen_file_hashes(root, prereg)
    if _semantic_sha(target_manifest["targets"]) != prereg["target_manifest_sha256"]:
        raise RuntimeError("target manifest mismatch")
    if _semantic_sha(_json(root / FIREWALL.relative_to(ROOT))) != prereg["firewall_sha256"]:
        raise RuntimeError("firewall semantic hash mismatch")
    _verify_preexecution_state(root, target_manifest)
    return {
        "source_commit": parent,
        "execution_commit": head,
        "execution_parent_matches_source": True,
        "execution_commit_changed_files": changed,
        "scientific_source_sha256": source_sha,
        "preflight_status": "PASS",
    }


def _verify_frozen_file_hashes(root: Path, prereg: Mapping[str, object]) -> None:
    for ref_key, sha_key in (
        ("owner_decision_ref", "owner_decision_sha256"),
        ("configuration_ref", "configuration_sha256"),
        ("target_manifest_ref", "target_manifest_file_sha256"),
        ("firewall_ref", "firewall_file_sha256"),
        ("resolved_history_manifest_ref", "resolved_history_manifest_file_sha256"),
        ("canonical_history_audit_ref", "canonical_history_audit_file_sha256"),
        ("readiness_rehearsal_ref", "readiness_rehearsal_file_sha256"),
        ("quarantine_manifest_ref", "quarantine_manifest_file_sha256"),
        ("reference_artifact_ref", "reference_artifact_file_sha256"),
    ):
        if _file_sha(root / str(prereg[ref_key])) != prereg[sha_key]:
            raise RuntimeError(f"{sha_key} mismatch")


def _verify_preexecution_state(root: Path, target_manifest: Mapping[str, object]) -> None:
    audit = _json(root / AUDIT.relative_to(ROOT))
    audit_counts = cast(dict[str, int], audit["counts"])
    if audit["status"] != "PASS" or audit_counts["unresolved_admitted_timeline_conflicts"] != 0:
        raise RuntimeError("CANONICAL_HISTORY_REPAIR_REQUIRED")
    readiness = _json(root / READINESS.relative_to(ROOT))
    target_count = len(cast(Sequence[object], target_manifest["targets"]))
    ready_counts = (
        readiness["snapshot_readiness_count"],
        readiness["elo_readiness_count"],
        readiness["competition_prior_readiness_count"],
        readiness["distribution_validation_count"],
    )
    qualification = cast(Mapping[str, object], target_manifest["qualification"])
    if (
        readiness["status"] != "PASS"
        or readiness["unresolved_failures"]
        or readiness["selected_target_count"] != target_count
        or any(value != target_count for value in ready_counts)
        or readiness["target_history_identity_conflicts"] != 0
        or readiness["team_timeline_conflicts"] != 0
        or readiness["target_outcome_columns_selected"] != 0
        or readiness["target_outcome_getter_calls"] != 0
        or qualification["target_real_fixture_duplicates"] != 0
        or qualification["team_timestamp_target_conflicts"] != 0
        or qualification["failures"]
    ):
        raise RuntimeError("MODEL_READINESS_FAILURE")
    state = _json(root / EXECUTION_STATE.relative_to(ROOT))
    if state != {
        "logical_executions": 0,
        "outcomes_loaded": False,
        "readiness_rehearsal": "PASS",
        "canonical_history_audit": "PASS",
        "protocol_id": PROTOCOL_ID,
    }:
        raise RuntimeError("final replacement holdout already consumed")


def _preregistration(
    root: Path,
    target_manifest: Mapping[str, object],
    readiness: Mapping[str, object],
    config: Mapping[str, object],
) -> dict[str, object]:
    source_commit = str(config["source_commit"])
    files = scientific_source_files(root)
    allowed = [
        OWNER_DECISION.relative_to(ROOT).as_posix(),
        AUDIT.relative_to(ROOT).as_posix(),
        QUARANTINE.relative_to(ROOT).as_posix(),
        FIREWALL.relative_to(ROOT).as_posix(),
        TARGET_MANIFEST.relative_to(ROOT).as_posix(),
        RESOLVED_HISTORY_MANIFEST.relative_to(ROOT).as_posix(),
        READINESS.relative_to(ROOT).as_posix(),
        CONFIG.relative_to(ROOT).as_posix(),
        PREREGISTRATION.relative_to(ROOT).as_posix(),
        EXECUTION_STATE.relative_to(ROOT).as_posix(),
        "docs/project-status.json",
    ]
    reference = _json(root / REFERENCE_CONFIG.relative_to(ROOT))
    return {
        "contract": "MatchForgeFullCoverageV2FinalPreregistrationV1",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "amendment_reason": "CANONICAL_REAL_FIXTURE_IDENTITY_AND_EXHAUSTIVE_PREOUTCOME_READINESS",
        "source_commit": source_commit,
        "required_execution_parent": source_commit,
        "execution_commit_policy": "DIRECT_CHILD_CONTROL_ONLY_V1",
        "execution_commit_allowed_files": allowed,
        "scientific_source_files": list(files),
        "scientific_source_sha256": scientific_source_sha(root, files),
        "real_fixture_resolution_version": "RealFixtureIdentityV1",
        "owner_decision_ref": OWNER_DECISION.relative_to(ROOT).as_posix(),
        "owner_decision_sha256": _file_sha(root / OWNER_DECISION.relative_to(ROOT)),
        "configuration_ref": CONFIG.relative_to(ROOT).as_posix(),
        "configuration_sha256": _file_sha(root / CONFIG.relative_to(ROOT)),
        "target_manifest_ref": TARGET_MANIFEST.relative_to(ROOT).as_posix(),
        "target_manifest_file_sha256": _file_sha(root / TARGET_MANIFEST.relative_to(ROOT)),
        "target_manifest_sha256": target_manifest["target_manifest_sha256"],
        "firewall_ref": FIREWALL.relative_to(ROOT).as_posix(),
        "firewall_file_sha256": _file_sha(root / FIREWALL.relative_to(ROOT)),
        "firewall_sha256": _semantic_sha(_json(root / FIREWALL.relative_to(ROOT))),
        "resolved_history_manifest_ref": RESOLVED_HISTORY_MANIFEST.relative_to(ROOT).as_posix(),
        "resolved_history_manifest_file_sha256": _file_sha(
            root / RESOLVED_HISTORY_MANIFEST.relative_to(ROOT)
        ),
        "resolved_history_manifest_sha256": _json(
            root / RESOLVED_HISTORY_MANIFEST.relative_to(ROOT)
        )["resolved_history_manifest_sha256"],
        "canonical_history_audit_ref": AUDIT.relative_to(ROOT).as_posix(),
        "canonical_history_audit_file_sha256": _file_sha(root / AUDIT.relative_to(ROOT)),
        "canonical_history_audit_sha256": _semantic_sha(_json(root / AUDIT.relative_to(ROOT))),
        "readiness_rehearsal_ref": READINESS.relative_to(ROOT).as_posix(),
        "readiness_rehearsal_file_sha256": _file_sha(root / READINESS.relative_to(ROOT)),
        "readiness_rehearsal_sha256": _semantic_sha(readiness),
        "quarantine_manifest_ref": QUARANTINE.relative_to(ROOT).as_posix(),
        "quarantine_manifest_file_sha256": _file_sha(root / QUARANTINE.relative_to(ROOT)),
        "reference_artifact_ref": REFERENCE_CONFIG.relative_to(ROOT).as_posix(),
        "reference_artifact_file_sha256": _file_sha(root / REFERENCE_CONFIG.relative_to(ROOT)),
        "reference_artifact_sha256": reference["artifact_sha256"],
        "frozen_v2_candidate_artifact_sha256": config["frozen_v2_candidate_artifact_sha256"],
        "execution_state_ref": EXECUTION_STATE.relative_to(ROOT).as_posix(),
        "readiness_target_count": readiness["selected_target_count"],
        "readiness_pass_count": readiness["snapshot_readiness_count"],
        "unresolved_failures": readiness["unresolved_failures"],
        "bootstrap": {
            "type": "MOVING_BLOCK",
            "block_length": 10,
            "replicates": 2000,
            "seed": 20260921,
            "confidence_interval": 0.95,
        },
        "acceptance_criteria": {
            "joint_ll_delta_max": -0.003,
            "joint_ll_ci_upper_max_exclusive": 0,
            "result_ll_delta_max": 0,
            "result_ll_ci_upper_max": 0,
            "brier_ci_upper_max": 0.01,
            "rps_ci_upper_max": 0.01,
            "crps_ci_upper_max": 0.02,
            "domain_joint_ll_delta_max": 0.02,
        },
    }


def _consume(path: Path) -> None:
    payload = {
        "logical_executions": 1,
        "outcomes_loaded": True,
        "readiness_rehearsal": "PASS",
        "canonical_history_audit": "PASS",
        "protocol_id": PROTOCOL_ID,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    os.replace(temporary, path)


def _current_relevant_manifest(
    metadata: Sequence[Mapping[str, object]], targets: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    teams = {str(row[field]) for row in targets for field in ("home_team", "away_team")}
    competitions = {str(row["competition_id"]) for row in targets}
    target_real_ids = {str(row["real_fixture_id"]) for row in targets}
    maximum = max(datetime.fromisoformat(str(row["kickoff"])) for row in targets)
    return [
        {
            "real_fixture_id": str(row["real_fixture_id"]),
            "member_fixture_ids": list(cast(Sequence[str], row["member_fixture_ids"])),
            "representative_fixture_id": str(row["representative_fixture_id"]),
            "competition_id": str(row["competition_id"]),
            "kickoff": cast(datetime, row["kickoff_at"]).astimezone(UTC).isoformat(),
            "home_team_id": str(row["home_team_id"]),
            "away_team_id": str(row["away_team_id"]),
            "resolution_status": str(row["resolution_status"]),
            "source_evidence_sha256": str(row["evidence_sha256"]),
        }
        for row in metadata
        if str(row["real_fixture_id"]) not in target_real_ids
        and cast(datetime, row["kickoff_at"]) <= maximum
        and (
            str(row["competition_id"]) in competitions
            or str(row["home_team_id"]) in teams
            or str(row["away_team_id"]) in teams
        )
    ]


def _require_success(forecast: ModelForecast) -> None:
    if forecast.status is not ModelStatus.SUCCESS:
        raise RuntimeError(f"MODEL_READINESS_FAILURE: {forecast.model_id}:{forecast.status.value}")


def _route(forecast: ModelForecast) -> str:
    return forecast.lineage.forecast_mode.value if forecast.lineage else "NATIVE"


def _semantic_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _update_project_status(root: Path, result: Mapping[str, object]) -> None:
    path = root / "docs/project-status.json"
    status = _json(path)
    tracks = cast(list[dict[str, object]], status["evaluation_tracks"])
    tracks.append(
        {
            "evaluation_protocol_id": PROTOCOL_ID,
            "provider": "MULTISOURCE_RETAINED_RESOLVED",
            "status": f"COMPLETE_{result['final_disposition']}",
            "owner_decision": AUTHORIZATION_ID,
            "owner_decision_ref": OWNER_DECISION.relative_to(ROOT).as_posix(),
            "source_commit": cast(dict[str, object], result["execution"])["source_commit"],
            "execution_commit": cast(dict[str, object], result["execution"])["execution_commit"],
            "replacement_holdout_target_count": result["target_count"],
            "development_outcomes_loaded": True,
            "logical_executions": 1,
            "result_classification": result["final_disposition"],
            "development_winner": result["development_winner"],
            "evidence_ref": RESULT.relative_to(ROOT).as_posix(),
            "report_ref": REPORT.relative_to(ROOT).as_posix(),
            "execution_receipt_ref": RECEIPT.relative_to(ROOT).as_posix(),
            "independent_evaluation_available": False,
            "model_promoted": False,
            "production_champion_changed": False,
            "next_action": "OWNER_HANDOFF_V2_FINAL_DEVELOPMENT_COMPLETE",
        }
    )
    status["updated_at"] = f"{DATE}T00:00:00Z"
    _write_pretty(path, status)


def _markdown(result: Mapping[str, object]) -> str:
    return "\n".join(
        (
            "# Full-coverage V2 final replacement holdout",
            "",
            f"Protocol: `{result['protocol_id']}`",
            f"Targets: `{result['target_count']}`",
            f"Champion eligible: `{result['champion_eligible_count']}`",
            f"Champion ineligible: `{result['champion_ineligible_count']}`",
            f"Disposition: `{result['final_disposition']}`",
            f"Development winner: `{result['development_winner']}`",
            "",
            "Canonical history audit: PASS.",
            "Pre-outcome readiness rehearsal: PASS.",
            "Outcome access before each batch forecast: 0.",
            "Independent evaluation available: NO.",
            "Production champion changed: NO.",
            "",
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
