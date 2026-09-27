"""Run the single owner-authorized PitchAPI V4 evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from football.forecasting.pitchapi_v3 import TransferableGoalModelV1, TransferableParametersV1
from football.forecasting.pitchapi_v3_executor import (
    PitchApiV4ExecutionConfigV1,
    PitchApiV4Executor,
)
from football.forecasting.pitchapi_v3_runtime import (
    PitchApiSnapshotCorpusV4,
    RustSimulationV4,
    load_model_parameters,
)

PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--rust-policy", type=Path, required=True)
    parser.add_argument("--reference-artifact", type=Path, required=True)
    parser.add_argument("--challenger-artifact", type=Path, required=True)
    parser.add_argument("--rust-binary", type=Path, required=True)
    parser.add_argument("--canonicalizer-binary", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execution-timestamp", required=True)
    args = parser.parse_args()
    if subprocess.run(["git", "diff", "--quiet"], check=False).returncode != 0:
        raise RuntimeError("authorized evaluation requires a clean tracked worktree")

    configuration = _load(args.configuration)
    preregistration = _load(args.preregistration)
    authorization = _load(args.authorization)
    identities = {
        "alias_reconciliation_sha256": str(configuration["alias_reconciliation_sha256"]),
        "challenger_artifact_sha256": _sha256(args.challenger_artifact),
        "corpus_sha256": str(configuration["corpus_sha256"]),
        "evaluation_execution_authorized": True,
        "execution_configuration_sha256": _sha256(args.configuration),
        "firewall_sha256": str(
            cast(dict[str, object], preregistration["source"])["firewall_sha256"]
        ),
        "policy_sha256": _sha256(args.policy),
        "preregistration_sha256": _sha256(args.preregistration),
        "protocol_id": PROTOCOL_ID,
        "reference_artifact_sha256": _sha256(args.reference_artifact),
        "rust_build_sha256": _sha256(args.rust_binary),
        "rust_policy_sha256": _sha256(args.rust_policy),
        "snapshot_sha256": str(configuration["snapshot_sha256"]),
        "target_count": 712,
        "forecast_validation_count": 1_424,
    }
    if any(authorization.get(key) != value for key, value in identities.items()):
        raise RuntimeError("owner authorization does not bind exact V4 execution identities")
    if authorization.get("exact_logical_execution_count") != 1:
        raise RuntimeError("owner authorization must permit exactly one logical V4 execution")
    if configuration.get("execution_authorized") is not False:
        raise RuntimeError("frozen readiness configuration must not self-authorize execution")
    if preregistration.get("evaluation_outcomes_loaded_for_v4_design") is not False:
        raise RuntimeError("V4 design record reports evaluation outcome access")
    source_commit = str(configuration["implementation_source_commit"])
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"], check=False
        ).returncode
        != 0
    ):
        raise RuntimeError("frozen implementation source commit is not in execution history")

    config = PitchApiV4ExecutionConfigV1(
        protocol_id=PROTOCOL_ID,
        policy_sha256=cast(str, identities["policy_sha256"]),
        preregistration_sha256=cast(str, identities["preregistration_sha256"]),
        snapshot_sha256=cast(str, identities["snapshot_sha256"]),
        corpus_sha256=cast(str, identities["corpus_sha256"]),
        firewall_sha256=cast(str, identities["firewall_sha256"]),
        alias_reconciliation_sha256=cast(str, identities["alias_reconciliation_sha256"]),
        reference_artifact_sha256=cast(str, identities["reference_artifact_sha256"]),
        challenger_artifact_sha256=cast(str, identities["challenger_artifact_sha256"]),
        rust_policy_sha256=cast(str, identities["rust_policy_sha256"]),
        rust_build_sha256=cast(str, identities["rust_build_sha256"]),
        executor_source_commit=source_commit,
        execution_configuration_sha256=cast(str, identities["execution_configuration_sha256"]),
    )
    executor = PitchApiV4Executor(
        config=config,
        reference_model=_model(_load(args.reference_artifact)),
        challenger_model=_model(_load(args.challenger_artifact)),
        simulator=RustSimulationV4(
            binary=args.rust_binary,
            canonicalizer_binary=args.canonicalizer_binary,
            policy_sha256=config.rust_policy_sha256,
            build_sha256=config.rust_build_sha256,
        ),
        corpus=PitchApiSnapshotCorpusV4(args.snapshot_root),
    )
    result = executor.execute(
        run_id=args.run_id,
        execution_timestamp=datetime.fromisoformat(args.execution_timestamp),
        output_root=args.output_root,
    )
    output = asdict(result)
    output["directory"] = str(result.directory)
    print(json.dumps(output, sort_keys=True))


def _model(payload: dict[str, Any]) -> TransferableGoalModelV1:
    return TransferableGoalModelV1(TransferableParametersV1(**load_model_parameters(payload)))


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
