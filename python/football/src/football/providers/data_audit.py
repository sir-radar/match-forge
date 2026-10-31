"""Read-only provider inventory and observed statistic depth; never qualifies data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row

from football.contracts.source import canonical_json_bytes
from football.product.live_resources import _stat_rows, _stat_values
from football.providers.normalization.measurements import TEAM_METRICS, compact
from football.providers.normalization.pipeline import NORMALIZERS
from football.storage.raw import ImmutableFileStore


def _field(scope: tuple[Any, ...]) -> dict[str, Any]:
    provider, competition, season, period, key = scope
    return {
        "provider": provider,
        "competition_id": competition,
        "season_id": season,
        "period": period,
        "source_key": key,
        "normalized_field": TEAM_METRICS.get(compact(key)),
        "resource_rows": 0,
        "measurement_rows": 0,
        "repeated_measurements": 0,
        "fixture_ids": set(),
        "earliest_fixture": None,
        "latest_fixture": None,
        "home_known": 0,
        "away_known": 0,
        "home_zero": 0,
        "away_zero": 0,
        "identity_qualified": None,
        "semantically_qualified": None,
        "pit_eligible": None,
        "modeled": None,
    }


def _fixture_depth(field: dict[str, Any], row: Mapping[str, Any]) -> None:
    if row["fixture_id"] is not None:
        field["fixture_ids"].add(str(row["fixture_id"]))
    kickoff = row["kickoff_at"]
    if kickoff is not None:
        field["earliest_fixture"] = min(field["earliest_fixture"] or kickoff, kickoff)
        field["latest_fixture"] = max(field["latest_fixture"] or kickoff, kickoff)


def summarize_statistics(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure retained native fields without blending sources or inventing trust.

    Resource revisions are counted separately from distinct stored fixtures.
    A recognized normalizer field is a code capability, not qualified coverage.
    """
    fields: dict[tuple[Any, ...], dict[str, Any]] = {}
    unparsed: Counter[str] = Counter()
    for row in rows:
        provider = row["provider"]
        if provider not in {"fotmob", "pitchapi"}:
            unparsed[provider] += 1
            continue
        seen: set[tuple[Any, ...]] = set()
        for period, item in _stat_rows(provider, row["payload"]):
            key = item.get("key")
            if not isinstance(key, str) or not key.strip():
                continue
            scope = (provider, row["competition_id"], row["season_id"], period, key)
            field = fields.get(scope)
            if field is None:
                field = fields[scope] = _field(scope)
            field["resource_rows"] += int(scope not in seen)
            field["measurement_rows"] += 1
            field["repeated_measurements"] += int(scope in seen)
            seen.add(scope)
            _fixture_depth(field, row)
            for side, value in zip(("home", "away"), _stat_values(provider, item), strict=True):
                field[side + "_known"] += int(value is not None and math.isfinite(value))
                field[side + "_zero"] += int(value == 0)
    ordered = sorted(fields, key=lambda scope: tuple(str(value or "") for value in scope))
    result = []
    for scope in ordered:
        field = fields[scope]
        field["fixtures"] = len(field.pop("fixture_ids"))
        result.append(field)
    return {"fields": result, "unparsed_resource_rows": dict(sorted(unparsed.items()))}


def _rows(connection: Connection[Any], query: str) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def audit_provider_data(connection: Connection[Any]) -> dict[str, Any]:
    """Take one current, read-only snapshot; this is not a historical feature reader."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("provider audit requires an idle connection")
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = _rows(
            connection,
            "SELECT current_database() database,transaction_timestamp() recorded_at,"
            "current_setting('transaction_read_only') read_only",
        )[0]
        resources = _rows(
            connection,
            """SELECT p.code provider,count(r.id) registered_resources,
                coalesce(sum(r.size_bytes),0)::bigint registered_bytes,
                min(r.acquired_at) first_acquired_at,max(r.acquired_at) last_acquired_at
            FROM football.providers p LEFT JOIN football.source_snapshots s ON s.provider_id=p.id
            LEFT JOIN football.source_resources r ON r.source_snapshot_id=s.id
            GROUP BY p.code ORDER BY p.code""",
        )
        legacy = _rows(
            connection,
            """SELECT o.provider_code provider,o.resource_type,
                m.competition_id,m.season_id,o.availability_status,
                o.point_in_time_eligibility recorded_pit_eligibility,
                count(*) resource_rows,count(DISTINCT o.canonical_fixture_id) fixtures,
                min(f.kickoff_at) earliest_fixture,max(f.kickoff_at) latest_fixture,
                min(o.observed_at) first_observed_at,max(o.known_at) last_known_at
            FROM football.product_provider_resource_observations o
            LEFT JOIN football.product_fixtures f ON f.fixture_id=o.canonical_fixture_id
            LEFT JOIN football.matches m ON m.id=o.canonical_fixture_id
            GROUP BY 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6""",
        )
        owners = _rows(
            connection,
            """WITH normalized AS (
                SELECT provider_id,count(*) n FROM football.resource_observation_artifacts
                GROUP BY provider_id
            ), capabilities AS (
                SELECT provider_id,count(*) n FROM football.provider_resource_capabilities
                GROUP BY provider_id
            ), authority AS (
                SELECT provider_id,count(*) n FROM football.provider_resource_authority
                GROUP BY provider_id
            ), coverage AS (
                SELECT provider_id,count(*) n FROM football.provider_resource_coverage
                GROUP BY provider_id
            ) SELECT p.code provider,coalesce(n.n,0) normalized_artifacts,
                coalesce(c.n,0) capability_decisions,coalesce(a.n,0) authority_decisions,
                coalesce(v.n,0) coverage_reports
            FROM football.providers p LEFT JOIN normalized n ON n.provider_id=p.id
            LEFT JOIN capabilities c ON c.provider_id=p.id
            LEFT JOIN authority a ON a.provider_id=p.id
            LEFT JOIN coverage v ON v.provider_id=p.id ORDER BY p.code""",
        )
        with connection.cursor(name="provider_statistics_audit", row_factory=dict_row) as cursor:
            cursor.execute(
                """SELECT o.provider_code provider,o.canonical_fixture_id fixture_id,
                    m.competition_id,m.season_id,f.kickoff_at,o.payload
                FROM football.product_provider_resource_observations o
                LEFT JOIN football.product_fixtures f ON f.fixture_id=o.canonical_fixture_id
                LEFT JOIN football.matches m ON m.id=o.canonical_fixture_id
                WHERE o.resource_type='STATISTICS'
                ORDER BY o.provider_code,o.resource_observation_id"""
            )
            statistics = summarize_statistics(cursor)
    return {
        **snapshot,
        "registered_resources": resources,
        "recorded_resource_scopes": legacy,
        "existing_registry_counts": owners,
        "normalizer_routes": [
            {"provider": provider, "resource": resource}
            for provider, resource in sorted(NORMALIZERS)
        ],
        "observed_statistics": statistics,
        "limitations": [
            "Registrations do not prove physical byte retention or current endpoint access.",
            "Counts include revisions; distinct fixtures are reported separately.",
            "Known/zero counts describe measurements; repeated measurements do not add resources.",
            "Competition/season IDs and kickoff describe the current diagnostic snapshot.",
            "Recorded eligibility and recognized fields do not establish identity, semantics "
            "or model qualification.",
            "Unknown qualification and model use remain null; no missing value becomes zero.",
            "No provider request, identity decision, model fit or operating mutation is performed.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args(argv)
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL is required")
    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            report = audit_provider_data(connection)
        # Only database-native timestamps/UUIDs need conversion; counts stay integers.
        payload = canonical_json_bytes(json.loads(json.dumps(report, default=str))) + b"\n"
        digest = hashlib.sha256(payload).hexdigest()
        artifact = ImmutableFileStore(args.artifact_root).publish(
            f"reports/provider-data-audit/{digest}.json", payload
        )
    except (OSError, psycopg.Error) as error:
        print(f"Provider audit unavailable ({type(error).__name__})", file=sys.stderr)
        return 2
    print(json.dumps({"report": str(artifact.path), "sha256": artifact.sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
