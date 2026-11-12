from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

from scripts import backup_destination, manual_backup
from scripts.backup_destination import BackupConfig, Restic, credential_environment
from scripts.backup_recovery import capture_recovery, verify_capture, verify_restore
from scripts.capture_architecture_v2_baseline import ROOT, compose_command


def test_complete_snapshot_file_restore_isolated_from_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = "football_storage_test_" + uuid4().hex[:16]
    subprocess.run(compose_command("createdb", database), cwd=ROOT, check=True)
    try:
        url = make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=database)
        subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "postgres", url, "up"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        monkeypatch.setenv("DATABASE_URL", url)
        source = tmp_path / "source"
        source.mkdir()
        payload = b'{"retained_original":42}'
        digest = hashlib.sha256(payload).hexdigest()
        (source / "source.json").write_bytes(payload)
        with psycopg.connect(url) as connection:
            provider = connection.execute(
                "INSERT INTO football.providers(code,name,source_type) "
                "VALUES ('recovery_test','Recovery test','file_download') RETURNING id"
            ).fetchone()[0]
            snapshot = connection.execute(
                "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
                "acquired_at,manifest_path,manifest_sha256,status) "
                "VALUES (%s,'test','v1',now(),'source.json',%s,'validated') RETURNING id",
                (provider, digest),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO football.source_resources(source_snapshot_id,provider_path,sha256,"
                "size_bytes,media_type,parse_status,validation_status,acquired_at) "
                "VALUES (%s,'native.json',%s,%s,'application/json','parsed','valid',now())",
                (snapshot, digest, len(payload)),
            )
        archive = tmp_path / "capture"
        assert capture_recovery(archive, source)["status"] == "CAPTURED"
        source.rename(tmp_path / "original-unavailable")
        restored = tmp_path / "restored"
        result = verify_restore(archive, restored)
        assert result["status"] == "PASS"
        assert result["database_isolated"] is True
        assert result["full_recovery"] is False
        assert (restored / "data/source.json").read_bytes() == payload
        independent = tmp_path / "independent-application"
        independent.mkdir()
        verify_capture(archive)
        with tarfile.open(archive / "application.tar") as application:
            application.extractall(independent, filter="data")
        replay = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; "
                "import football; import scripts.backup_recovery as recovery; "
                "assert Path(recovery.__file__).is_relative_to(Path.cwd()); "
                "assert Path(football.__file__).is_relative_to(Path.cwd()); "
                "recovery.verify_restore(Path(sys.argv[1]),Path(sys.argv[2]))",
                str(archive),
                str(tmp_path / "independent-restored"),
            ],
            cwd=independent,
            env={**os.environ, "PYTHONPATH": str(independent / "python/football/src")},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert replay.returncode == 0, replay.stdout + replay.stderr
        restore_fresh_cluster(archive, database, digest)
        password = tmp_path / "recovery-password"
        password.write_text("disposable-fixture-password-only")
        password.chmod(0o600)
        enrollment = BackupConfig(tmp_path, "fixture-volume", "", str(password), "")
        (tmp_path / "MatchForgeBackup").mkdir()
        restic = Restic(tmp_path / "MatchForgeBackup", credential_environment(enrollment))
        restic.run("init", "--repository-version", "2")
        enrolled = BackupConfig(tmp_path, "fixture-volume", restic.identity(), str(password), "")
        monkeypatch.setattr(
            backup_destination,
            "inspect_volume",
            lambda _: {
                "volume_uuid": "fixture-volume",
                "filesystem": "test-fixture",
                "filesystem_encrypted": False,
                "free_bytes": 800_000_000_000,
                "capacity_bytes": 1_000_000_000_000,
                "device_id": tmp_path.stat().st_dev,
            },
        )
        monkeypatch.setattr(manual_backup, "inspect_volume", backup_destination.inspect_volume)
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(restored / "data"))
        monkeypatch.delenv("MATCHFORGE_SYNC_RUN_ID", raising=False)
        backup = manual_backup.backup(enrolled, admin=True)
        assert backup["scope"] == "FULL_RECOVERY"
        assert backup["full_operating_restore_drill"]["global_role_restore"]["status"] == "PASS"
        assert backup["full_operating_restore_drill"]["full_recovery"] is True
        assert backup["status"] == "VERIFIED"
        assert backup["verified"] is True
        assert backup["repository_file_bytes"] > 0
        (tmp_path / "manual-backup-result.json").write_text(
            json.dumps(
                {
                    **backup,
                    "isolated_restore_seconds": result["duration_seconds"],
                    "database_dump_bytes": (archive / "database.dump").stat().st_size,
                    "referenced_file_bytes": len(payload),
                    "global_roles_and_ownership_restored": True,
                    "independent_application_restore": replay.returncode == 0,
                },
                indent=2,
            )
            + "\n"
        )
        verified_points = json.loads(
            restic.run("snapshots", "--json", "--tag", "matchforge-verified")
        )
        assert verified_points[0]["id"] == backup["snapshot_id"]
        with psycopg.connect(url) as connection:
            assert (
                connection.execute("SELECT count(*) FROM football.source_resources").fetchone()[0]
                == 1
            )
        (archive / "files/data/source.json").write_bytes(b"corrupt")
        with pytest.raises(ValueError, match="verification"):
            verify_capture(archive)
    finally:
        subprocess.run(compose_command("dropdb", "--force", database), cwd=ROOT, check=True)


def restore_fresh_cluster(archive: Path, database: str, digest: str) -> None:
    container = "matchforge-recovery-test-" + uuid4().hex
    source = subprocess.check_output(
        ["docker", "compose", "ps", "-q", "postgres"],
        cwd=ROOT,
        text=True,
    ).strip()
    image = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Image}}", source],
        text=True,
    ).strip()
    subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--network",
            "none",
            "--env",
            "POSTGRES_USER=recovery_drill",
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            image,
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    try:
        for _ in range(100):
            if (
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        container,
                        "pg_isready",
                        "-h",
                        "127.0.0.1",
                        "-U",
                        "recovery_drill",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.1)
        else:
            raise AssertionError("isolated recovery PostgreSQL did not become ready")
        with (archive / "globals.sql").open("rb") as globals_file:
            restore = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "psql",
                    "-U",
                    "recovery_drill",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                stdin=globals_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            assert restore.returncode == 0, restore.stderr.decode()
        with (archive / "database.dump").open("rb") as dump:
            restore = subprocess.run(
                [
                    "docker",
                    "exec",
                    "-i",
                    container,
                    "pg_restore",
                    "-U",
                    "recovery_drill",
                    "-d",
                    "postgres",
                    "--create",
                    "--exit-on-error",
                ],
                stdin=dump,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            assert restore.returncode == 0, restore.stderr.decode()
        actual = subprocess.check_output(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "recovery_drill",
                "-d",
                database,
                "-Atc",
                "SELECT sha256 FROM football.source_resources",
            ],
            text=True,
        ).strip()
        assert actual == digest
        owner = subprocess.check_output(
            [
                "docker",
                "exec",
                container,
                "psql",
                "-U",
                "recovery_drill",
                "-d",
                database,
                "-Atc",
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='football'",
            ],
            text=True,
        ).strip()
        assert owner == os.environ["POSTGRES_USER"]
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", container],
            stdout=subprocess.DEVNULL,
            check=True,
        )


def test_declared_missing_sources_restore_without_claiming_full_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.recovery_scope import inventory

    database = "football_storage_test_" + uuid4().hex[:16]
    subprocess.run(compose_command("createdb", database), cwd=ROOT, check=True)
    try:
        url = make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=database)
        subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "postgres", url, "up"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        monkeypatch.setenv("DATABASE_URL", url)
        source = tmp_path / "source"
        source.mkdir()
        payload = b"retained original"
        digest = hashlib.sha256(payload).hexdigest()
        (source / "original.json").write_bytes(payload)
        with psycopg.connect(url) as connection:
            provider = connection.execute(
                "INSERT INTO football.providers(code,name,source_type) "
                "VALUES ('recovery_test','Recovery test','file_download') RETURNING id"
            ).fetchone()[0]
            for path in ("original.json", "unavailable.json"):
                connection.execute(
                    "INSERT INTO football.source_snapshots(provider_id,source_identity,"
                    "source_revision,acquired_at,manifest_path,manifest_sha256,status) "
                    "VALUES (%s,%s,'v1',now(),%s,%s,'validated')",
                    (provider, path, path, digest),
                )
        with psycopg.connect(url) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            selected = inventory(connection, source, ROOT, {})
            oid = connection.execute(
                "SELECT oid::text FROM pg_database WHERE datname=current_database()"
            ).fetchone()[0]
        plan = {
            "scope": "RECOVERABLE_ONLY",
            "locations": {},
            "database": database,
            "database_oid": oid,
            "unavailable_sha256": selected["unavailable_sha256"],
            "unavailable": selected["unavailable"],
        }
        assert len(plan["unavailable"]) == 1
        archive = tmp_path / "capture"
        report = capture_recovery(archive, source, plan)
        assert report["status"] == "CAPTURED_RECOVERABLE"
        assert report["recovery_scope"]["full_recovery"] is False
        with pytest.raises(ValueError, match="incomplete"):
            verify_capture(archive)
        source.rename(tmp_path / "unavailable-originals")
        restored = tmp_path / "restored"
        result = verify_restore(archive, restored, allow_recoverable=True)
        assert result["status"] == "PASS_RECOVERABLE"
        assert result["full_recovery"] is False
        assert result["unavailable_dependencies"] == 1
        assert (restored / "data/original.json").read_bytes() == payload
        assert not (restored / "data/unavailable.json").exists()
        assert (restored / "repository/uv.lock").is_file()
        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(restored / "data"))
        password = tmp_path / "password"
        password.write_text("disposable-fixture-password")
        password.chmod(0o600)
        (tmp_path / "MatchForgeBackup").mkdir()
        config = BackupConfig(tmp_path, "fixture", "", str(password), "")
        restic = Restic(tmp_path / "MatchForgeBackup", credential_environment(config))
        restic.run("init", "--repository-version", "2")
        config = BackupConfig(tmp_path, "fixture", restic.identity(), str(password), "")

        def volume(_: BackupConfig) -> dict[str, int]:
            return {
                "free_bytes": 800_000_000_000,
                "capacity_bytes": 1_000_000_000_000,
                "device_id": tmp_path.stat().st_dev,
            }

        monkeypatch.setattr(backup_destination, "inspect_volume", volume)
        monkeypatch.setattr(manual_backup, "inspect_volume", volume)
        monkeypatch.delenv("MATCHFORGE_SYNC_RUN_ID", raising=False)
        backed_up = manual_backup.backup(config, plan, admin=True)
        assert backed_up["scope"] == "RECOVERABLE_ONLY"
        assert backed_up["unavailable_sha256"] == plan["unavailable_sha256"]
        assert backed_up["status"] == "VERIFIED_RECOVERABLE"
        assert backed_up["full_recovery"] is False
        assert backed_up["full_operating_restore_drill"]["status"] == "PASS_RECOVERABLE"
        assert json.loads(restic.run("snapshots", "--json", "--tag", "matchforge-verified")) == []
        points = json.loads(
            restic.run("snapshots", "--json", "--tag", "matchforge-recoverable-verified")
        )
        assert points[0]["id"] == backed_up["snapshot_id"]
        monkeypatch.setenv("MATCHFORGE_SYNC_RUN_ID", str(uuid4()))
        with pytest.raises(backup_destination.BackupError, match="confirmed policy"):
            manual_backup.backup(config, plan, tmp_path / "rejected-admin")
        changed = {**plan, "unavailable_sha256": "0" * 64}
        with pytest.raises(ValueError, match="changed"):
            capture_recovery(tmp_path / "changed-capture", restored / "data", changed)
    finally:
        subprocess.run(compose_command("dropdb", "--force", database), cwd=ROOT, check=True)


def test_governed_scope_restores_every_original_and_only_skips_approved_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime

    from scripts.recovery_dispositions import Approval, Retirement, record_dispositions
    from scripts.recovery_scope import GOVERNED_SCOPE, inventory, validate_governed

    database = "football_storage_test_" + uuid4().hex[:16]
    subprocess.run(compose_command("createdb", database), cwd=ROOT, check=True)
    try:
        url = make_conninfo(os.environ["TEST_DATABASE_URL"], dbname=database)
        subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "postgres", url, "up"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        monkeypatch.setenv("DATABASE_URL", url)
        source = tmp_path / "source"
        source.mkdir()
        payload = b"retained original"
        digest = hashlib.sha256(payload).hexdigest()
        (source / "original.json").write_bytes(payload)
        suffix = uuid4().hex
        with psycopg.connect(url) as connection:
            real = connection.execute(
                "INSERT INTO football.providers(code,name,source_type) "
                "VALUES ('governed_test','Governed test','file_download') RETURNING id"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO football.source_snapshots(provider_id,source_identity,"
                "source_revision,acquired_at,manifest_path,manifest_sha256,status) "
                "VALUES (%s,'original.json','v1',now(),'original.json',%s,'validated')",
                (real, digest),
            )
            synthetic = connection.execute(
                "INSERT INTO football.providers(code,name,source_type) "
                "VALUES (%s,'Synthetic','git_repository') RETURNING id",
                (f"provider_{suffix}",),
            ).fetchone()[0]
            snapshot = connection.execute(
                "INSERT INTO football.source_snapshots(provider_id,source_identity,"
                "source_revision,git_sha,acquired_at,manifest_path,manifest_sha256,status) "
                "VALUES (%s,%s,%s,%s,now(),%s,%s,'acquired') RETURNING id",
                (
                    synthetic,
                    f"example/open-data/{suffix}",
                    "b" * 40,
                    "b" * 40,
                    f"manifests/{suffix}.json",
                    "a" * 64,
                ),
            ).fetchone()[0]
            record_dispositions(
                connection,
                (
                    Retirement(
                        "source_snapshots",
                        str(snapshot),
                        f"manifests/{suffix}.json",
                        "a" * 64,
                        "evidence.json",
                        "1" * 64,
                    ),
                ),
                (),
                Approval("GOVERNED_TEST_DECISION", datetime.now(UTC), "a" * 40),
            )
        with psycopg.connect(url) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            selected = inventory(connection, source, ROOT, {})
            oid = connection.execute(
                "SELECT oid::text FROM pg_database WHERE datname=current_database()"
            ).fetchone()[0]
        plan = {
            "scope": "RECOVERABLE_ONLY",
            "locations": {},
            "database": database,
            "database_oid": oid,
            **{
                key: selected[key]
                for key in (
                    "unavailable",
                    "unavailable_sha256",
                    "excluded",
                    "excluded_sha256",
                    "governed_sha256",
                )
            },
        }
        assert plan["unavailable"] == [] and len(plan["excluded"]) == 1
        validate_governed(plan)
        archive = tmp_path / "capture"
        report = capture_recovery(archive, source, plan, governed=True)
        assert report["status"] == "CAPTURED_GOVERNED"
        assert report["recovery_scope"]["scope"] == GOVERNED_SCOPE
        assert report["recovery_scope"]["full_recovery"] is False
        # FULL_RECOVERY and RECOVERABLE_ONLY verifiers never accept a governed capture.
        for kwargs in ({}, {"allow_recoverable": True}):
            with pytest.raises(ValueError, match="unsupported"):
                verify_capture(archive, **kwargs)
        source.rename(tmp_path / "unavailable-originals")
        restored = tmp_path / "restored"
        result = verify_restore(archive, restored, allow_governed=True)
        assert result["status"] == "PASS_GOVERNED_SCOPE"
        assert result["full_recovery"] is False
        assert result["unavailable_dependencies"] == 0
        assert result["excluded_dependencies"] == 1
        assert result["governed_sha256"] == plan["governed_sha256"]
        assert (restored / "data/original.json").read_bytes() == payload
        # A tampered approval binding fails against the restored database's own records.
        tampered = tmp_path / "tampered"
        subprocess.run(["cp", "-R", str(archive), str(tampered)], check=True)
        recorded = json.loads((tampered / "recovery.json").read_text())
        recorded["recovery_scope"]["governed_sha256"] = "f" * 64
        (tampered / "recovery.json").write_text(json.dumps(recorded))
        with pytest.raises(ValueError, match="governed scope differs"):
            verify_restore(tampered, tmp_path / "tampered-restore", allow_governed=True)

        monkeypatch.setenv("FOOTBALL_DATA_ROOT", str(restored / "data"))
        password = tmp_path / "password"
        password.write_text("disposable-fixture-password")
        password.chmod(0o600)
        (tmp_path / "MatchForgeBackup").mkdir()
        config = BackupConfig(tmp_path, "fixture", "", str(password), "")
        restic = Restic(tmp_path / "MatchForgeBackup", credential_environment(config))
        restic.run("init", "--repository-version", "2")
        config = BackupConfig(tmp_path, "fixture", restic.identity(), str(password), "")

        def volume(_: BackupConfig) -> dict[str, int]:
            return {
                "free_bytes": 800_000_000_000,
                "capacity_bytes": 1_000_000_000_000,
                "device_id": tmp_path.stat().st_dev,
            }

        monkeypatch.setattr(backup_destination, "inspect_volume", volume)
        monkeypatch.setattr(manual_backup, "inspect_volume", volume)
        monkeypatch.delenv("MATCHFORGE_SYNC_RUN_ID", raising=False)
        backed_up = manual_backup.backup(config, plan, admin=True, governed=True)
        assert backed_up["scope"] == GOVERNED_SCOPE
        assert backed_up["status"] == "VERIFIED_GOVERNED_SCOPE"
        assert backed_up["full_recovery"] is False
        assert backed_up["governed_sha256"] == plan["governed_sha256"]
        drill = backed_up["full_operating_restore_drill"]
        assert drill["status"] == "PASS_GOVERNED_SCOPE" and drill["full_recovery"] is False
        assert drill["global_role_restore"]["status"] == "PASS"
        for tag in ("matchforge-verified", "matchforge-recoverable-verified"):
            assert json.loads(restic.run("snapshots", "--json", "--tag", tag)) == []
        points = json.loads(
            restic.run("snapshots", "--json", "--tag", "matchforge-governed-verified")
        )
        assert points[0]["id"] == backed_up["snapshot_id"]

        # A new gap, or any change to the approvals, invalidates the reviewed scope.
        with psycopg.connect(url) as connection:
            connection.execute(
                "INSERT INTO football.source_snapshots(provider_id,source_identity,"
                "source_revision,acquired_at,manifest_path,manifest_sha256,status) "
                "VALUES (%s,'new.json','v1',now(),'new.json',%s,'validated')",
                (real, digest),
            )
        with pytest.raises(ValueError, match="changed"):
            capture_recovery(tmp_path / "changed-capture", restored / "data", plan, governed=True)
        with pytest.raises(ValueError, match="changed"):
            capture_recovery(
                tmp_path / "stale-capture",
                restored / "data",
                {**plan, "governed_sha256": "0" * 64},
                governed=True,
            )
    finally:
        subprocess.run(compose_command("dropdb", "--force", database), cwd=ROOT, check=True)
