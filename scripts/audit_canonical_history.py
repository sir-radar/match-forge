#!/usr/bin/env python3
"""Audit and persist provider-neutral real-fixture identity resolutions."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import psycopg
from football.history.fixture_identity import (
    RESOLUTION_VERSION,
    audit_canonical_history,
    load_canonical_history,
    persist_resolutions,
    semantic_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / ".local/reports/canonical-history-audit.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args()
    report = run_audit(args.database_url, persist=not args.no_persist)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": report["status"], **cast(Mapping[str, object], report["counts"])},
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 2


def run_audit(database_url: str, *, persist: bool) -> dict[str, object]:
    with psycopg.connect(database_url) as connection:
        audit = audit_canonical_history(load_canonical_history(connection))
        if persist:
            persist_resolutions(connection, audit.identities, datetime.now(UTC))
            connection.commit()
    manifest = audit.manifest
    known = [
        item
        for item in manifest
        if item["kickoff_at"] == "2019-07-12T17:00:00+00:00"
        and set(cast(Sequence[str], item["member_fixture_ids"]))
        == {
            "10151aeb-0deb-57e1-9d36-22aa6f7b2d9e",
            "ddfe2ee5-c301-58e4-89dc-710a2170695b",
        }
    ]
    return {
        "contract": "MatchForgeCanonicalHistoryIntegrityAuditV1",
        "resolution_version": RESOLUTION_VERSION,
        "status": "PASS" if audit.unresolved_failures == 0 else "FAIL",
        "counts": dict(audit.counts),
        "by_provider": audit.by_provider,
        "by_competition": audit.by_competition,
        "by_season": audit.by_season,
        "known_openfootball_duplicate": known,
        "resolved_history_manifest_sha256": semantic_sha256(manifest),
        "resolution_manifest": manifest,
    }


if __name__ == "__main__":
    raise SystemExit(main())
