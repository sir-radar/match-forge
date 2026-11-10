"""Complete snapshot-bound capture and explicitly isolated recovery verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg import sql

from scripts.capture_architecture_v2_baseline import (
    ROOT,
    capture_relations,
    compare_relations,
    compose_command,
    cutoff_hash,
    repository_state,
    write_json,
)
from scripts.capture_architecture_v2_baseline import file_sha256 as digest_file
from scripts.recovery_files import (
    capture_files,
    registered_files,
    regular_file,
    restore_files,
    verify_files,
)


def global_fingerprint() -> str:
    with psycopg.connect(
        os.environ["DATABASE_URL"], options="-c default_transaction_read_only=on"
    ) as connection:
        roles = connection.execute(
            "SELECT to_jsonb(r)::text FROM pg_authid r ORDER BY rolname"
        ).fetchall()
        spaces = connection.execute(
            "SELECT to_jsonb(t)::text FROM pg_tablespace t ORDER BY spcname"
        ).fetchall()
    return hashlib.sha256(json.dumps([roles, spaces]).encode()).hexdigest()


def capture_recovery(output: Path, data_root: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report: dict[str, Any] = {
        "version": 1,
        "status": "INCOMPLETE",
        "repository": repository_state(),
    }
    write_json(output / "recovery.json", report)
    started = time.monotonic()
    globals_before = global_fingerprint()
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        options="-c default_transaction_read_only=on -c statement_timeout=300000",
        application_name="matchforge-manual-recovery-capture",
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        state = connection.execute(
            "SELECT transaction_timestamp(),pg_export_snapshot(),current_database(),version()"
        ).fetchone()
        assert state is not None
        captured_at, snapshot, database, version = state
        report.update(
            captured_at=captured_at.isoformat(),
            snapshot=snapshot,
            database=database,
            postgres_version=version,
        )
        with (output / "globals.sql").open("xb") as globals_file:
            subprocess.run(
                compose_command("pg_dumpall", "--globals-only"),
                cwd=ROOT,
                stdout=globals_file,
                stderr=subprocess.PIPE,
                check=True,
                timeout=60,
            )
        with (output / "database.dump").open("xb") as dump:
            process = subprocess.Popen(
                compose_command(
                    "pg_dump",
                    "--dbname",
                    database,
                    "--format=custom",
                    "--compress=0",
                    "--snapshot",
                    snapshot,
                ),
                cwd=ROOT,
                stdout=dump,
                stderr=subprocess.DEVNULL,
            )
            try:
                report["relations"] = capture_relations(connection, output)
                report["cutoffs"] = {captured_at.isoformat(): cutoff_hash(connection, captured_at)}
                refs = registered_files(connection, data_root)
                report["files"] = capture_files(
                    refs, {"data": data_root, "repository": ROOT}, output
                )
                report["extensions"] = connection.execute(
                    "SELECT extname,extversion FROM pg_extension ORDER BY extname"
                ).fetchall()
                if process.wait(timeout=3600) != 0:
                    raise RuntimeError("database snapshot dump failed")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=30)
        connection.rollback()
    if global_fingerprint() != globals_before:
        raise ValueError("global database metadata changed during capture; retry manually")
    report["global_metadata_fingerprint"] = globals_before
    # The repository archive supplies exact code, migrations, schemas, locks and
    # example configuration. Local credentials must be recovered separately.
    with (output / "application.tar").open("xb") as application:
        subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, stdout=application, check=True)
    report["checksums"] = {
        name: digest_file(output / name)
        for name in ("database.dump", "globals.sql", "application.tar", "recovery-files.json")
    }
    report["duration_seconds"] = time.monotonic() - started
    report["status"] = "CAPTURED" if report["files"]["status"] == "COMPLETE" else "INCOMPLETE"
    report["restore_verified"] = False
    write_json(output / "recovery.json", report)
    return report


def verify_capture(root: Path) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(regular_file(root, "recovery.json").read_text())
    if report["version"] != 1 or report["status"] != "CAPTURED":
        raise ValueError("incomplete or unsupported recovery capture")
    if verify_files(root):
        raise ValueError("recovery file verification failed")
    required = {"database.dump", "globals.sql", "application.tar", "recovery-files.json"}
    if set(report["checksums"]) != required:
        raise ValueError("incomplete recovery checksums")
    for name, digest in report["checksums"].items():
        if digest_file(regular_file(root, name)) != digest:
            raise ValueError("recovery checksum verification failed")
    return report


def verify_restore(root: Path, destination: Path) -> dict[str, Any]:
    report = verify_capture(root)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    restore_files(root, {"data": destination / "data", "repository": destination / "repository"})
    database = "football_restore_test_" + uuid4().hex
    started = time.monotonic()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as control:
        # New random database only; there is no caller-supplied operating target.
        control.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database))
        )
        try:
            with (root / "database.dump").open("rb") as dump:
                subprocess.run(
                    compose_command(
                        "pg_restore",
                        "--dbname",
                        database,
                        "--exit-on-error",
                        "--no-owner",
                        "--no-acl",
                    ),
                    cwd=ROOT,
                    stdin=dump,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True,
                    timeout=3600,
                )
            params = psycopg.conninfo.make_conninfo(os.environ["DATABASE_URL"], dbname=database)
            with psycopg.connect(params) as restored:
                restored.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                restored.execute("SET LOCAL TIME ZONE 'UTC'")
                relations = capture_relations(restored, destination)
                cutoffs = {
                    cutoff: cutoff_hash(restored, datetime.fromisoformat(cutoff))
                    for cutoff in report["cutoffs"]
                }
                extensions = restored.execute(
                    "SELECT extname,extversion FROM pg_extension ORDER BY extname"
                ).fetchall()
                if (
                    compare_relations(report["relations"], relations)
                    or compare_relations(report["cutoffs"], cutoffs)
                    or [list(row) for row in extensions] != report["extensions"]
                ):
                    raise ValueError("restored database verification failed")
                refs = registered_files(restored, destination / "data")
                verify_dir = destination / "reference-check"
                verified = capture_files(
                    refs,
                    {"data": destination / "data", "repository": destination / "repository"},
                    verify_dir,
                )
                if verified["status"] != "COMPLETE":
                    raise ValueError("restored snapshot-to-file verification failed")
        finally:
            if not re.fullmatch(r"football_restore_test_[0-9a-f]{32}", database):
                raise ValueError("unsafe restore database")
            control.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
    result = {
        "status": "PASS",
        "database_isolated": True,
        "duration_seconds": time.monotonic() - started,
        "verified_at": datetime.now(UTC).isoformat(),
        "global_role_restore": "NOT_RUN: apply globals only to a new isolated cluster",
    }
    write_json(destination / "verification.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--data-root", type=Path, required=True)
    restore = sub.add_parser("verify-restore")
    restore.add_argument("--capture", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    result = (
        capture_recovery(args.output, args.data_root)
        if args.action == "capture"
        else verify_restore(args.capture, args.destination)
    )
    print(json.dumps({"status": result["status"]}))
    if result["status"] == "INCOMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
