"""Read-only per-database inventory and identity comparison against the operating database.

Every connection is opened with ``default_transaction_read_only=on``. The script only
reads catalogs and primary keys. It never creates, alters, drops or writes anything,
and it never treats a name, age or size as evidence that a database is disposable.

For each canonical table it reports how many primary keys in the candidate database
are absent from the authoritative database. Keys are compared by a 64-bit BLAKE2b
fingerprint of the key's text form; the collision probability is reported, and a
zero count is evidence of no unique *identities*, not proof that row contents match.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import numpy as np
import psycopg

# Canonical identity, registration, forecast, model and source tables. Pure work-queue
# and metrics tables are excluded: rehearsal runs create their own operational rows.
CANONICAL_TABLES = (
    "competitions",
    "seasons",
    "teams",
    "players",
    "matches",
    "event_catalog",
    "product_competitions",
    "product_teams",
    "product_team_aliases",
    "product_fixtures",
    "product_team_match_history",
    "product_match_history_decisions",
    "product_identity_admissions",
    "product_provider_mapping_decisions",
    "fixture_identity_resolutions",
    "team_provider_mappings",
    "match_provider_mappings",
    "player_provider_mappings",
    "player_source_facts",
    "product_forecasts",
    "baseline_forecasts",
    "model_artifacts",
    "model_artifact_files",
    "source_resources",
    "source_snapshots",
    "resource_observation_artifacts",
    "product_read_reports",
)
SAMPLE_LIMIT = 5


def database_url(base: str, name: str) -> str:
    parts = urlsplit(base)
    return urlunsplit(parts._replace(path="/" + name))


def connect(base: str, name: str) -> psycopg.Connection[Any]:
    return psycopg.connect(
        database_url(base, name),
        options="-c default_transaction_read_only=on -c statement_timeout=900000",
        autocommit=False,
    )


def fingerprint(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode(), digest_size=8).digest(), "big")


def primary_keys(conn: psycopg.Connection[Any]) -> dict[str, list[str]]:
    rows = conn.execute(
        """SELECT c.relname, array_agg(a.attname::text ORDER BY k.ord)
           FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           CROSS JOIN LATERAL unnest(i.indkey::int2[]) WITH ORDINALITY AS k(attnum, ord)
           JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
           WHERE i.indisprimary AND n.nspname='football' AND c.relname = ANY(%s)
           GROUP BY c.relname""",
        (list(CANONICAL_TABLES),),
    ).fetchall()
    return {name: list(columns) for name, columns in rows}


def key_texts(conn: psycopg.Connection[Any], table: str, columns: list[str]) -> Iterator[str]:
    expression = "row(" + ",".join(f'"{c}"' for c in columns) + ")::text"
    with conn.cursor(name=f"keys_{table}") as cursor:
        cursor.itersize = 50_000
        cursor.execute(f'SELECT {expression} FROM football."{table}"')  # noqa: S608 - catalog names
        for (text,) in cursor:
            yield text


def key_set(conn: psycopg.Connection[Any], table: str, columns: list[str]) -> np.ndarray:
    values = np.fromiter((fingerprint(t) for t in key_texts(conn, table, columns)), dtype=np.uint64)
    return np.unique(values)


def metadata(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    row = conn.execute(
        """SELECT d.oid::bigint, pg_database_size(d.oid),
             (pg_stat_file('base/'||d.oid||'/PG_VERSION')).modification,
             (SELECT count(*) FROM pg_stat_activity a
              WHERE a.datid=d.oid AND a.pid<>pg_backend_pid()),
             s.xact_commit, s.tup_inserted, s.tup_updated, s.tup_deleted, s.stats_reset,
             (SELECT system_identifier::text FROM pg_control_system()),
             pg_get_userbyid(d.datdba), shobj_description(d.oid,'pg_database')
           FROM pg_database d LEFT JOIN pg_stat_database s ON s.datid=d.oid
           WHERE d.datname=current_database()"""
    ).fetchone()
    assert row is not None
    goose = None
    if conn.execute("SELECT to_regclass('public.goose_db_version') IS NOT NULL").fetchone() == (
        True,
    ):
        goose_row = conn.execute(
            "SELECT max(version_id), max(tstamp) FROM public.goose_db_version WHERE is_applied"
        ).fetchone()
        assert goose_row is not None
        goose = {"version": goose_row[0], "applied_at": iso(goose_row[1])}
    return {
        "oid": row[0],
        "size_bytes": row[1],
        "created_at": iso(row[2]),
        "active_connections": row[3],
        "activity_counters": {
            "xact_commit": row[4],
            "tup_inserted": row[5],
            "tup_updated": row[6],
            "tup_deleted": row[7],
            "stats_reset": iso(row[8]),
        },
        "cluster_system_identifier": row[9],
        "owner": row[10],
        "comment": row[11],
        "latest_migration": goose,
    }


def iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def compare(
    conn: psycopg.Connection[Any],
    reference: dict[str, tuple[list[str], np.ndarray]],
) -> dict[str, Any]:
    keys = primary_keys(conn)
    tables: dict[str, Any] = {}
    for table in CANONICAL_TABLES:
        if table not in reference:
            continue
        if table not in keys:
            tables[table] = {"present": False}
            continue
        columns, authoritative = reference[table]
        if keys[table] != columns:
            tables[table] = {
                "present": True,
                "schema": "PRIMARY_KEY_DIFFERS",
                "columns": keys[table],
            }
            continue
        rows, absent, samples = compare_keys(key_texts(conn, table, columns), authoritative)
        tables[table] = {
            "present": True,
            "rows": rows,
            "absent_from_authoritative": absent,
            "absent_samples": samples,
        }
    return tables


def compare_keys(texts: Iterator[str], authoritative: np.ndarray) -> tuple[int, int, list[str]]:
    """Count keys absent from the sorted authoritative fingerprints, in bounded chunks."""
    rows = absent = 0
    samples: list[str] = []
    chunk: list[str] = []

    def flush(batch: list[str]) -> int:
        fingerprints = np.array([fingerprint(t) for t in batch], dtype=np.uint64)
        missing = ~np.isin(fingerprints, authoritative)
        for index in np.flatnonzero(missing)[: SAMPLE_LIMIT - len(samples)]:
            samples.append(batch[int(index)])
        return int(missing.sum())

    for text in texts:
        rows += 1
        chunk.append(text)
        if len(chunk) >= 200_000:
            absent += flush(chunk)
            chunk = []
    if chunk:
        absent += flush(chunk)
    return rows, absent, samples


def summarize(tables: dict[str, Any]) -> dict[str, Any]:
    compared = [t for t in tables.values() if t.get("present") and "rows" in t]
    unresolved = [
        name for name, t in tables.items() if t.get("present") and t.get("schema") is not None
    ]
    unique = sum(t["absent_from_authoritative"] for t in compared)
    tables_with_unique = sorted(
        name for name, t in tables.items() if t.get("absent_from_authoritative")
    )
    if unresolved:
        finding = "UNRESOLVED_SCHEMA_DIFFERENCE"
    elif unique == 0:
        finding = "NO_UNIQUE_CANONICAL_IDENTITIES"
    else:
        finding = "UNIQUE_CANONICAL_IDENTITIES_PRESENT"
    return {
        "finding": finding,
        "unique_identity_rows": unique,
        "tables_with_unique_identities": tables_with_unique,
        "tables_compared": len(compared),
        "tables_absent": sorted(n for n, t in tables.items() if not t.get("present")),
        "tables_schema_differs": unresolved,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster-url", required=True, help="URL of any database in the cluster")
    parser.add_argument("--authoritative", required=True, help="operating database name")
    parser.add_argument("--authoritative-oid", type=int, required=True)
    parser.add_argument("--system-identifier", required=True)
    parser.add_argument("--only", nargs="*", help="limit comparison to these databases")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()

    with connect(args.cluster_url, args.authoritative) as conn:
        auth_meta = metadata(conn)
        if (
            auth_meta["oid"] != args.authoritative_oid
            or auth_meta["cluster_system_identifier"] != args.system_identifier
        ):
            raise SystemExit("authoritative identity mismatch: refusing to compare")
        names = [
            r[0]
            for r in conn.execute(
                "SELECT datname FROM pg_database"
                " WHERE NOT datistemplate AND datallowconn ORDER BY 1"
            ).fetchall()
        ]
        reference: dict[str, tuple[list[str], np.ndarray]] = {}
        reference_rows: dict[str, int] = {}
        for table, columns in primary_keys(conn).items():
            values = key_set(conn, table, columns)
            reference[table] = (columns, values)
            reference_rows[table] = int(values.size)
        conn.rollback()

    keys_total = sum(reference_rows.values())
    result: dict[str, Any] = {
        "observed_at": datetime.now(UTC).isoformat(),
        "method": "read-only catalog and primary-key fingerprint comparison",
        "fingerprint": "BLAKE2b-64 of row(primary key)::text",
        "collision_bound_per_database": f"<= {keys_total**2 / 2**65:.3e}",
        "row_contents_compared": False,
        "authoritative": {
            "database": args.authoritative,
            **auth_meta,
            "canonical_key_counts": reference_rows,
        },
        "databases": [],
    }
    for name in names:
        if name == args.authoritative or (args.only and name not in args.only):
            continue
        entry: dict[str, Any] = {"database": name}
        try:
            with connect(args.cluster_url, name) as conn:
                entry.update(metadata(conn))
                if entry["cluster_system_identifier"] != args.system_identifier:
                    raise RuntimeError("cluster identity changed during inventory")
                entry["tables"] = compare(conn, reference)
                conn.rollback()
            entry["summary"] = summarize(entry["tables"])
        except (psycopg.Error, RuntimeError) as error:
            entry["error"] = f"{type(error).__name__}: {error}"
            entry["summary"] = {"finding": "UNRESOLVED_INVENTORY_ERROR"}
        result["databases"].append(entry)
        print(json.dumps({"database": name, **entry["summary"]}), flush=True)
    result["duration_seconds"] = round(time.monotonic() - started, 1)
    with args.output.open("x") as output:
        json.dump(result, output, indent=1)
        output.write("\n")


if __name__ == "__main__":
    main()
