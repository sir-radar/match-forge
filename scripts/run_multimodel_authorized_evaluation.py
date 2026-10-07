"""Run the owner-authorized multi-model protected evaluation exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from football.forecasting.multimodel_authorized_evaluation import execute_authorized_evaluation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root", type=Path, default=Path(".local/pitchapi-snapshot-v1/primary")
    )
    parser.add_argument(
        "--champion-artifact",
        type=Path,
        default=Path("docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"),
    )
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path("docs/evaluation/multimodel-challenger-evaluation-v1-preregistration.json"),
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    preregistration_sha256 = hashlib.sha256(args.preregistration.read_bytes()).hexdigest()
    result = execute_authorized_evaluation(
        snapshot_root=args.snapshot_root,
        champion_artifact_path=args.champion_artifact,
        code_commit_sha=args.source_commit,
        preregistration_sha256=preregistration_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["results"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
