"""Audit retained V4 normalization evidence without granting identity or eligibility."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from football.canonical_resources.resolution import _references
from football.contracts.observations import Observation
from football.contracts.source import canonical_json_bytes
from football.observations.storage import ObservationArtifactStore
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.common import NormalizationContext
from football.storage.raw import ImmutableFileStore
from psycopg import Connection


def resource_matrix(
    resource_type: str, context: NormalizationContext, observations: Iterable[Observation]
) -> dict[str, Any]:
    """Record measured native facts separately from missing canonical use decisions.

    Even a canonical ID in a source artifact is only a claim. This audit never
    substitutes a normalizer version or mapping claim for an admission, historical
    eligibility decision, or an exact market semantic binding.
    """
    rows = tuple(observations)
    refs: dict[str, set[str]] = {}
    anonymous: Counter[str] = Counter()
    for observation in rows:
        for path, reference in _references(observation).items():
            kind = path.rsplit("/", 1)[-1]
            native = reference.provider_native_id
            if native is None:
                anonymous[kind] += 1
            else:
                refs.setdefault(kind, set()).add(native)
    fixtures = refs.get("fixture", set())
    players = refs.get("player", set()) | refs.get("assisting_player", set())
    contracts = Counter(row.CONTRACT for row in rows)
    schedule = [row for row in rows if hasattr(row, "kickoff_precision")]
    exact = sum(row.kickoff_precision == "EXACT" for row in schedule)
    has_players = bool(players or anonymous["player"] or anonymous["assisting_player"])
    return {
        "provider": context.provenance.provider,
        "native_competition": sorted(refs.get("competition", set())),
        "native_season": sorted(
            {
                str(row.season_label)
                for row in rows
                if getattr(row, "season_label", None) is not None
            }
        ),
        "resource_type": resource_type,
        "source_resource_id": str(context.provenance.source_resource_id),
        "source_sha256": context.provenance.source_sha256,
        "resource_key": context.resource_key,
        "source_bytes": "VERIFIED",
        "normalized_records": len(rows),
        "contracts": dict(sorted(contracts.items())),
        "native_fixtures": len(fixtures),
        "native_players": len(players),
        "anonymous_fixture_references": anonymous["fixture"],
        "anonymous_player_references": anonymous["player"],
        "fixture_identity_status": "MISSING_PROOF",
        "team_identity_status": "MISSING_PROOF",
        "player_identity_status": "MISSING_PROOF" if has_players else "NOT_APPLICABLE",
        "kickoff_time_status": _precision_status(len(schedule), exact),
        "exact_kickoff_observations": exact,
        "date_only_kickoff_observations": len(schedule) - exact,
        "event_time_status": "PARTIAL"
        if any(row.time.event_time for row in rows)
        else "MISSING_PROOF",
        "period_status": "MISSING_PROOF",
        "quantity_semantics_status": "MISSING_PROOF",
        "participation_status": "MISSING_PROOF" if has_players else "NOT_APPLICABLE",
        "membership_status": "MISSING_PROOF" if has_players else "NOT_APPLICABLE",
        "historical_eligibility": "MISSING_PROOF",
        "market_target_eligibility": "MISSING_PROOF",
        "blocker": "EXACT_IDENTITY_TIME_AND_TARGET_USE_DECISIONS_REQUIRED",
        "next_proof_required": (
            "Existing identity-owner source/canonical bindings; verified fixture/event clocks; "
            "period and target semantics; historical-use decision. Player uses additionally "
            "require admitted identity, fixture participation and observed exposure."
        ),
    }


def _precision_status(total: int, exact: int) -> str:
    if not total:
        return "MISSING_PROOF"
    return "VERIFIED" if exact == total else "PARTIAL"


def audit_database(
    connection: Connection[Any], source_root: Path, artifact_root: Path
) -> dict[str, Any]:
    """Checksum-verify the entire registered normalized population in one snapshot."""
    matrix = []
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = connection.execute(
            "SELECT current_database(),transaction_timestamp(),"
            "current_setting('transaction_read_only')"
        ).fetchone()
        inventory = connection.execute(
            """SELECT p.code,count(*),sum(r.size_bytes)
            FROM football.source_resources r
            JOIN football.source_snapshots s ON s.id=r.source_snapshot_id
            JOIN football.providers p ON p.id=s.provider_id GROUP BY 1 ORDER BY 1"""
        ).fetchall()
        groups = connection.execute(
            """SELECT source_resource_id,array_agg(observation_id ORDER BY observation_id)
            FROM football.resource_observation_artifacts
            GROUP BY source_resource_id ORDER BY source_resource_id"""
        ).fetchall()
        store = ObservationArtifactStore(connection, artifact_root)
        for resource_id, ids in groups:
            context, _ = registered_resource(connection, source_root, resource_id)
            matrix.append(
                resource_matrix(
                    "retained_normalization",
                    context,
                    (store.load(observation_id) for observation_id in ids),
                )
            )
        registry = {
            table: _count(connection, table)
            for table in (
                "provider_resource_capabilities",
                "provider_resource_authority",
                "canonical_resource_resolutions",
                "canonical_resource_coverage",
            )
        }
    assert snapshot is not None
    return {
        "database": snapshot[0],
        "recorded_at": snapshot[1].isoformat(),
        "read_only": snapshot[2],
        "raw_registered_resources": sum(row[1] for row in inventory),
        "raw_registration_inventory": [
            {"provider": provider, "resources": count, "bytes": int(size)}
            for provider, count, size in inventory
        ],
        "verified_normalized_resources": len(matrix),
        "verified_observations": sum(row["normalized_records"] for row in matrix),
        "registry_counts": registry,
        "resources": matrix,
    }


def _count(connection: Connection[Any], table: str) -> int:
    from psycopg import sql

    row = connection.execute(
        sql.SQL("SELECT count(*) FROM football.{}").format(sql.Identifier(table))
    ).fetchone()
    assert row is not None
    return int(row[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operating-database-url", required=True)
    parser.add_argument("--shadow-database-url", required=True)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--shadow-root", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args(argv)
    reports = []
    for url, root in (
        (args.operating_database_url, args.source_root),
        (args.shadow_database_url, args.shadow_root),
    ):
        with psycopg.connect(
            url, options="-c default_transaction_read_only=on", connect_timeout=5
        ) as connection:
            reports.append(audit_database(connection, args.source_root, root))
    report = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "databases": reports,
        "operating_writes": 0,
        "provider_requests": 0,
        "qualification_grants": 0,
        "limitations": [
            "Matrix covers every registered normalized source, including revisions; raw-only "
            "registrations are inventoried separately and are not declared byte-verified.",
            "Native fixture/player counts are per resource; sums are source occurrences.",
            "Missing proof describes unestablished use, not proof that a value is absent.",
        ],
    }
    payload = canonical_json_bytes(report) + b"\n"
    artifact = ImmutableFileStore(args.artifact_root).publish(
        "qualification/" + hashlib.sha256(payload).hexdigest() + ".json", payload
    )
    print(json.dumps({"report": str(artifact.path), "sha256": artifact.sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
