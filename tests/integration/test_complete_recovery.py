from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

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
        assert (restored / "data/source.json").read_bytes() == payload
        restore_fresh_cluster(archive, database, digest)
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
