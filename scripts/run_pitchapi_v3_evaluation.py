"""Run one owner-authorized PitchAPI V3 evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from football.forecasting.pitchapi_v3 import (
    PROTOCOL_ID,
    TransferableGoalModelV1,
    TransferableParametersV1,
)
from football.forecasting.pitchapi_v3_executor import (
    PitchApiV3ExecutionConfigV1,
    PitchApiV3Executor,
)
from football.forecasting.pitchapi_v3_runtime import (
    PitchApiSnapshotCorpusV3,
    RustSimulationV3,
    load_model_parameters,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--reference-artifact", type=Path, required=True)
    parser.add_argument("--challenger-artifact", type=Path, required=True)
    parser.add_argument("--rust-binary", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--execution-timestamp", required=True)
    args = parser.parse_args()
    if subprocess.run(["git", "diff", "--quiet"], check=False).returncode != 0:
        raise RuntimeError("authorized evaluation requires a clean tracked worktree")
    configuration_payload = _load(args.configuration)
    configuration_sha256 = _sha256(args.configuration)
    preregistration_sha256 = _sha256(args.preregistration)
    reference_sha256 = _sha256(args.reference_artifact)
    challenger_sha256 = _sha256(args.challenger_artifact)
    authorization = _load(args.authorization)
    expected_authorization = {
        "challenger_artifact_sha256": challenger_sha256,
        "evaluation_execution_authorized": True,
        "execution_configuration_sha256": configuration_sha256,
        "preregistration_sha256": preregistration_sha256,
        "protocol_id": PROTOCOL_ID,
        "reference_artifact_sha256": reference_sha256,
        "rust_build_sha256": _sha256(args.rust_binary),
    }
    if any(authorization.get(key) != value for key, value in expected_authorization.items()):
        raise RuntimeError("owner authorization does not bind exact V3 execution identities")
    if configuration_payload.get("execution_authorized") is not False:
        raise RuntimeError("frozen readiness configuration must not self-authorize execution")
    config = PitchApiV3ExecutionConfigV1(
        protocol_id=PROTOCOL_ID,
        policy_sha256=str(configuration_payload["policy_sha256"]),
        preregistration_sha256=preregistration_sha256,
        snapshot_sha256=str(configuration_payload["snapshot_sha256"]),
        corpus_sha256=str(configuration_payload["corpus_sha256"]),
        firewall_sha256=str(configuration_payload["firewall_sha256"]),
        alias_reconciliation_sha256=str(configuration_payload["alias_reconciliation_sha256"]),
        reference_artifact_sha256=reference_sha256,
        challenger_artifact_sha256=challenger_sha256,
        rust_policy_sha256=str(configuration_payload["rust_policy_sha256"]),
        rust_build_sha256=str(configuration_payload["rust_build_sha256"]),
        executor_source_commit=str(configuration_payload["executor_source_commit"]),
        execution_configuration_sha256=configuration_sha256,
    )
    reference = _model(_load(args.reference_artifact))
    challenger = _model(_load(args.challenger_artifact))
    executor = PitchApiV3Executor(
        config=config,
        reference_model=reference,
        challenger_model=challenger,
        simulator=RustSimulationV3(
            binary=args.rust_binary,
            policy_sha256=config.rust_policy_sha256,
            build_sha256=config.rust_build_sha256,
        ),
        corpus=PitchApiSnapshotCorpusV3(args.snapshot_root),
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
    values = load_model_parameters(payload)
    return TransferableGoalModelV1(TransferableParametersV1(**values))


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
