"""Validate, inspect schemas and register typed shadow observation artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from football.contracts.observation_schema import observation_schema
from football.contracts.observations import observation_from_bytes
from football.observations.storage import ObservationArtifactStore
from football.storage.experimental import experimental_connection


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    schema = sub.add_parser("schema")
    schema.add_argument("--version", choices=("1", "2"), default="1")
    for command in ("validate", "store"):
        action = sub.add_parser(command)
        action.add_argument("input", type=Path)
        if command == "store":
            action.add_argument("--data-root", type=Path, required=True)
            action.add_argument("--database-url", required=True)
            action.add_argument("--operating-database-url", required=True)
    args = parser.parse_args(argv)
    if args.command == "schema":
        print(json.dumps(observation_schema(args.version), indent=2, sort_keys=True))
        return 0
    observation = observation_from_bytes(args.input.read_bytes())
    if args.command == "store":
        with (
            experimental_connection(args.database_url, args.operating_database_url) as connection,
            connection.transaction(),
        ):
            ObservationArtifactStore(connection, args.data_root).publish(observation)
    print(
        json.dumps(
            {
                "contract": observation.CONTRACT,
                "observation_id": str(observation.observation_id),
                "sha256": observation.sha256,
                "status": "PASS",
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
