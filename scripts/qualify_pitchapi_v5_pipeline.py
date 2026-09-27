"""Run the proposed V5 evidence pipeline on synthetic data only."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3 import (
    MatchHistoryFeaturesV1,
    TeamHistoryFeaturesV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
)
from football.forecasting.pitchapi_v3_executor import (
    ForecastBatchV1,
    PitchApiV5ExecutionConfigV1,
    PitchApiV5Executor,
    PreparedTargetV1,
    RevealedOutcomeV1,
)
from football.forecasting.pitchapi_v3_runtime import RustSimulationV4, load_model_parameters
from football.forecasting.pitchapi_v5_evaluation import goal_on_xg_calibration

PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V5"
V4_RUST_POLICY_SHA256 = "b4127ae64bd0755ea0d7472da8e984e8c31c4226c93c8a516f10b93ff6df90bf"
DOMAINS = (
    ("bundesliga_2022_23", 216),
    ("bundesliga_2023_24", 216),
    ("ligue1_2022_23", 280),
)
SYNTHETIC_SHA256 = "a" * 64


class SyntheticBoundaryCorpus:
    def __init__(self) -> None:
        self.revealed = False

    def preflight(self) -> dict[str, object]:
        return {
            "alias_reconciliation_sha256": SYNTHETIC_SHA256,
            "corpus_sha256": SYNTHETIC_SHA256,
            "firewall_sha256": SYNTHETIC_SHA256,
            "protocol_id": PROTOCOL_ID,
            "snapshot_sha256": SYNTHETIC_SHA256,
            "target_count": 712,
        }

    def batches(self):  # type: ignore[no-untyped-def]
        domains = [name for name, count in DOMAINS for _ in range(count)]
        targets = tuple(
            PreparedTargetV1(
                context=TransferableForecastContextV1(
                    match_id=UUID(int=index + 1),
                    scope_key=domain,
                    kickoff_at=datetime(2026, 1, 1, tzinfo=UTC),
                    home_team_id=UUID(int=10_000 + index * 2),
                    away_team_id=UUID(int=10_001 + index * 2),
                ),
                domain=domain,
                kickoff_batch=index,
                features=MatchHistoryFeaturesV1(
                    TeamHistoryFeaturesV1(10, 1.4, 1.2, 1.3),
                    TeamHistoryFeaturesV1(10, 1.1, 1.5, 1.0),
                ),
            )
            for index, domain in enumerate(domains)
        )
        yield ForecastBatchV1("synthetic-boundary-batch", targets)

    def reveal_batch(self, batch_id: str) -> tuple[RevealedOutcomeV1, ...]:
        if batch_id != "synthetic-boundary-batch":
            raise RuntimeError("synthetic batch identity mismatch")
        self.revealed = True
        return tuple(
            RevealedOutcomeV1(str(UUID(int=index + 1)), index % 3, (index + 1) % 2)
            for index in range(712)
        )

    def heterogeneity(self) -> dict[str, object]:
        probabilities = (0.0,) + (1e-15, 0.25, 0.75, 1.0 - 1e-15) * 4
        outcomes = (1,) + (0, 0, 1, 1) * 4
        flags = (True,) + (False,) * 16
        result = goal_on_xg_calibration(probabilities, outcomes, flags)
        return {
            "artificial_boundary_cases": {
                "fit": asdict(result.fit),
                "interior_count": result.interior_count,
                "own_goal_zero_count": result.own_goal_zero_count,
                "raw_count": result.raw_count,
                "raw_values_modified": False,
            },
            "classification": "SYNTHETIC_DEVELOPMENT_ONLY",
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-artifact", type=Path, required=True)
    parser.add_argument("--challenger-artifact", type=Path, required=True)
    parser.add_argument("--rust-binary", type=Path, required=True)
    parser.add_argument("--canonicalizer-binary", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise RuntimeError("qualification output root already exists")
    args.output_root.mkdir(parents=True)
    reference_sha256 = _sha256(args.reference_artifact)
    challenger_sha256 = _sha256(args.challenger_artifact)
    rust_sha256 = _sha256(args.rust_binary)
    canonicalizer_sha256 = _sha256(args.canonicalizer_binary)
    models = (
        _model(_load(args.reference_artifact)),
        _model(_load(args.challenger_artifact)),
    )
    results = []
    for replay in ("a", "b"):
        corpus = SyntheticBoundaryCorpus()
        config = PitchApiV5ExecutionConfigV1(
            protocol_id=PROTOCOL_ID,
            policy_sha256=SYNTHETIC_SHA256,
            preregistration_sha256=SYNTHETIC_SHA256,
            snapshot_sha256=SYNTHETIC_SHA256,
            corpus_sha256=SYNTHETIC_SHA256,
            firewall_sha256=SYNTHETIC_SHA256,
            alias_reconciliation_sha256=SYNTHETIC_SHA256,
            reference_artifact_sha256=reference_sha256,
            challenger_artifact_sha256=challenger_sha256,
            rust_policy_sha256=V4_RUST_POLICY_SHA256,
            rust_build_sha256=rust_sha256,
            executor_source_commit="b" * 40,
            execution_configuration_sha256=SYNTHETIC_SHA256,
        )
        executor = PitchApiV5Executor(
            config=config,
            reference_model=models[0],
            challenger_model=models[1],
            simulator=RustSimulationV4(
                binary=args.rust_binary,
                canonicalizer_binary=args.canonicalizer_binary,
                policy_sha256=V4_RUST_POLICY_SHA256,
                build_sha256=rust_sha256,
            ),
            corpus=corpus,
        )
        result = executor.execute(
            run_id="synthetic-v5-qualification",
            execution_timestamp=datetime(2026, 9, 27, tzinfo=UTC),
            output_root=args.output_root / f"replay-{replay}",
        )
        if not corpus.revealed:
            raise RuntimeError("synthetic outcomes were not revealed")
        results.append(result)
    if asdict(results[0]) != asdict(results[1]) | {"directory": results[0].directory}:
        first = asdict(results[0])
        second = asdict(results[1])
        first.pop("directory")
        second.pop("directory")
        if first != second:
            raise RuntimeError("full pipeline replay hashes differ")
    evidence = {
        "calibration_boundary_evidence_generation": "PASS",
        "challenger_artifact_sha256": challenger_sha256,
        "complete_evidence_pipeline": "PASS",
        "contract": "PitchApiV5PipelineQualificationV1",
        "deterministic_full_pipeline_replay": "PASS",
        "evaluation_execution_authorized": False,
        "evaluation_snapshot_used": False,
        "forecast_validation_count_per_replay": 1424,
        "human_publication": "PASS",
        "machine_publication": "PASS",
        "reference_artifact_sha256": reference_sha256,
        "replay_artifact_hashes": {
            key: value for key, value in asdict(results[0]).items() if key != "directory"
        },
        "rust_build_sha256": rust_sha256,
        "rust_canonicalizer_sha256": canonicalizer_sha256,
        "rust_deterministic_serial_parallel_replay": "PASS",
        "rust_policy_sha256": V4_RUST_POLICY_SHA256,
        "synthetic_target_count": 712,
        "v4_evaluation_rerun": False,
        "v5_evaluation_executed": False,
    }
    path = args.output_root / "qualification-evidence.json"
    path.write_bytes(canonical_json_bytes(evidence) + b"\n")
    print(json.dumps({"path": str(path), "sha256": _sha256(path)}, sort_keys=True))


def _model(payload: dict[str, Any]) -> TransferableGoalModelV1:
    return TransferableGoalModelV1(TransferableParametersV1(**load_model_parameters(payload)))


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
