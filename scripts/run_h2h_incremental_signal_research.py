#!/usr/bin/env python3
"""Execute frozen development-only residualized H2H research."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from football.forecasting.h2h_incremental_signal import execute, result_markdown


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path(".local/pitchapi-firewall-safe-h2h-history-extension-v1"),
    )
    parser.add_argument(
        "--target-root",
        type=Path,
        default=Path(".local/pitchapi-multi-domain-development-v1-r3/primary"),
    )
    parser.add_argument(
        "--snapshot-result",
        type=Path,
        default=Path(".local/pitchapi-firewall-safe-h2h-history-extension-v1/RESULT.json"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("docs/evidence/matchforge-h2h-incremental-signal-research-v1-2026-10-07.json"),
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=Path("docs/evidence/matchforge-h2h-incremental-signal-research-v1-2026-10-07.md"),
    )
    args = parser.parse_args()
    source_commit = subprocess.run(
        ("git", "rev-parse", "HEAD"), check=True, capture_output=True, text=True
    ).stdout.strip()
    tracked = subprocess.run(
        ("git", "status", "--porcelain", "--untracked-files=no"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if tracked:
        raise RuntimeError("tracked worktree must be clean before outcome execution")
    result = execute(
        snapshot_root=args.snapshot_root,
        target_root=args.target_root,
        snapshot_result_path=args.snapshot_result,
        source_commit=source_commit,
    )
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    args.output_markdown.write_text(result_markdown(result), encoding="utf-8")
    print(json.dumps({"final_disposition": result["final_disposition"]}, sort_keys=True))


if __name__ == "__main__":
    main()
