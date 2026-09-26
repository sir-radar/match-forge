"""Qualify the proposed PitchAPI V4 Rust parity policy offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3_evaluation import ExactScoreDistributionV1
from football.forecasting.pitchapi_v3_runtime import _analytic_probabilities
from scipy.stats import poisson

V4_PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4"
V4_POLICY_SHA256 = "b4127ae64bd0755ea0d7472da8e984e8c31c4226c93c8a516f10b93ff6df90bf"
V4_ALGORITHM_VERSION = "pitchapi-score-categorical-v2"
V4_SEED_SCHEDULE_ID = "pitchapi-v4-splitmix64-sha256-v1"
SIMULATION_COUNT = 112_460
SYNTHETIC_CASES = (
    ("balanced", 1.4, 1.2),
    ("away_heavy", 0.7, 2.8),
    ("home_heavy", 2.8, 0.7),
    ("low_rate", 0.1, 0.1),
    ("high_rate", 4.0, 3.5),
    ("moderate_asymmetric", 2.0, 3.0),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v3-failing-input", type=Path, required=True)
    parser.add_argument("--canonicalizer-binary", type=Path, required=True)
    parser.add_argument("--v4-binary", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    evidence = qualify(
        v3_failing_input=args.v3_failing_input,
        canonicalizer_binary=args.canonicalizer_binary,
        v4_binary=args.v4_binary,
        output_root=args.output_root,
    )
    path = args.output_root / "qualification-evidence.json"
    path.write_bytes(canonical_json_bytes(evidence) + b"\n")
    print(json.dumps({"path": str(path), "sha256": _sha256(path)}, sort_keys=True))


def qualify(
    *,
    v3_failing_input: Path,
    canonicalizer_binary: Path,
    v4_binary: Path,
    output_root: Path,
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=False)
    v3_payload = _load(v3_failing_input)
    exact = _qualify_input(v3_payload, v4_binary, output_root, "exact-v3-failure-input")
    synthetic = []
    for case_id, lambda_home, lambda_away in SYNTHETIC_CASES:
        distribution = _poisson_distribution(lambda_home, lambda_away)
        payload = _payload_for_distribution(
            distribution,
            target_id=f"synthetic-v4-{case_id}",
            template=v3_payload,
            canonicalizer_binary=canonicalizer_binary,
        )
        result = _qualify_input(payload, v4_binary, output_root, f"synthetic-{case_id}")
        synthetic.append(
            {
                "case_id": case_id,
                "lambda_away": lambda_away,
                "lambda_home": lambda_home,
                **result,
            }
        )
    malformed = _v4_payload(v3_payload)
    probabilities = cast(list[dict[str, object]], malformed["analytic_probabilities"])
    probabilities[0]["probability"] = float(cast(float, probabilities[0]["probability"])) + 0.01
    malformed_result = _run(v4_binary, canonical_json_bytes(malformed), workers=1)
    if malformed_result.returncode == 0 or not malformed_result.stderr.decode().startswith(
        "ANALYTIC_REDUCTION_MISMATCH"
    ):
        raise RuntimeError("V4 malformed analytic reduction did not fail closed")
    return {
        "analytic_reduction_mismatch": "FAIL_CLOSED_PASS",
        "contract": "PitchApiV4RustOfflineQualificationV1",
        "exact_v3_failure_input": exact,
        "simulation_count_per_forecast": SIMULATION_COUNT,
        "synthetic_cases": synthetic,
        "v3_evaluation_executed": False,
        "v3_failing_input_sha256": _sha256(v3_failing_input),
        "v4_binary_sha256": _sha256(v4_binary),
        "v4_execution_authorized": False,
        "v4_policy_sha256": V4_POLICY_SHA256,
    }


def _qualify_input(
    payload: dict[str, Any], binary: Path, output_root: Path, name: str
) -> dict[str, object]:
    v4_payload = _v4_payload(payload)
    input_bytes = canonical_json_bytes(v4_payload)
    input_path = output_root / f"{name}-input.json"
    input_path.write_bytes(input_bytes)
    one = _run(binary, input_bytes, workers=1)
    four = _run(binary, input_bytes, workers=4)
    if one.returncode != 0:
        raise RuntimeError(one.stderr.decode(errors="replace"))
    if four.returncode != 0:
        raise RuntimeError(four.stderr.decode(errors="replace"))
    if one.stdout != four.stdout:
        raise RuntimeError("V4 one-worker/four-worker canonical outputs differ")
    output = cast(dict[str, object], json.loads(one.stdout))
    if output["status"] not in ("PASS", "PASS_WITH_WARNINGS"):
        raise RuntimeError("V4 qualification did not pass")
    output_path = output_root / f"{name}-output.json"
    output_path.write_bytes(one.stdout)
    events = cast(list[dict[str, object]], output["events"])
    return {
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "maximum_event_absolute_error": max(
            float(cast(float, event["absolute_error"])) for event in events
        ),
        "output_sha256": hashlib.sha256(one.stdout).hexdigest(),
        "serial_parallel_canonical_match": True,
        "status": output["status"],
        "total_variation": output["total_variation"],
        "total_variation_limit": output["total_variation_limit"],
        "warnings": output["warnings"],
    }


def _v4_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = cast(dict[str, Any], json.loads(json.dumps(payload)))
    result["algorithm_version"] = V4_ALGORITHM_VERSION
    result["policy_sha256"] = V4_POLICY_SHA256
    result["protocol_id"] = V4_PROTOCOL_ID
    result["seed_schedule_id"] = V4_SEED_SCHEDULE_ID
    return result


def _payload_for_distribution(
    distribution: ExactScoreDistributionV1,
    *,
    target_id: str,
    template: dict[str, Any],
    canonicalizer_binary: Path,
) -> dict[str, Any]:
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
    probability_sha256 = hashlib.sha256(
        _canonicalize_atoms(canonicalizer_binary, canonical_json_bytes(atoms))
    ).hexdigest()
    model_artifact_sha256 = str(template["model_artifact_sha256"])
    forecast_payload = {
        "model_artifact_sha256": model_artifact_sha256,
        "model_role": "REFERENCE",
        "probability_sha256": probability_sha256,
        "target_id": target_id,
    }
    return {
        "algorithm_version": V4_ALGORITHM_VERSION,
        "analytic_probabilities": _analytic_probabilities(distribution),
        "atoms": atoms,
        "canonical_match_id": target_id,
        "forecast_artifact_sha256": hashlib.sha256(
            canonical_json_bytes(forecast_payload)
        ).hexdigest(),
        "forecast_id": f"{target_id}:reference",
        "forecast_probability_sha256": probability_sha256,
        "model_artifact_sha256": model_artifact_sha256,
        "policy_sha256": V4_POLICY_SHA256,
        "protocol_id": V4_PROTOCOL_ID,
        "schema_version": "PitchApiSimulationInputV1",
        "seed_schedule_id": V4_SEED_SCHEDULE_ID,
        "simulation_count": SIMULATION_COUNT,
    }


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


def _run(binary: Path, payload: bytes, *, workers: int) -> subprocess.CompletedProcess[bytes]:
    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(payload)
        handle.flush()
        return subprocess.run(
            [str(binary), handle.name, digest, str(workers)],
            capture_output=True,
            check=False,
        )


def _canonicalize_atoms(binary: Path, payload: bytes) -> bytes:
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(payload)
        handle.flush()
        result = subprocess.run(
            [str(binary), "--canonicalize-atoms", handle.name],
            capture_output=True,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result.stdout


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
