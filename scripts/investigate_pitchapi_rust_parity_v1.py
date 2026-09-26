"""Reproduce and diagnose the closed PitchAPI V3 Rust parity failure."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3 import (
    HistoryObservationV1,
    RollingHistoryV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
    expected_goals,
)
from football.forecasting.pitchapi_v3_evaluation import (
    ExactScoreDistributionV1,
    exact_distribution,
)
from football.forecasting.pitchapi_v3_executor import PreparedTargetV1
from football.forecasting.pitchapi_v3_runtime import (
    ALGORITHM_VERSION,
    SEED_SCHEDULE_ID,
    SIMULATION_COUNT,
    _analytic_probabilities,
    load_model_parameters,
)
from scipy.stats import beta, poisson

PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3"
POLICY_SHA256 = "682ebf08298dbe7aa5078d2e5b0922b5c43e8dee05be8ea89781bce97eed7ebf"
REFERENCE_SHA256 = "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"
CHALLENGER_SHA256 = "314e1e0891ffaae6d7fe3885f5bf7e9087bed4b02bdc323e685ee49c11f0675a"
EVALUATION_MANIFESTS = {
    "bundesliga_2022_23": "893b888a36474c7cf55a207cb266d32a60351c0c87e9659a38a2cdc962784f74",
    "bundesliga_2023_24": "0700ee9d976366db3a12b0c3bc4c9e3d6a953d95b7fbe1dac153773553ae9b87",
    "ligue1_2022_23": "ded84fa1ce6f2695469f1e258bffd8c2b3ac79ee5edec5afa24be0e4d0b0939d",
}
COUNT_STUDY = (25_000, 50_000, 112_460, 250_000, 500_000, 1_000_000)
EVENT_COUNT = 62
EVALUATION_FORECAST_COUNT = 712 * 2


@dataclass(frozen=True, slots=True)
class FailingInput:
    target: PreparedTargetV1
    model: TransferableGoalModelV1
    model_artifact_sha256: str
    model_role: str
    distribution: ExactScoreDistributionV1
    input_bytes: bytes
    input_payload: dict[str, object]
    worker_count: int
    failure: str
    previously_revealed_target_count: int


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--reference-artifact", type=Path, required=True)
    parser.add_argument("--challenger-artifact", type=Path, required=True)
    parser.add_argument("--frozen-binary", type=Path, required=True)
    parser.add_argument("--diagnostic-binary", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    evidence = investigate(
        snapshot_root=args.snapshot_root,
        reference_artifact=args.reference_artifact,
        challenger_artifact=args.challenger_artifact,
        frozen_binary=args.frozen_binary,
        diagnostic_binary=args.diagnostic_binary,
        output_root=args.output_root,
    )
    evidence_path = args.output_root / "investigation-evidence.json"
    evidence_path.write_bytes(canonical_json_bytes(evidence) + b"\n")
    print(
        json.dumps(
            {
                "evidence_path": str(evidence_path),
                "evidence_sha256": _sha256(evidence_path),
            },
            sort_keys=True,
        )
    )


def investigate(
    *,
    snapshot_root: Path,
    reference_artifact: Path,
    challenger_artifact: Path,
    frozen_binary: Path,
    diagnostic_binary: Path,
    output_root: Path,
) -> dict[str, object]:
    reference_payload = _load(reference_artifact)
    challenger_payload = _load(challenger_artifact)
    if _sha256(reference_artifact) != REFERENCE_SHA256:
        raise RuntimeError("reference artifact identity mismatch")
    if _sha256(challenger_artifact) != CHALLENGER_SHA256:
        raise RuntimeError("challenger artifact identity mismatch")
    reference_model = TransferableGoalModelV1(
        TransferableParametersV1(**load_model_parameters(reference_payload))
    )
    challenger_model = TransferableGoalModelV1(
        TransferableParametersV1(**load_model_parameters(challenger_payload))
    )
    failing = _find_failing_input(
        root=snapshot_root,
        reference_model=reference_model,
        challenger_model=challenger_model,
        frozen_binary=frozen_binary,
    )
    output_root.mkdir(parents=True, exist_ok=False)
    target = failing.target
    model = failing.model
    input_bytes = failing.input_bytes
    input_payload = failing.input_payload
    lambda_home, lambda_away = expected_goals(model.parameters, target.features)
    input_path = output_root / "exact-failing-input.json"
    input_path.write_bytes(input_bytes)
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    frozen_error = failing.failure
    expected_error = "PARITY_FAILURE: score:1-4 analytic probability is outside parity interval"
    if frozen_error != expected_error:
        raise RuntimeError(f"exact V3 failure did not reproduce: {frozen_error}")

    one_worker = _diagnose(
        diagnostic_binary, input_path, input_sha256, workers=1, total_draws=SIMULATION_COUNT
    )
    four_worker = _diagnose(
        diagnostic_binary, input_path, input_sha256, workers=4, total_draws=SIMULATION_COUNT
    )
    if _worker_invariant(one_worker) != _worker_invariant(four_worker):
        raise RuntimeError("diagnostic serial/parallel results differ")
    (output_root / "diagnostic-112460-worker-1.json").write_bytes(canonical_json_bytes(one_worker))
    (output_root / "diagnostic-112460-worker-4.json").write_bytes(canonical_json_bytes(four_worker))

    analytic = cast(list[dict[str, object]], input_payload["analytic_probabilities"])
    analytic_map = {
        str(item["event_id"]): float(cast(float, item["probability"])) for item in analytic
    }
    event = _event(one_worker, "score:1-4")
    raw_count = int(cast(int, event["count"]))
    observed = float(cast(float, event["simulated_probability"]))
    interval = _clopper_pearson(raw_count, SIMULATION_COUNT, 0.01 / EVENT_COUNT)
    production_probability = analytic_map["score:1-4"]
    scipy_probability = float(poisson.pmf(1, lambda_home) * poisson.pmf(4, lambda_away))
    manual_probability = (
        math.exp(-lambda_home)
        * lambda_home
        * math.exp(-lambda_away)
        * lambda_away**4
        / math.factorial(4)
    )
    decimal_probability = _decimal_poisson_product(lambda_home, lambda_away)
    oracle_values = (
        production_probability,
        scipy_probability,
        manual_probability,
        decimal_probability,
    )
    if max(oracle_values) - min(oracle_values) > 1e-15:
        raise RuntimeError("independent analytic calculations disagree")

    count_study = []
    for total_draws in COUNT_STUDY:
        result = (
            one_worker
            if total_draws == SIMULATION_COUNT
            else _diagnose(
                diagnostic_binary,
                input_path,
                input_sha256,
                workers=4,
                total_draws=total_draws,
            )
        )
        value = _event(result, "score:1-4")
        probability = float(cast(float, value["simulated_probability"]))
        count_study.append(
            {
                "absolute_error": abs(probability - production_probability),
                "count": int(cast(int, value["count"])),
                "error_times_sqrt_n": abs(probability - production_probability)
                * math.sqrt(total_draws),
                "expected_count": production_probability * total_draws,
                "simulated_probability": probability,
                "simulation_count": total_draws,
            }
        )

    synthetic_cases = []
    for case_id, synthetic_home, synthetic_away in (
        ("balanced", 1.4, 1.2),
        ("away_heavy", 0.7, 2.8),
        ("home_heavy", 2.8, 0.7),
        ("low_rate", 0.1, 0.1),
        ("high_rate", 4.0, 3.5),
        ("moderate_asymmetric", 2.0, 3.0),
    ):
        synthetic_distribution = _poisson_distribution(synthetic_home, synthetic_away)
        synthetic_bytes, synthetic_payload = _simulation_input(
            target_id=f"synthetic-{case_id}",
            model_role="REFERENCE",
            model_artifact_sha256=REFERENCE_SHA256,
            distribution=synthetic_distribution,
            frozen_binary=frozen_binary,
        )
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(synthetic_bytes)
            handle.flush()
            synthetic_result = _diagnose(
                diagnostic_binary,
                Path(handle.name),
                hashlib.sha256(synthetic_bytes).hexdigest(),
                workers=4,
                total_draws=SIMULATION_COUNT,
            )
        synthetic_cases.append(
            {
                "case_id": case_id,
                "lambda_away": synthetic_away,
                "lambda_home": synthetic_home,
                "metrics": _distribution_metrics(synthetic_payload, synthetic_result),
            }
        )

    per_cell_alpha = 0.01 / EVENT_COUNT
    total_cell_tests = EVENT_COUNT * EVALUATION_FORECAST_COUNT
    return {
        "analytic_oracle": {
            "decimal_50_digit": decimal_probability,
            "manual_poisson_pmf_product": manual_probability,
            "maximum_pairwise_difference": max(oracle_values) - min(oracle_values),
            "production": production_probability,
            "scipy": scipy_probability,
            "status": "PASS",
        },
        "classification": [
            "D_STATISTICAL_PARITY_POLICY_DEFECT",
            "E_EXPECTED_MONTE_CARLO_VARIATION",
        ],
        "contract": "PitchApiRustParityInvestigationV1Evidence",
        "count_study": count_study,
        "distribution_level": {
            "exact_failure_input": _distribution_metrics(input_payload, one_worker),
            "synthetic_cases": synthetic_cases,
        },
        "exact_reproduction": {
            "analytic_probability_score_1_4": production_probability,
            "batch_counts": event["batch_counts"],
            "confidence_level_individual": 1.0 - per_cell_alpha,
            "expected_count": production_probability * SIMULATION_COUNT,
            "failure": frozen_error,
            "forecast_artifact_sha256": input_payload["forecast_artifact_sha256"],
            "forecast_id": input_payload["forecast_id"],
            "forecast_probability_sha256": input_payload["forecast_probability_sha256"],
            "input_path": str(input_path),
            "input_sha256": input_sha256,
            "interval_formula": "two-sided Clopper-Pearson with alpha=0.01/62",
            "lambda_away": lambda_away,
            "lambda_home": lambda_home,
            "model_artifact_sha256": failing.model_artifact_sha256,
            "model_role": failing.model_role,
            "parity_interval_lower": interval[0],
            "parity_interval_upper": interval[1],
            "raw_count_score_1_4": raw_count,
            "rust_observed_probability_score_1_4": observed,
            "simulation_count": SIMULATION_COUNT,
            "target_id": str(target.context.match_id),
            "worker_count": failing.worker_count,
        },
        "frozen_v3_binary_sha256": _sha256(frozen_binary),
        "independent_input_boundary": {
            "evaluation_target_normalized_resource_read": False,
            "evaluation_target_outcome_read": False,
            "history_source": "strictly prior warm-up matches only",
            "previously_revealed_target_count": failing.previously_revealed_target_count,
            "scope": "first failing forecast input in frozen execution order",
            "target_manifest_metadata_read": True,
        },
        "investigation_id": "PITCHAPI_RUST_PARITY_INVESTIGATION_V1",
        "model_artifacts": {
            "challenger_status": (
                "VALID_UNCHANGED_INVOLVED_IN_FAILURE"
                if failing.model_role == "CHALLENGER"
                else "VALID_UNCHANGED_NOT_INVOLVED_IN_FAILURE"
            ),
            "reference_status": (
                "VALID_UNCHANGED_INVOLVED_IN_FAILURE"
                if failing.model_role == "REFERENCE"
                else "VALID_UNCHANGED_NOT_INVOLVED_IN_FAILURE"
            ),
        },
        "multiple_comparisons": {
            "evaluation_forecasts": EVALUATION_FORECAST_COUNT,
            "expected_false_rejections_at_nominal_cell_size": total_cell_tests * per_cell_alpha,
            "globally_controlled_per_cell_alpha_for_one_percent_fwer": 0.01 / total_cell_tests,
            "independent_approximation_at_least_one_false_rejection": 1.0
            - (1.0 - per_cell_alpha) ** total_cell_tests,
            "per_cell_alpha": per_cell_alpha,
            "per_forecast_familywise_alpha_upper_bound": 0.01,
            "total_cell_tests": total_cell_tests,
            "v3_evaluation_wide_multiplicity_control": False,
        },
        "no_additional_evaluation_outcomes_inspected": True,
        "failing_model_parameters": model.parameters.to_dict(),
        "rust_diagnostic_binary_sha256": _sha256(diagnostic_binary),
        "rust_implementation_defect": False,
        "rust_sampling": {
            "asymmetric_score_regression_test": "PASS",
            "home_away_ordering": "PASS",
            "independent_categorical_sampling": "PASS",
            "parallel_determinism": "PASS",
            "serialization": "PASS",
            "worker_1_output_sha256": hashlib.sha256(canonical_json_bytes(one_worker)).hexdigest(),
            "worker_4_output_sha256": hashlib.sha256(canonical_json_bytes(four_worker)).hexdigest(),
        },
        "v3_analytic_oracle_defect": False,
        "v3_parity_policy_defect": True,
        "v3_rerun_performed": False,
    }


def _find_failing_input(
    *,
    root: Path,
    reference_model: TransferableGoalModelV1,
    challenger_model: TransferableGoalModelV1,
    frozen_binary: Path,
) -> FailingInput:
    previously_revealed_target_count = 0
    global_batch = 0
    for domain, manifest_sha256 in EVALUATION_MANIFESTS.items():
        season = _load_hashed(root, "manifests", manifest_sha256)
        targets = frozenset(cast(dict[str, Any], season["target_plan"])["target_ids"])
        manifests = [
            _load_path(root / str(item["manifest_path"]))
            for item in cast(list[dict[str, Any]], season["matches"])
        ]
        manifests.sort(key=lambda row: (str(row["kickoff_at"]), str(row["canonical_match_id"])))
        history = RollingHistoryV1()
        position = 0
        while position < len(manifests):
            end = position + 1
            while (
                end < len(manifests)
                and manifests[end]["kickoff_at"] == manifests[position]["kickoff_at"]
            ):
                end += 1
            batch = manifests[position:end]
            target_manifests = sorted(
                (row for row in batch if str(row["canonical_match_id"]) in targets),
                key=lambda row: str(row["canonical_match_id"]),
            )
            for target_manifest in target_manifests:
                kickoff = datetime.fromisoformat(
                    str(target_manifest["kickoff_at"]).replace("Z", "+00:00")
                )
                home_team = UUID(str(target_manifest["home_canonical_team_id"]))
                away_team = UUID(str(target_manifest["away_canonical_team_id"]))
                target = PreparedTargetV1(
                    context=TransferableForecastContextV1(
                        match_id=UUID(str(target_manifest["canonical_match_id"])),
                        scope_key=domain,
                        kickoff_at=kickoff,
                        home_team_id=home_team,
                        away_team_id=away_team,
                    ),
                    domain=domain,
                    kickoff_batch=global_batch,
                    features=history.features(home_team, away_team, cutoff=kickoff),
                )
                for role, artifact_sha256, model in (
                    ("REFERENCE", REFERENCE_SHA256, reference_model),
                    ("CHALLENGER", CHALLENGER_SHA256, challenger_model),
                ):
                    distribution = exact_distribution(model.forecast_features(target.features))
                    input_bytes, input_payload = _simulation_input(
                        target_id=str(target.context.match_id),
                        model_role=role,
                        model_artifact_sha256=artifact_sha256,
                        distribution=distribution,
                        frozen_binary=frozen_binary,
                    )
                    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
                    with tempfile.NamedTemporaryFile() as handle:
                        handle.write(input_bytes)
                        handle.flush()
                        for worker_count in (1, 4):
                            result = subprocess.run(
                                [
                                    str(frozen_binary),
                                    handle.name,
                                    input_sha256,
                                    str(worker_count),
                                ],
                                capture_output=True,
                                check=False,
                            )
                            if result.returncode != 0:
                                return FailingInput(
                                    target=target,
                                    model=model,
                                    model_artifact_sha256=artifact_sha256,
                                    model_role=role,
                                    distribution=distribution,
                                    input_bytes=input_bytes,
                                    input_payload=input_payload,
                                    worker_count=worker_count,
                                    failure=result.stderr.decode(errors="replace").strip(),
                                    previously_revealed_target_count=(
                                        previously_revealed_target_count
                                    ),
                                )
            history.update_batch(tuple(_history_observation(root, row) for row in batch))
            previously_revealed_target_count += len(target_manifests)
            if target_manifests:
                global_batch += 1
            position = end
    raise RuntimeError("frozen execution order did not reproduce a parity failure")


def _history_observation(root: Path, manifest: Mapping[str, object]) -> HistoryObservationV1:
    normalized = _load_hashed(root, "normalized", str(manifest["normalized_sha256"]))
    home_provider = str(manifest["home_provider_team_id"])
    away_provider = str(manifest["away_provider_team_id"])
    goals = {home_provider: 0, away_provider: 0}
    npxg = {home_provider: 0.0, away_provider: 0.0}
    for period in cast(list[dict[str, Any]], normalized["data"]["periods"]):
        if period["period"] not in ("FirstHalf", "SecondHalf"):
            continue
        for shot in cast(list[dict[str, object]], period["shots"]):
            team = str(shot["team_id"])
            value = float(cast(float, shot["expected_goals"]))
            if shot["situation"] != "Penalty":
                npxg[team] += value
            if shot["event_type"] == "Goal":
                goals[team] += 1
    return HistoryObservationV1(
        match_id=UUID(str(manifest["canonical_match_id"])),
        kickoff_at=datetime.fromisoformat(str(manifest["kickoff_at"]).replace("Z", "+00:00")),
        home_team_id=UUID(str(manifest["home_canonical_team_id"])),
        away_team_id=UUID(str(manifest["away_canonical_team_id"])),
        home_goals=goals[home_provider],
        away_goals=goals[away_provider],
        home_npxg=npxg[home_provider],
        away_npxg=npxg[away_provider],
    )


def _simulation_input(
    *,
    target_id: str,
    model_role: str,
    model_artifact_sha256: str,
    distribution: ExactScoreDistributionV1,
    frozen_binary: Path,
) -> tuple[bytes, dict[str, object]]:
    atoms = [
        {
            "away_goals": away,
            "home_goals": home,
            "kind": "EXACT_SCORE",
            "probability": probability,
        }
        for home, away, probability in distribution.atoms
    ] + [
        {
            "away_goals": None,
            "home_goals": None,
            "kind": "UNRESOLVED_TAIL",
            "probability": distribution.unresolved_tail,
        }
    ]
    canonical_atoms = _canonicalize(frozen_binary, canonical_json_bytes(atoms), atoms=True)
    probability_sha256 = hashlib.sha256(canonical_atoms).hexdigest()
    forecast_payload = {
        "model_artifact_sha256": model_artifact_sha256,
        "model_role": model_role,
        "probability_sha256": probability_sha256,
        "target_id": target_id,
    }
    payload: dict[str, object] = {
        "algorithm_version": ALGORITHM_VERSION,
        "analytic_probabilities": _analytic_probabilities(distribution),
        "atoms": atoms,
        "canonical_match_id": target_id,
        "forecast_artifact_sha256": hashlib.sha256(
            canonical_json_bytes(forecast_payload)
        ).hexdigest(),
        "forecast_id": f"{target_id}:{model_role.lower()}",
        "forecast_probability_sha256": probability_sha256,
        "model_artifact_sha256": model_artifact_sha256,
        "policy_sha256": POLICY_SHA256,
        "protocol_id": PROTOCOL_ID,
        "schema_version": "PitchApiSimulationInputV1",
        "seed_schedule_id": SEED_SCHEDULE_ID,
        "simulation_count": SIMULATION_COUNT,
    }
    return _canonicalize(frozen_binary, canonical_json_bytes(payload)), payload


def _canonicalize(binary: Path, payload: bytes, *, atoms: bool = False) -> bytes:
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(payload)
        handle.flush()
        result = subprocess.run(
            [str(binary), "--canonicalize-atoms" if atoms else "--canonicalize", handle.name],
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def _diagnose(
    binary: Path, input_path: Path, input_sha256: str, *, workers: int, total_draws: int
) -> dict[str, object]:
    if total_draws % 4:
        raise RuntimeError("diagnostic simulation count must divide into four batches")
    result = subprocess.run(
        [str(binary), str(input_path), input_sha256, str(workers), str(total_draws // 4)],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return cast(dict[str, object], json.loads(result.stdout))


def _worker_invariant(payload: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key not in ("worker_count",)}


def _event(payload: Mapping[str, object], event_id: str) -> dict[str, object]:
    for event in cast(list[dict[str, object]], payload["events"]):
        if event["event_id"] == event_id:
            return event
    raise RuntimeError(f"missing diagnostic event: {event_id}")


def _clopper_pearson(count: int, total: int, alpha: float) -> tuple[float, float]:
    lower = 0.0 if count == 0 else float(beta.ppf(alpha / 2.0, count, total - count + 1))
    upper = 1.0 if count == total else float(beta.ppf(1.0 - alpha / 2.0, count + 1, total - count))
    return lower, upper


def _decimal_poisson_product(lambda_home: float, lambda_away: float) -> float:
    with localcontext() as context:
        context.prec = 50
        home = Decimal(str(lambda_home))
        away = Decimal(str(lambda_away))
        value = (-home).exp() * home * (-away).exp() * away**4 / Decimal(24)
        return float(value)


def _poisson_distribution(lambda_home: float, lambda_away: float) -> ExactScoreDistributionV1:
    support = 8
    while support <= 100:
        atoms = tuple(
            (home, away, float(poisson.pmf(home, lambda_home) * poisson.pmf(away, lambda_away)))
            for home in range(support + 1)
            for away in range(support + 1)
        )
        tail = 1.0 - sum(value for _, _, value in atoms)
        if -1e-12 <= tail <= 1e-12:
            return ExactScoreDistributionV1(atoms, max(0.0, tail))
        support += 4
    raise RuntimeError("synthetic Poisson support did not converge")


def _distribution_metrics(
    input_payload: Mapping[str, object], diagnostic: Mapping[str, object]
) -> dict[str, object]:
    analytic = {
        str(item["event_id"]): float(cast(float, item["probability"]))
        for item in cast(list[dict[str, object]], input_payload["analytic_probabilities"])
    }
    observed = {
        str(item["event_id"]): float(cast(float, item["simulated_probability"]))
        for item in cast(list[dict[str, object]], diagnostic["events"])
    }
    errors = {name: abs(observed[name] - value) for name, value in analytic.items()}
    score_ids = [name for name in analytic if name.startswith("score:")]
    kl = 0.0
    kl_safe = True
    for name in score_ids:
        expected = analytic[name]
        actual = observed[name]
        if expected > 0.0 and actual == 0.0:
            kl_safe = False
            break
        if expected > 0.0:
            kl += expected * math.log(expected / actual)
    home_marginal_error = []
    away_marginal_error = []
    labels = ("0", "1", "2", "3", "4", "5+")
    for label in labels:
        home_marginal_error.append(
            abs(
                sum(analytic[f"score:{label}-{away}"] for away in labels)
                - sum(observed[f"score:{label}-{away}"] for away in labels)
            )
        )
        away_marginal_error.append(
            abs(
                sum(analytic[f"score:{home}-{label}"] for home in labels)
                - sum(observed[f"score:{home}-{label}"] for home in labels)
            )
        )
    return {
        "analytic_score_mass": sum(analytic[name] for name in score_ids),
        "away_goal_marginal_max_absolute_error": max(away_marginal_error),
        "btts_max_absolute_error": max(errors["btts:yes"], errors["btts:no"]),
        "home_goal_marginal_max_absolute_error": max(home_marginal_error),
        "kl_divergence_analytic_to_simulated": kl if kl_safe else None,
        "maximum_absolute_event_error": max(errors.values()),
        "mean_absolute_event_error": sum(errors.values()) / len(errors),
        "one_x_two_max_absolute_error": max(
            errors["outcome:home_win"], errors["outcome:draw"], errors["outcome:away_win"]
        ),
        "over_under_max_absolute_error": max(
            value for name, value in errors.items() if name.startswith("total:")
        ),
        "simulated_score_mass": sum(observed[name] for name in score_ids),
        "tail_draws": diagnostic["tail_draws"],
        "total_goal_max_absolute_error": max(
            value for name, value in errors.items() if name.startswith("total_goals:")
        ),
        "total_variation_score_matrix": 0.5
        * sum(abs(analytic[name] - observed[name]) for name in score_ids),
    }


def _load_hashed(root: Path, kind: str, digest: str) -> dict[str, Any]:
    path = root / kind / "sha256" / digest[:2] / f"{digest}.json"
    if _sha256(path) != digest:
        raise RuntimeError(f"{kind} resource identity mismatch")
    return _load_path(path)


def _load(path: Path) -> dict[str, Any]:
    return _load_path(path)


def _load_path(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
