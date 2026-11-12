"""Only explicit manual execution can create an encrypted recovery point."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
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
    verify_cluster_restore,
    verify_restore,
)
from scripts.capture_architecture_v2_baseline import ROOT, write_json
from scripts.recovery_files import RecoveryReferenceError, regular_file
from scripts.recovery_scope import GOVERNED_SCOPE, load_plan, validate_governed

FULL_RECOVERY = "FULL_RECOVERY"
RECOVERABLE_ONLY = "RECOVERABLE_ONLY"


SCOPED = (RECOVERABLE_ONLY, GOVERNED_SCOPE)


def governed_plan(path: Path) -> dict[str, Any]:
    plan = load_plan(path)
    validate_governed(plan)
    return plan


def admin_policy() -> tuple[str, dict[str, Any] | None]:
    scope = os.environ.get("MATCHFORGE_BACKUP_SCOPE", FULL_RECOVERY)
    if scope not in (FULL_RECOVERY, *SCOPED):
        raise BackupError("UNCONFIGURED", "Configure a valid backup recovery policy.")
    inventory_path = os.environ.get("MATCHFORGE_BACKUP_RECOVERABLE_INVENTORY")
    try:
        plan = load_plan(Path(inventory_path)) if inventory_path else None
        if scope == GOVERNED_SCOPE and plan is not None:
            validate_governed(plan)
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise BackupError("UNCONFIGURED", "The protected recovery inventory is invalid.") from error
    if scope in SCOPED and plan is None:
        raise BackupError("UNCONFIGURED", "Configure the owner-reviewed recovery inventory first.")
    return scope, plan


def policy_details(scope: str, plan: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "scope": scope,
        "known_unavailable_dependencies": len(plan["unavailable"]) if plan else None,
        "unavailable_sha256": plan["unavailable_sha256"] if plan else None,
        "excluded_dependencies": len(plan.get("excluded", [])) if plan else None,
        "governed_sha256": plan["governed_sha256"] if plan and scope == GOVERNED_SCOPE else None,
    }


def prior_verified_receipt() -> dict[str, Any] | None:
    configured = os.environ.get("MATCHFORGE_BACKUP_PRIOR_RECEIPT")
    if not configured:
        return None
    try:
        path = Path(configured).absolute().relative_to(ROOT).as_posix()
        receipt = json.loads(regular_file(ROOT, path).read_text())
        if (
            receipt["repository_id"] != os.environ.get("MATCHFORGE_BACKUP_REPOSITORY_ID")
            or receipt["volume_uuid"] != os.environ.get("MATCHFORGE_BACKUP_VOLUME_UUID")
            or not re.fullmatch(r"[0-9a-f]{64}", receipt["repository_id"])
        ):
            raise ValueError("receipt does not belong to the enrolled repository")
        summary = receipt["verification"]
        restore = summary["full_operating_restore_drill"]
        return {
            **{
                key: summary[key]
                for key in (
                    "scope",
                    "snapshot_id",
                    "verified_at",
                    "captured_at",
                    "status",
                    "verified",
                    "full_recovery",
                    "unavailable_dependencies",
                    "unavailable_sha256",
                    "logical_bytes",
                    "data_added_packed_bytes",
                    "repository_file_bytes",
                )
            },
            "volume_free_space_change_bytes": summary.get("volume_free_space_change_bytes"),
            "full_operating_restore_drill": {
                **{
                    key: restore[key]
                    for key in (
                        "status",
                        "database_isolated",
                        "full_recovery",
                        "unavailable_dependencies",
                    )
                },
                "global_role_restore": restore.get("global_role_restore")
                if summary["full_recovery"]
                else None,
            },
        }
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise BackupError(
            "UNCONFIGURED", "The prior verified recovery receipt is invalid."
        ) from error


def preview(
    config: BackupConfig,
    recovery_plan: dict[str, Any] | None = None,
    *,
    use_reviewed_estimate: bool = False,
    governed: bool = False,
) -> dict[str, Any]:
    _, volume = destination(config)
    data_root = Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data")))
    estimate = recovery_estimate(
        data_root, recovery_plan, use_reviewed_estimate=use_reviewed_estimate, governed=governed
    )
    estimated = estimate["estimated_staging_bytes"]
    low_external = require_capacity(volume["free_bytes"], estimated, volume["capacity_bytes"])
    internal = shutil.disk_usage(ROOT)
    low_internal = require_capacity(internal.free, 4 * estimated, internal.total)
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
        "impact": (
            "One dump worker and two Restic CPUs/readers. This action includes encrypted "
            "read-back and an isolated database and file restore. The worker verifies every "
            "dependency against the capture snapshot. Keep the drive connected until completion."
        ),
    }


def progress(phase: str) -> None:
    identity = os.environ.get("MATCHFORGE_SYNC_RUN_ID")
    if identity:
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            # Progress uses a control transaction separate from data publication.
            connection.execute(
                "SELECT set_config('matchforge.sync_run_id','',true),"
                "set_config('matchforge.sync_worker_id','',true),"
                "set_config('matchforge.history_claim_token','',true)"
            )
            updated = connection.execute(
                "UPDATE football.product_sync_runs "
                "SET summary=jsonb_build_object('current_phase',%s::text) "
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
    *,
    admin: bool = False,
    governed: bool = False,
) -> dict[str, Any]:
    if governed and recovery_plan is None:
        raise BackupError("UNCONFIGURED", "Configure the owner-reviewed recovery inventory first.")
    if restore_destination is None and not admin:
        raise BackupError(
            "INCOMPLETE",
            "Command-line execution requires an isolated restore destination.",
        )
    if os.environ.get("MATCHFORGE_SYNC_RUN_ID") and not admin:
        raise BackupError("INCOMPLETE", "Admin backup jobs require a confirmed policy.")
    plan = preview(config, recovery_plan, governed=governed)
    progress("Capturing consistent database snapshot and original files")
    staging = ROOT / ".local/backup-staging"
    staging.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(prefix="manual-", dir=staging) as temporary:
        root = Path(temporary)
        payload = root / "payload"
        data_root = Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data")))
        captured = capture_recovery(payload, data_root, recovery_plan, governed=governed)
        expected = "CAPTURED_GOVERNED" if governed else "CAPTURED_RECOVERABLE"
        if captured["status"] != ("CAPTURED" if recovery_plan is None else expected):
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
        isolated = root / "isolated-restore" if admin else restore_destination
        assert isolated is not None
        restoration = restore_readback(root / "read-back", isolated, captured, admin=admin)
        progress("Verification complete; recording recovery point")
        inspect_volume(config)
        verified_tag = (
            "matchforge-governed-verified"
            if governed
            else "matchforge-recoverable-verified"
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
        scope = (
            GOVERNED_SCOPE
            if governed
            else RECOVERABLE_ONLY
            if recovery_plan is not None
            else FULL_RECOVERY
        )
        return {
            "backup": True,
            "scope": scope,
            "repository_id": config.repository_id,
            "volume_uuid": config.volume_uuid,
            "unavailable_sha256": recovery_plan["unavailable_sha256"] if recovery_plan else None,
            "governed_sha256": recovery_plan["governed_sha256"]
            if governed and recovery_plan
            else None,
            "excluded_dependencies": len(recovery_plan.get("excluded", [])) if recovery_plan else 0,
            "status": {
                FULL_RECOVERY: "VERIFIED",
                RECOVERABLE_ONLY: "VERIFIED_RECOVERABLE",
                GOVERNED_SCOPE: "VERIFIED_GOVERNED_SCOPE",
            }[scope],
            "verified": True,
            "full_recovery": recovery_plan is None,
            "unavailable_dependencies": len(recovery_plan["unavailable"]) if recovery_plan else 0,
            "verified_at": datetime.now(UTC).isoformat(),
            "captured_at": captured["captured_at"],
            "snapshot_id": snapshots[0]["id"],
            "repository_file_bytes": repository_bytes,
            "volume_free_space_change_bytes": (
                plan["drive"]["free_bytes"] - inspect_volume(config)["free_bytes"]
            ),
            "logical_bytes": required,
            "data_added_bytes": summary["data_added"],
            "data_added_packed_bytes": summary["data_added_packed"],
            "capture_seconds": captured["duration_seconds"],
            "referenced_bytes": plan["referenced_bytes"],
            "full_operating_restore_drill": restoration,
        }


def restore_readback(
    root: Path, isolated: Path, captured: dict[str, Any], *, admin: bool
) -> dict[str, Any]:
    recoverable = captured["status"] == "CAPTURED_RECOVERABLE"
    governed = captured["status"] == "CAPTURED_GOVERNED"
    progress("Restoring the database and verifying restored dependencies")
    try:
        restoration = verify_restore(
            root, isolated, allow_recoverable=recoverable, allow_governed=governed
        )
    except (OSError, ValueError, psycopg.Error, subprocess.SubprocessError) as error:
        raise BackupError(
            "VERIFICATION_FAILED",
            "Encrypted read-back or isolated restoration failed. "
            "Previous recovery points are retained.",
        ) from error
    if not recoverable:
        progress("Verifying globals and ownership in a network-isolated cluster")
        restoration["global_role_restore"] = verify_cluster_restore(root, captured)
        # A governed scope is restored as strictly as full recovery, but it still has
        # approved exclusions, so it never reports full recovery.
        restoration["full_recovery"] = not governed
        if not admin:
            write_json(isolated / "verification.json", restoration)
    if admin:
        # The encrypted capture retains the individual artifact outcomes.
        restoration.pop("registered_artifact_readers", None)
    return restoration


def admin_action(args: argparse.Namespace, details: dict[str, Any]) -> dict[str, Any]:
    scope, inventory = admin_policy()
    details.update(policy_details(scope, inventory))
    if args.action != "run":
        details["prior_verified"] = prior_verified_receipt()
    config = BackupConfig.load()
    if args.action == "status":
        return backup_status(config)
    plan = inventory if scope in SCOPED else None
    governed = scope == GOVERNED_SCOPE
    if scope == FULL_RECOVERY and inventory and inventory["unavailable"]:
        raise BackupError(
            "MISSING_FILES", "Full recovery is blocked by the declared unavailable dependencies."
        )
    if args.action == "preview":
        return preview(config, plan, use_reviewed_estimate=True, governed=governed)
    if not os.environ.get("MATCHFORGE_SYNC_RUN_ID") or (
        args.scope != scope
        or args.unavailable_sha256 != (plan["unavailable_sha256"] if plan else None)
        or args.governed_sha256 != (plan["governed_sha256"] if governed and plan else None)
    ):
        raise BackupError("INCOMPLETE", "Recovery scope changed. Run preflight and confirm again.")
    os.nice(10)
    return backup(config, plan, admin=True, governed=governed)


def backup_status(config: BackupConfig) -> dict[str, Any]:
    restic, volume = destination(config)
    return {
        "state": "READY",
        "message": "Enrolled encrypted repository is available.",
        "drive": volume,
        "repository_unlocked": not restic.run("list", "locks").strip(),
    }


def cli_action(args: argparse.Namespace) -> dict[str, Any]:
    if os.environ.get("MATCHFORGE_SYNC_RUN_ID"):
        raise BackupError("INCOMPLETE", "Admin backup jobs require a confirmed policy.")
    if args.governed and not args.recoverable_inventory:
        raise BackupError("UNCONFIGURED", "A governed scope needs --recoverable-inventory.")
    load = governed_plan if args.governed else load_plan
    try:
        plan = load(args.recoverable_inventory) if args.recoverable_inventory else None
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise BackupError("UNCONFIGURED", "The protected recovery inventory is invalid.") from error
    config = BackupConfig.load()
    if args.action == "status":
        return backup_status(config)
    if args.action == "preview":
        return preview(config, plan, governed=args.governed)
    os.nice(10)
    return backup(config, plan, args.restore_destination, governed=args.governed)


def interrupt(_signum: int, _frame: Any) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise BackupError(
        "INTERRUPTED", "Backup was interrupted. Previous recovery points are retained."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "preview", "run"))
    parser.add_argument("--admin", action="store_true")
    parser.add_argument("--scope", choices=(FULL_RECOVERY, *SCOPED))
    parser.add_argument("--unavailable-sha256")
    parser.add_argument("--governed-sha256")
    parser.add_argument(
        "--governed",
        action="store_true",
        help="command line: capture the reviewed governed scope (VERIFIED_GOVERNED_SCOPE)",
    )
    parser.add_argument("--recoverable-inventory", type=Path)
    parser.add_argument("--restore-destination", type=Path)
    args = parser.parse_args()
    details: dict[str, Any] = {}
    if args.admin and args.action == "run":
        signal.signal(signal.SIGTERM, interrupt)
    try:
        result = admin_action(args, details) if args.admin else cli_action(args)
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
    except (OSError, ValueError, psycopg.Error, subprocess.SubprocessError, RuntimeError) as error:
        # The public message stays generic; the protected run log keeps the cause.
        print(
            json.dumps(
                {
                    "status": "RECOVERY_DIAGNOSTIC",
                    "private_failure_type": type(error).__name__,
                    "private_failure_detail": str(error)[:2000],
                }
            ),
            file=sys.stderr,
        )
        code = "MISSING_FILES" if isinstance(error, FileNotFoundError) else "SNAPSHOT_FAILED"
        result = {
            "backup": True,
            "status": "FAILED",
            "state": code,
            "message": "Backup preflight or verification failed. Check original files, "
            "local storage and database access; no previous verified recovery point was changed.",
        }
    print(json.dumps({**details, **result}))
    if args.action == "run" and result.get("verified") is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
