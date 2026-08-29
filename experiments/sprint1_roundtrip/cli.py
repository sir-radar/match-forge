from __future__ import annotations

import argparse
import shutil
import sys

from experiments.sprint1_roundtrip.core import RUNTIME_ROOT
from experiments.sprint1_roundtrip.database import PrototypeDatabase
from experiments.sprint1_roundtrip.runner import run_gate_a


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Disposable Sprint 1 Gate A prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run", help="run real-data round trip and failure-injection matrix")
    subparsers.add_parser("clean", help="remove only dedicated prototype data and schema")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "clean":
        database = PrototypeDatabase()
        try:
            with database.connection() as connection, connection.cursor() as cursor:
                cursor.execute("DROP SCHEMA IF EXISTS gate_a CASCADE")
        except Exception as error:
            print(f"prototype database cleanup skipped: {error}", file=sys.stderr)
        if RUNTIME_ROOT.exists():
            shutil.rmtree(RUNTIME_ROOT)
        print("removed dedicated Gate A database schema and runtime artifacts")
        return 0

    report, json_path, markdown_path = run_gate_a()
    print(f"Gate A: {report['overall_result']}")
    print(f"Recommendation: {report['recommendation']}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0 if report["recommendation"] == "PROCEED" else 6


if __name__ == "__main__":
    raise SystemExit(main())
