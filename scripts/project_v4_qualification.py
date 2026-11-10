"""Project a frozen blocked pilot through existing coverage owners in isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from football.contracts.source import canonical_json_bytes
from football.coverage.resources import ProviderCoverage
from football.coverage.storage import CoverageRegistry, prepare_coverage
from football.product.market_capability_cli import market_capability_report
from football.providers.resource_capabilities import ResourceScope
from football.storage.experimental import experimental_connection
from football.storage.raw import ImmutableFileStore
from psycopg.types.json import Jsonb


def frozen_report(path: Path) -> tuple[dict[str, Any], str]:
    evidence = json.loads(path.read_bytes())
    reference = evidence["report"]
    raw = Path(reference["report"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
        raise ValueError("frozen qualification report checksum mismatch")
    return json.loads(raw), reference["sha256"]


def blocked_population(
    identity: dict[str, Any], timing: dict[str, Any], players: dict[str, Any]
) -> frozenset[str]:
    """An empty qualified set is publishable only with measured blocked evidence."""
    if any(report["status"] != "BLOCKED_WITH_EVIDENCE" for report in (identity, timing, players)):
        raise ValueError("this projection requires a frozen blocked population")
    if {report["match_resource_id"] for report in (identity, timing, players)} != {
        "01a051db-5a13-7417-b9b5-247d08f3b82f"
    }:
        raise ValueError("reports must bind the frozen EPL 2/27 match index")
    fixtures = frozenset(row["native_fixture_id"] for row in identity["fixtures"])
    timed = frozenset(row["native_fixture_id"] for row in timing["clocks"])
    rostered = frozenset(row["native_fixture_id"] for row in players["records"])
    if not fixtures or fixtures != timed or fixtures != rostered:
        raise ValueError("qualification reports must bind the same nonempty fixture population")
    if any(row["admitted_proof"] is not None for row in identity["owner_mapping_checks"]):
        raise ValueError("admitted evidence requires requalification through its existing owner")
    if timing["qualified_market_labels"] or players["canonical_identity_admissions"]:
        raise ValueError("qualified evidence cannot be replaced with empty coverage")
    if any(row["current_resolution_decisions"] for row in identity["fixtures"]):
        raise ValueError("existing fixture decisions require exact owner qualification")
    return fixtures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--operating-database-url", required=True)
    parser.add_argument("--expected-database", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--competition-id", type=UUID, required=True)
    parser.add_argument("--season-id", type=UUID, required=True)
    args = parser.parse_args(argv)
    reports, hashes = [], []
    for name in ("identity", "time-targets", "players"):
        report, digest = frozen_report(Path(f"docs/evidence/v4-issue-02-{name}.json"))
        reports.append(report)
        hashes.append(digest)
    fixtures = blocked_population(*reports)
    cutoff = max(datetime.fromisoformat(report["knowledge_cutoff"]) for report in reports)
    with psycopg.connect(
        args.operating_database_url,
        options="-c default_transaction_read_only=on",
        connect_timeout=5,
    ) as source:
        provider = source.execute(
            "SELECT to_jsonb(p) FROM football.providers p WHERE code='statsbomb_open_data'"
        ).fetchone()
        assert provider is not None
    with experimental_connection(args.database_url, args.operating_database_url) as connection:
        if connection.info.dbname != args.expected_database:
            raise ValueError("experimental database differs from the expected pilot target")
        connection.execute(
            """INSERT INTO football.providers
            SELECT (jsonb_populate_record(NULL::football.providers,%s)).*
            ON CONFLICT (id) DO NOTHING""",
            (Jsonb(provider[0]),),
        )
        registry = CoverageRegistry(connection)
        coverage = [
            ProviderCoverage(
                scope=ResourceScope(
                    provider="statsbomb_open_data", resource_type=kind, competition="2", season="27"
                ),
                knowledge_cutoff=cutoff,
                expected_units=fixtures,
                observed_units=fixtures,
                qualified_units=(),
                evidence_refs=tuple("sha256:" + digest for digest in hashes),
            )
            for kind in ("results", "events", "lineups", "shots")
        ]
        first = [
            registry.register(prepare_coverage(args.artifact_root, report)) for report in coverage
        ]
        second = [
            registry.register(prepare_coverage(args.artifact_root, report)) for report in coverage
        ]
        if first != second:
            raise ValueError("repeated coverage registration changed identities")
        counts = {}
        for table in (
            "provider_resource_coverage",
            "canonical_resource_coverage",
            "canonical_resource_resolutions",
            "resource_observation_artifacts",
        ):
            row = connection.execute(f"SELECT count(*) FROM football.{table}").fetchone()
            assert row is not None
            counts[table] = row[0]
        markets = market_capability_report(
            connection,
            args.artifact_root,
            competition_id=args.competition_id,
            season_id=args.season_id,
            knowledge_cutoff=cutoff,
        )
    report = {
        "phase": "R02-E",
        "status": "BLOCKED_WITH_EVIDENCE",
        "database": args.expected_database,
        "isolated_from_operating": True,
        "artifact_root": str(args.artifact_root.resolve()),
        "input_sha256": hashes,
        "native_fixtures": len(fixtures),
        "qualified_canonical_fixtures": 0,
        "qualified_canonical_players": 0,
        "canonical_history_rows_created": 0,
        "unqualified_observations_copied": 0,
        "coverage_report_ids": [str(key) for key in first],
        "coverage_sha256": [report.sha256 for report in coverage],
        "repeat_registration_identical": first == second,
        "registry_counts": counts,
        "market_diagnostics": markets,
        "market_status_counts": dict(
            Counter(row["diagnostic_status"] for row in markets["markets"])
        ),
        "scope_identity_status": "RECORDED_MAPPING_CLAIM_ONLY; no canonical use granted",
        "operating_writes": 0,
        "provider_requests": 0,
        "model_publications": 0,
        "interpretation": "Four native coverage reports measure 380 observed and zero qualified "
        "units each. No unqualified observation proceeds to canonical history. Existing market "
        "diagnostics remain data-blocked; no support or history sufficiency is invented.",
    }
    payload = canonical_json_bytes(report) + b"\n"
    artifact = ImmutableFileStore(args.artifact_root).publish(
        "qualification/" + hashlib.sha256(payload).hexdigest() + ".json", payload
    )
    print(json.dumps({"report": str(artifact.path), "sha256": artifact.sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
