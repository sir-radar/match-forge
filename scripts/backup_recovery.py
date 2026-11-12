"""Complete snapshot-bound capture and explicitly isolated recovery verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from football.integrity import PostgresIntegrityVerifier
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
from scripts.recovery_scope import (
    EMPTY_SHA256,
    inventory,
    load_plan,
    require_inventory_database,
    selected_inventory,
    validate_gaps,
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


def require_compose_database(connection: psycopg.Connection[Any], database: str) -> None:
    query = (
        "SELECT system_identifier::text||'|'||"
        "(SELECT oid::text FROM pg_database WHERE datname=current_database()) "
        "FROM pg_control_system()"
    )
    expected = connection.execute(query).fetchone()
    actual = subprocess.check_output(
        compose_command("psql", "--dbname", database, "-Atc", query),
        cwd=ROOT,
        text=True,
    ).strip()
    if expected is None or actual != expected[0]:
        raise ValueError("dump transport differs from selected database identity")


def recovery_estimate(
    data_root: Path,
    recovery_plan: dict[str, Any] | None = None,
    *,
    use_reviewed_estimate: bool = False,
) -> dict[str, int]:
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        row = connection.execute("SELECT pg_database_size(current_database())").fetchone()
        assert row is not None
        if recovery_plan is not None and use_reviewed_estimate:
            require_inventory_database(connection, recovery_plan)
            referenced_files = recovery_plan["available_files"]
            referenced_bytes = recovery_plan["logical_bytes"]
        elif recovery_plan is None:
            refs = registered_files(connection, data_root)
            referenced_bytes = sum(
                regular_file(data_root if ref.root == "data" else ROOT, ref.path).stat().st_size
                for ref in refs
            )
            referenced_files = len(refs)
        else:
            selected = selected_inventory(connection, data_root, recovery_plan)
            referenced_files = len(selected["references"])
            referenced_bytes = selected["logical_bytes"]
        connection.rollback()
    return {
        "referenced_files": referenced_files,
        "referenced_bytes": referenced_bytes,
        "estimated_staging_bytes": int(row[0]) + referenced_bytes,
    }


def capture_recovery(
    output: Path, data_root: Path, recovery_plan: dict[str, Any] | None = None
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report: dict[str, Any] = {
        "version": 1,
        "status": "INCOMPLETE",
        "repository": repository_state(),
    }
    report["capture_process_configuration"] = {
        name: os.environ[name]
        for name in (
            "API_ADDR",
            "WEB_ORIGIN",
            "FOOTBALL_DATA_ROOT",
            "MATCHFORGE_REPO_ROOT",
            "MATCHFORGE_OPERATIONAL_SYNC_INTERVAL",
            "MATCHFORGE_HISTORY_SYNC_ENABLED",
            "MATCHFORGE_HISTORY_SYNC_INTERVAL",
            "MATCHFORGE_FOTMOB_ENABLED",
            "MATCHFORGE_PITCHAPI_ENABLED",
        )
        if name in os.environ
    }
    report["configuration_limit"] = (
        "Capture process settings, not proof of the running release configuration. "
        "Database, provider and Admin credentials must be recovered or replaced separately."
    )
    report["data_root"] = str(data_root.resolve())
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
        require_compose_database(connection, database)
        database_size = connection.execute("SELECT pg_database_size(current_database())").fetchone()
        assert database_size is not None
        report["database_size_bytes"] = database_size[0]
        database_owner = connection.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        assert database_owner is not None
        report.update(
            captured_at=captured_at.isoformat(),
            snapshot=snapshot,
            database=database,
            postgres_version=version,
            database_owner=database_owner[0],
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
                prior_cutoffs = connection.execute(
                    "SELECT min(football_cutoff),min(knowledge_cutoff) "
                    "FROM football.product_forecasts"
                ).fetchone()
                cutoffs = {
                    captured_at,
                    *(value for value in (prior_cutoffs or ()) if value is not None),
                }
                report["cutoffs"] = {
                    cutoff.isoformat(): cutoff_hash(connection, cutoff)
                    for cutoff in sorted(cutoffs)
                }
                if recovery_plan is None:
                    refs = registered_files(connection, data_root)
                else:
                    selected = selected_inventory(connection, data_root, recovery_plan)
                    refs = selected["references"]
                    report["recovery_scope"] = {
                        "scope": "RECOVERABLE_ONLY",
                        "full_recovery": False,
                        "unavailable": selected["unavailable"],
                        "unavailable_sha256": selected["unavailable_sha256"],
                        "excluded": selected["excluded"],
                        "excluded_sha256": selected["excluded_sha256"],
                    }
                report["files"] = capture_files(
                    refs, {"data": data_root, "repository": ROOT}, output
                )
                if recovery_plan is not None:
                    report["artifact_reader_results"] = artifact_reader_results(
                        connection, output / "files/data"
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
    if report["files"]["status"] == "COMPLETE":
        report["status"] = "CAPTURED_RECOVERABLE" if recovery_plan is not None else "CAPTURED"
    report["restore_verified"] = False
    write_json(output / "recovery.json", report)
    return report


def verify_capture(root: Path, *, allow_recoverable: bool = False) -> dict[str, Any]:
    report: dict[str, Any] = json.loads(regular_file(root, "recovery.json").read_text())
    accepted = {"CAPTURED", "CAPTURED_RECOVERABLE"} if allow_recoverable else {"CAPTURED"}
    if report["version"] != 1 or report["status"] not in accepted:
        raise ValueError("incomplete or unsupported recovery capture")
    scope = report.get("recovery_scope")
    if (report["status"] == "CAPTURED_RECOVERABLE") != (scope is not None):
        raise ValueError("recovery scope does not match capture status")
    if scope is not None:
        validate_gaps(scope)
        if scope["full_recovery"] is not False:
            raise ValueError("recoverable capture cannot claim full recovery")
    if verify_files(root):
        raise ValueError("recovery file verification failed")
    required = {"database.dump", "globals.sql", "application.tar", "recovery-files.json"}
    if set(report["checksums"]) != required:
        raise ValueError("incomplete recovery checksums")
    for name, digest in report["checksums"].items():
        if digest_file(regular_file(root, name)) != digest:
            raise ValueError("recovery checksum verification failed")
    return report


def artifact_reader_results(
    connection: psycopg.Connection[Any], data_root: Path
) -> list[dict[str, object]]:
    verifier = PostgresIntegrityVerifier(connection, data_root)
    results = []
    for (identity,) in connection.execute("SELECT id FROM football.dataset_versions ORDER BY id"):
        results.append(verifier.verify_dataset(identity).to_dict())
    for (identity,) in connection.execute("SELECT id FROM football.model_artifacts ORDER BY id"):
        results.append(verifier.verify_model_artifact(identity).to_dict())
    return results


RELOCATED_EVIDENCE = ".recovered-evidence"


def restore_application(archive: Path, repository: Path) -> dict[str, str]:
    """Restore regular tracked files only; never follow archive links or lose evidence.

    A record may register an older version of a tracked file. When the current
    application file has the same path, the retained bytes move unchanged to a
    content-addressed path and the returned locations map their checksum to it.
    """
    from football.contracts.source import validate_relative_posix_path

    relocated: dict[str, str] = {}
    with tarfile.open(archive / "application.tar") as application:
        for member in application.getmembers():
            name = member.name.rstrip("/")
            validate_relative_posix_path(name)
            if not (member.isfile() or member.isdir()):
                raise ValueError("application archive contains a link or special file")
            if name == RELOCATED_EVIDENCE or name.startswith(RELOCATED_EVIDENCE + "/"):
                raise ValueError("application archive uses the relocated evidence path")
        for member in application.getmembers():
            target = repository / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            source = application.extractfile(member)
            assert source is not None
            with source:
                payload = source.read()
            if target.exists():
                existing = regular_file(repository, member.name)
                retained = digest_file(existing)
                if hashlib.sha256(payload).hexdigest() == retained:
                    continue
                location = f"{RELOCATED_EVIDENCE}/{retained}"
                kept = repository / location
                kept.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                if kept.exists():
                    if digest_file(regular_file(repository, location)) != retained:
                        raise ValueError("relocated evidence conflicts with retained evidence")
                    existing.unlink()
                else:
                    existing.rename(kept)
                relocated[retained] = location
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with target.open("xb") as output:
                output.write(payload)
            target.chmod(member.mode & 0o777)
    return relocated


def verify_artifact_readers(connection: psycopg.Connection[Any], data_root: Path) -> dict[str, int]:
    verifier = PostgresIntegrityVerifier(connection, data_root)
    counts = {"datasets": 0, "models": 0}
    for (identity,) in connection.execute("SELECT id FROM football.dataset_versions ORDER BY id"):
        if verifier.verify_dataset(identity).status != "PASS":
            raise ValueError("restored dataset is incompatible with its registered reader")
        counts["datasets"] += 1
    for (identity,) in connection.execute("SELECT id FROM football.model_artifacts ORDER BY id"):
        if verifier.verify_model_artifact(identity).status != "PASS":
            raise ValueError("restored model is incompatible with its registered reader")
        counts["models"] += 1
    return counts


def verify_restore(
    root: Path, destination: Path, *, allow_recoverable: bool = False
) -> dict[str, Any]:
    report = verify_capture(root, allow_recoverable=allow_recoverable)
    require_restore_storage(report, root, destination)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    restore_files(root, {"data": destination / "data", "repository": destination / "repository"})
    relocated = restore_application(root, destination / "repository")
    database = "football_restore_test_" + uuid4().hex
    started = time.monotonic()
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as control:
        if database == control.info.dbname:
            raise ValueError("restore target equals source database")
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
                artifact_readers = verify_restored_dependencies(
                    restored, destination, report, relocated
                )
        finally:
            if not re.fullmatch(r"football_restore_test_[0-9a-f]{32}", database):
                raise ValueError("unsafe restore database")
            control.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )
    result = {
        "status": "PASS_RECOVERABLE" if report.get("recovery_scope") else "PASS",
        "full_recovery": False,
        "unavailable_dependencies": len(report.get("recovery_scope", {}).get("unavailable", [])),
        "database_isolated": True,
        "duration_seconds": time.monotonic() - started,
        "verified_at": datetime.now(UTC).isoformat(),
        "global_role_restore": "NOT_RUN: apply globals only to a new isolated cluster",
        "registered_artifact_readers": artifact_readers,
    }
    write_json(destination / "verification.json", result)
    return result


def verify_cluster_restore(root: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Replay global roles and original ownership outside the source cluster."""
    source = subprocess.check_output(
        ["docker", "compose", "ps", "-q", "postgres"], cwd=ROOT, text=True, timeout=15
    ).strip()
    image = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Image}}", source], text=True, timeout=15
    ).strip()
    container = "matchforge-backup-restore-" + uuid4().hex
    admin = "recovery_drill_" + uuid4().hex
    command = ["docker", "exec", container]
    started = time.monotonic()
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--pull=never",
                "--name",
                container,
                "--network",
                "none",
                "--env",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "--env",
                f"POSTGRES_USER={admin}",
                "--env",
                "POSTGRES_DB=postgres",
                image,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
            timeout=30,
        )
        wait_for_restore_cluster(command, admin)
        with (root / "globals.sql").open("rb") as globals_file:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "psql",
                    "-U",
                    admin,
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                stdin=globals_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                timeout=120,
            )
        with (root / "database.dump").open("rb") as dump:
            subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    admin,
                    "-d",
                    "template1",
                    "--create",
                    "--exit-on-error",
                ],
                stdin=dump,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=True,
                timeout=3600,
            )
        verify_cluster_catalog(command, admin, report)
    finally:
        cleanup = subprocess.run(
            ["docker", "rm", "--force", "--volumes", container],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if cleanup.returncode and "No such container" not in cleanup.stderr:
            cleanup.check_returncode()
    return {
        "status": "PASS",
        "network": "none",
        "globals_applied": True,
        "original_ownership_restored": True,
        "duration_seconds": time.monotonic() - started,
    }


def wait_for_restore_cluster(command: list[str], admin: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        ready = subprocess.run(
            [*command, "pg_isready", "-h", "127.0.0.1", "-U", admin, "-d", "postgres"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.2)
    raise ValueError("isolated PostgreSQL did not become ready")


def verify_cluster_catalog(command: list[str], admin: str, report: dict[str, Any]) -> None:
    expected = {name: item["rows"] for name, item in report["relations"].items()}
    counts = (
        sql.SQL(" UNION ALL ")
        .join(
            sql.SQL("SELECT {}::text AS name,count(*) AS rows FROM {}").format(
                sql.Literal(name), sql.Identifier(*name.split(".", 1))
            )
            for name in sorted(expected)
        )
        .as_string(None)
    )
    query = (
        "SELECT json_build_object('owner',pg_get_userbyid(datdba),"
        "'extensions',(SELECT json_agg(json_build_array(extname,extversion) ORDER BY extname)"
        " FROM pg_extension),'counts',(SELECT json_object_agg(name,rows) FROM ("
        + counts
        + ") restored)) FROM pg_database WHERE datname=current_database()"
    )
    metadata = json.loads(
        subprocess.check_output(
            [
                *command,
                "psql",
                "-U",
                admin,
                "-d",
                report["database"],
                "-At",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                query,
            ],
            text=True,
            timeout=600,
        )
    )
    if (
        metadata["owner"] != report["database_owner"]
        or metadata["extensions"] != [list(row) for row in report["extensions"]]
        or metadata["counts"] != expected
    ):
        raise ValueError("isolated cluster ownership, extensions or relation counts differ")


def verify_restored_dependencies(
    connection: psycopg.Connection[Any],
    destination: Path,
    report: dict[str, Any],
    relocated: dict[str, str] | None = None,
) -> dict[str, Any]:
    locations = relocated or {}
    scope = report.get("recovery_scope")
    if scope is not None:
        selected = inventory(
            connection, destination / "data", destination / "repository", locations
        )
        if selected["unavailable_sha256"] != scope["unavailable_sha256"] or selected[
            "excluded_sha256"
        ] != scope.get("excluded_sha256", EMPTY_SHA256):
            raise ValueError("restored unavailable dependencies differ from the captured inventory")
        readers = artifact_reader_results(connection, destination / "data")
        if readers != report["artifact_reader_results"]:
            raise ValueError("restored artifact reader results differ from the captured results")
        return {"results": readers, "full_recovery": False}
    refs = [
        replace(ref, source_path=locations[ref.sha256])
        if ref.root == "repository" and ref.sha256 in locations
        else ref
        for ref in registered_files(
            connection, destination / "data", repository_root=destination / "repository"
        )
    ]
    verified = capture_files(
        refs,
        {"data": destination / "data", "repository": destination / "repository"},
        destination / "reference-check",
    )
    if verified["status"] != "COMPLETE":
        raise ValueError("restored snapshot-to-file verification failed")
    return verify_artifact_readers(connection, destination / "data")


def require_restore_storage(report: dict[str, Any], root: Path, destination: Path) -> None:
    configured = Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data")))
    if destination.resolve().is_relative_to(configured.resolve()):
        raise ValueError("isolated restore must be outside the operating data root")
    source = report.get("data_root")
    if source and destination.resolve().is_relative_to(Path(source).resolve()):
        raise ValueError("isolated restore must be outside the source data root")
    parent = destination.parent
    while not parent.exists():
        parent = parent.parent
    required = report["files"]["logical_bytes"] + report.get(
        "database_size_bytes", (root / "database.dump").stat().st_size
    )
    if shutil.disk_usage(parent).free < required:
        raise ValueError("insufficient storage for the isolated restore estimate")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--data-root", type=Path, required=True)
    capture.add_argument("--recoverable-inventory", type=Path)
    restore = sub.add_parser("verify-restore")
    restore.add_argument("--capture", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    restore.add_argument("--allow-recoverable", action="store_true")
    args = parser.parse_args()
    result = (
        capture_recovery(
            args.output,
            args.data_root,
            load_plan(args.recoverable_inventory) if args.recoverable_inventory else None,
        )
        if args.action == "capture"
        else verify_restore(
            args.capture, args.destination, allow_recoverable=args.allow_recoverable
        )
    )
    print(json.dumps({"status": result["status"]}))
    if result["status"] == "INCOMPLETE":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
