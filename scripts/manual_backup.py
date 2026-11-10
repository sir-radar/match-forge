"""Only explicit manual execution can create an encrypted recovery point."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg

from scripts.backup_destination import (
    BackupConfig,
    BackupError,
    destination,
    inspect_volume,
    require_capacity,
)
from scripts.backup_recovery import (
    capture_recovery,
    recovery_estimate,
    verify_capture,
    verify_restore,
)
from scripts.capture_architecture_v2_baseline import ROOT, write_json
from scripts.recovery_files import RecoveryReferenceError
from scripts.recovery_scope import load_plan


def preview(config: BackupConfig, recovery_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    _, volume = destination(config)
    data_root = Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data")))
    estimate = recovery_estimate(data_root, recovery_plan)
    estimated = estimate["estimated_staging_bytes"]
    low_external = require_capacity(volume["free_bytes"], estimated, volume["capacity_bytes"])
    internal = shutil.disk_usage(ROOT)
    copies = 4 if recovery_plan is not None else 2
    low_internal = require_capacity(internal.free, copies * estimated, internal.total)
    return {
        "state": "READY",
        "message": (
            "Preflight passed with less than the recommended 20% free-space headroom. "
            "Review capacity before confirming."
            if low_external or low_internal
            else "Preflight passed. Snapshot checksums will be verified during capture."
        ),
        "drive": volume,
        **estimate,
        "impact": "One dump worker and two Restic CPUs/readers. Capture plus read-back "
        "verification needs temporary disk space. Full database restore drills are separate "
        "manual actions. Duration is unmeasured for this operating scope.",
    }


def progress(phase: str) -> None:
    identity = os.environ.get("MATCHFORGE_SYNC_RUN_ID")
    if identity:
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            updated = connection.execute(
                "UPDATE football.product_sync_runs "
                "SET summary=jsonb_build_object('current_phase',%s) "
                "WHERE run_id=%s::uuid AND worker_id=%s AND status='RUNNING' "
                "AND heartbeat_at>clock_timestamp()-interval '2 minutes' RETURNING run_id",
                (phase, identity, identity),
            ).fetchone()
            if updated is None:
                raise BackupError(
                    "INTERRUPTED",
                    "Backup ownership was lost. Retry manually after checking run status.",
                )


def backup(
    config: BackupConfig,
    recovery_plan: dict[str, Any] | None = None,
    restore_destination: Path | None = None,
) -> dict[str, Any]:
    if recovery_plan is not None and (
        restore_destination is None or os.environ.get("MATCHFORGE_SYNC_RUN_ID")
    ):
        raise BackupError(
            "RECOVERABLE_SCOPE",
            "Recoverable-only execution requires an explicit isolated restore destination "
            "and cannot complete a full-scope Admin job.",
        )
    plan = preview(config, recovery_plan)
    progress("Capturing consistent database snapshot and original files")
    staging = ROOT / ".local/backup-staging"
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="manual-", dir=staging) as temporary:
        root = Path(temporary)
        payload = root / "payload"
        data_root = Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data")))
        captured = capture_recovery(payload, data_root, recovery_plan)
        if captured["status"] not in ("CAPTURED", "CAPTURED_RECOVERABLE"):
            print(
                json.dumps(
                    {
                        "status": "RECOVERY_DIAGNOSTIC",
                        "failed_dependencies": captured["files"]["failures"][:20],
                        "total_failed_dependencies": len(captured["files"]["failures"]),
                    }
                ),
                file=sys.stderr,
            )
            raise BackupError(
                "MISSING_FILES",
                "Recovery is incomplete. Resolve missing original files before retrying.",
            )
        captured["destination"] = {
            "volume_uuid": config.volume_uuid,
            "repository_id": config.repository_id,
            "key_recovery": "Owner attested separate password; password is not in this backup.",
        }
        write_json(payload / "recovery.json", captured)
        restic, volume = destination(config)
        required = sum(path.stat().st_size for path in payload.rglob("*") if path.is_file())
        require_capacity(volume["free_bytes"], required, volume["capacity_bytes"])
        progress("Writing encrypted incremental snapshot")
        marker = "matchforge-run:" + uuid4().hex
        events = restic.run(
            "backup",
            "--json",
            "--compression",
            "auto",
            "--read-concurrency",
            "2",
            "--tag",
            "matchforge",
            "--tag",
            marker,
            str(payload),
        )
        summaries = [
            event
            for line in events.splitlines()
            if (event := json.loads(line)).get("message_type") == "summary"
        ]
        if len(summaries) != 1 or not summaries[0].get("snapshot_id"):
            raise BackupError("INCOMPLETE", "Restic did not return a complete recovery point.")
        summary = summaries[0]
        progress("Verifying repository data and restoring snapshot bytes")
        destination(config)
        restic.run("check", "--read-data")
        destination(config)
        restic.run(
            "restore",
            summary["snapshot_id"] + ":" + str(payload),
            "--target",
            str(root / "read-back"),
            "--verify",
        )
        try:
            verify_capture(root / "read-back", allow_recoverable=recovery_plan is not None)
        except (OSError, ValueError) as error:
            raise BackupError(
                "VERIFICATION_FAILED",
                "Restored backup bytes or manifest failed verification. "
                "The previous recovery point is retained.",
            ) from error
        restoration = None
        if restore_destination is not None:
            restoration = verify_restore(
                root / "read-back",
                restore_destination,
                allow_recoverable=recovery_plan is not None,
            )
        progress("Verification complete; recording recovery point")
        inspect_volume(config)
        verified_tag = (
            "matchforge-recoverable-verified"
            if recovery_plan is not None
            else "matchforge-verified"
        )
        restic.run("tag", "--add", verified_tag, summary["snapshot_id"])
        snapshots = json.loads(restic.run("snapshots", "--json", "--tag", marker))
        if len(snapshots) != 1 or verified_tag not in snapshots[0].get("tags", []):
            raise BackupError(
                "VERIFICATION_FAILED", "Verified recovery point metadata could not be confirmed."
            )
        repository_bytes = sum(
            path.stat().st_size
            for path in restic.repository.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
        return {
            "backup": True,
            "status": "VERIFIED_RECOVERABLE" if recovery_plan is not None else "VERIFIED",
            "verified": True,
            "full_recovery": recovery_plan is None,
            "unavailable_dependencies": len(recovery_plan["unavailable"]) if recovery_plan else 0,
            "verified_at": datetime.now(UTC).isoformat(),
            "captured_at": captured["captured_at"],
            "snapshot_id": snapshots[0]["id"],
            "repository_file_bytes": repository_bytes,
            "logical_bytes": required,
            "data_added_bytes": summary["data_added"],
            "data_added_packed_bytes": summary["data_added_packed"],
            "capture_seconds": captured["duration_seconds"],
            "referenced_bytes": plan["referenced_bytes"],
            "full_operating_restore_drill": restoration or "NOT_RUN",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "preview", "run"))
    parser.add_argument("--recoverable-inventory", type=Path)
    parser.add_argument("--restore-destination", type=Path)
    args = parser.parse_args()
    try:
        recovery_plan = (
            load_plan(args.recoverable_inventory) if args.recoverable_inventory else None
        )
        config = BackupConfig.load()
        if args.action == "status":
            restic, volume = destination(config)
            result = {
                "state": "READY",
                "message": "Enrolled encrypted repository is available.",
                "drive": volume,
                "repository_unlocked": not restic.run("list", "locks").strip(),
            }
        elif args.action == "preview":
            result = preview(config, recovery_plan)
        else:
            os.nice(10)
            result = backup(config, recovery_plan, args.restore_destination)
    except BackupError as error:
        result = {"backup": True, "status": "FAILED", "state": error.code, "message": str(error)}
    except RecoveryReferenceError as error:
        print(
            json.dumps({"status": "RECOVERY_DIAGNOSTIC", "private_dependency_detail": str(error)}),
            file=sys.stderr,
        )
        result = {
            "backup": True,
            "status": "FAILED",
            "state": "INCOMPLETE",
            "message": "Registered file dependencies conflict or are invalid. "
            "Review the protected attempt log or local capture report before retrying; "
            "no complete backup was recorded.",
        }
    except (OSError, ValueError, psycopg.Error, subprocess.SubprocessError) as error:
        code = "MISSING_FILES" if isinstance(error, FileNotFoundError) else "SNAPSHOT_FAILED"
        result = {
            "backup": True,
            "status": "FAILED",
            "state": code,
            "message": "Backup preflight or verification failed. Check original files, "
            "local storage and database access; no previous verified recovery point was changed.",
        }
    print(json.dumps(result))
    if args.action == "run" and result.get("verified") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
