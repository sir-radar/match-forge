#!/usr/bin/env python3
"""Freeze Architecture V2's starting data without changing live data."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import urllib.request
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import psycopg
from football.contracts.source import canonical_json_bytes, validate_relative_posix_path
from football.product.history_coverage import history_coverage
from football.product.identity_admission import _retained_payload
from football.storage.raw import ImmutableFileStore
from jsonschema import ValidationError
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
CHAMPION = ROOT / "docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json"
CHAMPION_SHA256 = "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")


def write_row_hashes(rows: Iterable[tuple[str | None, str]], path: Path) -> dict[str, Any]:
    """Store keys and row digests, including multiplicity, without exposing row contents."""
    digest = hashlib.sha256()
    count = 0
    with path.open("xb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as out:
        for row in rows:
            line = canonical_json_bytes(row) + b"\n"
            digest.update(line)
            out.write(line)
            count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def compare_relations(expected: Mapping[str, object], actual: Mapping[str, object]) -> list[str]:
    return [
        name
        for name in sorted(expected.keys() | actual.keys())
        if expected.get(name) != actual.get(name)
    ]


def capture_source_resource(
    root: Path, archive: Path, provider: str, row: tuple[Any, ...]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "resource_id": str(row[5]),
        "provider": provider,
        "registered_sha256": row[7],
        "registered_size_bytes": row[8],
    }
    try:
        payload = _retained_payload(root, provider, row)
    except FileNotFoundError:
        result["status"] = "SOURCE_BYTES_MISSING"
    except (OSError, ValueError, KeyError, TypeError, ValidationError):
        result["status"] = "INVALID_SOURCE_REFERENCE"
    else:
        result["status"] = "REGISTERED_CHECKSUM_NOT_VERIFIED"
        if payload is not None:
            relative = f"source-bytes/{row[7][:2]}/{row[7]}"
            ImmutableFileStore(archive).publish(relative, payload)
            result.update(status="BYTE_VERIFIED", archive_path=relative)
    return result


def capture_relations(
    connection: psycopg.Connection[Any], output: Path, *, views: bool = False
) -> dict[str, Any]:
    relations = connection.execute(
        """SELECT n.nspname, c.relname, ARRAY(
               SELECT a.attname FROM pg_index i
               CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum, position)
               JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
               WHERE i.indrelid=c.oid AND i.indisprimary ORDER BY k.position)
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE (n.nspname='football' OR (n.nspname='public' AND c.relname='goose_db_version'))
             AND c.relkind IN (%s,%s) ORDER BY n.nspname,c.relname""",
        ("v", "m") if views else ("r", "p"),
    ).fetchall()
    directory = output / ("view-hashes" if views else "row-hashes")
    directory.mkdir()
    result = {}
    for schema, name, keys in relations:
        key_sql = (
            sql.SQL("jsonb_build_array({})::text").format(
                sql.SQL(",").join(sql.Identifier("t", key) for key in keys)
            )
            if keys
            else sql.SQL("NULL::text")
        )
        order = (
            sql.SQL(",").join(sql.Identifier("t", key) for key in keys) if keys else sql.SQL("2")
        )
        query = sql.SQL(
            "SELECT {}, encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') "
            "FROM {} t ORDER BY {}"
        ).format(key_sql, sql.Identifier(schema, name), order)
        with connection.cursor(name="baseline_rows") as cursor:
            cursor.execute(query)
            result[f"{schema}.{name}"] = write_row_hashes(
                cursor, directory / f"{schema}.{name}.jsonl.gz"
            )
    return result


def capture_sources(
    connection: psycopg.Connection[Any], output: Path, root: Path
) -> dict[str, dict[str, int]]:
    rows = connection.execute(
        """SELECT p.code,s.manifest_path,s.manifest_sha256,s.source_identity,s.source_revision,
                  s.git_sha,r.id,r.provider_path,r.sha256,r.size_bytes,r.acquired_at
           FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id
           JOIN football.source_resources r ON r.source_snapshot_id=s.id ORDER BY r.id"""
    ).fetchall()
    results = [capture_source_resource(root, output, row[0], row[1:]) for row in rows]
    write_json(output / "source-resources.json", results)
    snapshots = connection.execute(
        "SELECT to_jsonb(s) FROM football.source_snapshots s ORDER BY id"
    ).fetchall()
    write_json(output / "source-snapshots.json", [row[0] for row in snapshots])
    manifests = [capture_manifest(root, output, row[0]) for row in snapshots]
    write_json(output / "source-manifests.json", manifests)
    return {
        "resources": dict(Counter(row["status"] for row in results)),
        "manifests": dict(Counter(row["status"] for row in manifests)),
    }


def capture_manifest(root: Path, output: Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    result = {"snapshot_id": snapshot["id"], "manifest_path": snapshot["manifest_path"]}
    try:
        path = root / validate_relative_posix_path(snapshot["manifest_path"])
        path.resolve().relative_to(root.resolve())
        if path.is_symlink():
            raise ValueError("symlink source manifest")
        payload = path.read_bytes()
    except FileNotFoundError:
        return {**result, "status": "SOURCE_BYTES_MISSING"}
    except (OSError, ValueError):
        return {**result, "status": "INVALID_SOURCE_REFERENCE"}
    digest = hashlib.sha256(payload).hexdigest()
    if digest != snapshot["manifest_sha256"]:
        return {**result, "status": "REGISTERED_CHECKSUM_NOT_VERIFIED", "actual_sha256": digest}
    target = output / "source-bytes" / digest[:2] / digest
    ImmutableFileStore(output).publish(str(target.relative_to(output)), payload)
    return {**result, "status": "BYTE_VERIFIED", "archive_path": str(target.relative_to(output))}


def cutoff_hash(connection: psycopg.Connection[Any], cutoff: datetime) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    with connection.cursor(name="baseline_cutoff") as cursor:
        cursor.execute(
            "SELECT to_jsonb(h)::text FROM football.product_eligible_history_at(%s) h "
            "ORDER BY fixture_id",
            (cutoff,),
        )
        for row in cursor:
            digest.update(row[0].encode() + b"\n")
            count += 1
    return {"rows": count, "sha256": digest.hexdigest()}


def verify_source_archive(root: Path) -> list[str]:
    failures = []
    for report in ("source-resources.json", "source-manifests.json"):
        for item in json.loads((root / report).read_text()):
            if item["status"] != "BYTE_VERIFIED":
                continue
            relative = validate_relative_posix_path(item["archive_path"])
            path = root / relative
            path.resolve().relative_to(root.resolve())
            if path.is_symlink() or not path.is_file() or file_sha256(path) != path.name:
                failures.append(relative)
    return failures


def capture_duplicates(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    canonical = connection.execute(
        """SELECT r.canonical_real_fixture_id::text,count(*)
           FROM football.product_serving_fixtures f JOIN football.fixture_identity_resolutions r
             ON r.member_fixture_id=f.fixture_id AND r.active
               AND r.resolution_status IN ('UNIQUE','DUPLICATE_RESOLVED')
           GROUP BY r.canonical_real_fixture_id HAVING count(*)>1 ORDER BY 1"""
    ).fetchall()
    native = connection.execute(
        """SELECT provider_id::text,provider_match_id,count(*)
           FROM football.match_provider_mappings WHERE valid_to IS NULL
             AND match_id IN (SELECT fixture_id FROM football.product_serving_fixtures)
           GROUP BY provider_id,provider_match_id HAVING count(*)>1 ORDER BY 1,2"""
    ).fetchall()
    return {
        "canonical_duplicates": canonical,
        "native_duplicates": native,
        "status": "FAIL" if canonical or native else "PASS",
    }


def compose_command(program: str, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "exec",
        "-T",
        "postgres",
        program,
        "--username",
        os.environ["POSTGRES_USER"],
        *args,
    ]


def capture_database(args: argparse.Namespace, output: Path) -> dict[str, Any]:
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        options="-c statement_timeout=300000",
        application_name="matchforge-architecture-v2-baseline",
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        state = connection.execute(
            "SELECT transaction_timestamp(),pg_export_snapshot(),current_database(),version()"
        ).fetchone()
        if state is None:
            raise RuntimeError("database did not return snapshot metadata")
        captured_at, snapshot, database, version = state
        report: dict[str, Any] = {
            "captured_at": captured_at.isoformat(),
            "snapshot": snapshot,
            "database": database,
            "postgres_version": version,
        }
        command = compose_command(
            "pg_dump",
            "--dbname",
            database,
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--snapshot",
            snapshot,
        )
        with (
            (output / "database.dump").open("xb") as dump,
            (output / "pg_dump.log").open("w") as log,
        ):
            process = subprocess.Popen(command, cwd=ROOT, stdout=dump, stderr=log)
            try:
                report["relations"] = capture_relations(connection, output)
                report["views"] = capture_relations(connection, output, views=True)
                report["cutoffs"] = {
                    cutoff.isoformat(): cutoff_hash(connection, cutoff)
                    for cutoff in sorted({captured_at, *args.cutoff})
                }
                report["duplicates"] = capture_duplicates(connection)
                write_json(
                    output / "history-coverage.json", history_coverage(connection, captured_at)
                )
                report["source_bytes"] = capture_sources(connection, output, args.data_root)
                write_json(
                    output / "locks.json",
                    [
                        row[0]
                        for row in connection.execute(
                            """SELECT to_jsonb(l) FROM (SELECT pid,locktype,database,relation,mode,
                              granted,waitstart,classid,objid,objsubid FROM pg_locks) l"""
                        )
                    ],
                )
                if process.wait(timeout=600) != 0:
                    raise RuntimeError("pg_dump failed; see pg_dump.log")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=30)
        write_json(output / "database-state.json", report)
    extract_schema(output)
    report["database_dump_sha256"] = file_sha256(output / "database.dump")
    report["schema_sha256"] = file_sha256(output / "schema.sql")
    return report


def extract_schema(output: Path) -> None:
    with (
        (output / "database.dump").open("rb") as dump,
        (output / "schema.sql").open("xb") as schema,
    ):
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "--file=-",
                "--schema-only",
                "--no-owner",
                "--no-acl",
            ],
            cwd=ROOT,
            stdin=dump,
            stdout=schema,
            check=True,
        )


def capture_api(base_url: str, days: Sequence[date], output: Path) -> dict[str, Any]:
    directory = output / "api"
    directory.mkdir()
    paths = ["/healthz", "/readyz", "/v1/admin/sync-runs"]
    paths.extend(
        "/v1/fixtures?" + urlencode({"date": day.isoformat(), "timezone": "Africa/Lagos"})
        for day in days
    )
    report: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "responses": []}
    for index, path in enumerate(paths):
        request = urllib.request.Request(
            base_url.rstrip("/") + path, headers={"Origin": "http://127.0.0.1:3000"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        target = directory / f"{index:02d}.json"
        target.write_bytes(payload)
        item: dict[str, Any] = {"path": path, "sha256": hashlib.sha256(payload).hexdigest()}
        if path in {"/healthz", "/readyz"}:
            item["status"] = json.loads(payload)["status"]
        if path.startswith("/v1/fixtures?"):
            groups = json.loads(payload)["groups"]
            fixtures = [fixture["id"] for group in groups for fixture in group["fixtures"]]
            competitions = [group["competition"]["id"] for group in groups]
            item.update(
                fixtures=len(fixtures),
                duplicate_fixture_ids=len(fixtures) - len(set(fixtures)),
                duplicate_competition_groups=len(competitions) - len(set(competitions)),
            )
        report["responses"].append(item)
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["consistency"] = (
        "HTTP responses are separately timed observations, outside the DB snapshot."
    )
    return report


def repository_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    return {
        "starting_sha": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "working_tree_status": git("status", "--short"),
        "migrations": {
            path.name: file_sha256(path)
            for path in sorted((ROOT / "infrastructure/migrations").glob("*.sql"))
        },
        "champion_sha256": file_sha256(CHAMPION),
    }


def utc_cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("cutoff must include a timezone")
    return parsed.astimezone(UTC)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("FOOTBALL_DATA_ROOT", ".local/football-data")),
    )
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--fixture-date", action="append", type=date.fromisoformat, default=[])
    parser.add_argument("--cutoff", action="append", type=utc_cutoff, default=[])
    parser.add_argument("--verify-restored-baseline", type=Path)
    args = parser.parse_args(argv)
    if not args.verify_restored_baseline and not args.fixture_date:
        parser.error("capture requires at least one --fixture-date")
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report: dict[str, Any] = {"phase": 0, "status": "INCOMPLETE", "repository": repository_state()}
    manifest = args.output / "manifest.json"
    write_json(manifest, report)
    if args.verify_restored_baseline:
        before = json.loads((args.verify_restored_baseline / "manifest.json").read_text())
        if before["status"] not in {"PASS", "PASS_WITH_WARNINGS"}:
            raise ValueError("cannot verify an incomplete or failed baseline")
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            report["relations"] = capture_relations(connection, args.output)
            report["cutoffs"] = {
                cutoff: cutoff_hash(connection, datetime.fromisoformat(cutoff))
                for cutoff in before["database"]["cutoffs"]
            }
        report["mismatched_relations"] = compare_relations(
            before["database"]["relations"], report["relations"]
        )
        report["mismatched_cutoffs"] = compare_relations(
            before["database"]["cutoffs"], report["cutoffs"]
        )
        report["invalid_source_archives"] = verify_source_archive(args.verify_restored_baseline)
        report["dump_checksum_matches"] = (
            file_sha256(args.verify_restored_baseline / "database.dump")
            == before["database"]["database_dump_sha256"]
        )
        failed = bool(
            report["mismatched_relations"]
            or report["mismatched_cutoffs"]
            or report["invalid_source_archives"]
            or not report["dump_checksum_matches"]
        )
        report["status"] = "FAIL" if failed else "PASS"
    else:
        report["database"] = capture_database(args, args.output)
        report["api"] = capture_api(args.api_base_url, args.fixture_date, args.output)
        failed = report["repository"]["champion_sha256"] != CHAMPION_SHA256
        failed |= report["database"]["duplicates"]["status"] != "PASS"
        failed |= [item.get("status") for item in report["api"]["responses"][:2]] != ["ok", "ready"]
        failed |= any(
            item.get("duplicate_fixture_ids") or item.get("duplicate_competition_groups")
            for item in report["api"]["responses"]
        )
        warnings = any(
            set(statuses) - {"BYTE_VERIFIED"}
            for statuses in report["database"]["source_bytes"].values()
        )
        report["status"] = "FAIL" if failed else "PASS_WITH_WARNINGS" if warnings else "PASS"
    report["finished_at"] = datetime.now(UTC).isoformat()
    write_json(manifest, report)
    print(json.dumps({"status": report["status"], "manifest": str(manifest)}))
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
