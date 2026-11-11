"""Replay retained API-Football fixture-date responses through history qualification.

Results that the dated fixture request stored before the P02 fix never reached
history qualification. This command re-reads the retained, checksum-verified
response bytes oldest first and passes them to the same
``_qualify_finished_history`` step the live sync now uses, so each new history
row cites the snapshot that shows its score. Decisions are append-only and
stamped with the replay time, so no earlier knowledge cutoff gains facts.

Each snapshot is one transaction followed by a checkpoint; a stopped run resumes
after the last committed snapshot. ``--dry-run`` rolls every transaction back.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import psycopg
from psycopg import Connection

from football.product.integrity_audit import incremental_findings
from football.product.sync import ProductSync
from football.product.sync_support import PROVIDER_CODE

REQUALIFICATION_VERSION = "p02-history-requalification-v1"


def _snapshots(connection: Connection[Any], after: tuple[str, str] | None) -> list[tuple[Any, ...]]:
    return connection.execute(
        """SELECT s.id, s.acquired_at, s.manifest_path, s.manifest_sha256, s.source_identity
           FROM football.source_snapshots s
           JOIN football.providers p ON p.id = s.provider_id
           WHERE p.code = %s AND s.source_identity LIKE 'fixtures-%%'
             AND s.status = 'validated'
             AND (%s::timestamptz IS NULL OR (s.acquired_at, s.id) > (%s::timestamptz, %s::uuid))
           ORDER BY s.acquired_at, s.id""",
        (
            PROVIDER_CODE,
            after[0] if after else None,
            after[0] if after else None,
            after[1] if after else None,
        ),
    ).fetchall()


def _rows(data_root: Path, path: str, sha256: str) -> tuple[Any, ...]:
    raw = (data_root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(f"retained response checksum mismatch: {path}")
    payload = json.loads(raw)
    rows = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"retained response has no response list: {path}")
    return tuple(rows)


def _finished(rows: Sequence[Any]) -> int:
    return sum(
        1
        for row in rows
        if isinstance(row, dict)
        and (row.get("fixture") or {}).get("status", {}).get("short") == "FT"
    )


def run(
    database_url: str,
    data_root: Path,
    checkpoint: Path,
    *,
    dry_run: bool,
    time_limit: float,
) -> dict[str, Any]:
    started = time.monotonic()
    state: dict[str, Any] = (
        json.loads(checkpoint.read_text())
        if checkpoint.exists()
        else {
            "version": REQUALIFICATION_VERSION,
            "after": None,
            "snapshots": 0,
            "finished_rows": 0,
            "qualified": 0,
            "missing_files": [],
        }
    )
    if state["version"] != REQUALIFICATION_VERSION:
        raise ValueError("checkpoint was written by another re-qualification version")
    with psycopg.connect(database_url) as connection:
        sync = ProductSync(connection, cast(Any, None), data_root, data_root / "unused-artifact")
        state["complete"] = False
        after = (state["after"][0], state["after"][1]) if state["after"] else None
        for snapshot_id, acquired_at, path, sha256, _name in _snapshots(connection, after):
            connection.commit()
            if time.monotonic() - started > time_limit:
                break
            try:
                rows = _rows(data_root, path, sha256)
            except FileNotFoundError:
                state["missing_files"].append(path)
                rows = ()
            with connection.transaction(force_rollback=dry_run):
                qualified = sync._qualify_finished_history(rows, snapshot_id, acquired_at)
            state["snapshots"] += 1
            state["finished_rows"] += _finished(rows)
            state["qualified"] += qualified
            state["after"] = [acquired_at.isoformat(), str(snapshot_id)]
            if not dry_run:
                checkpoint.parent.mkdir(parents=True, exist_ok=True)
                checkpoint.write_text(json.dumps(state, sort_keys=True, indent=1))
        else:
            state["complete"] = True
    return state


REPAIR_WINDOW = timedelta(hours=72)
REPAIR_SNAPSHOT_LIMIT = 8


def maintain_history(connection: Connection[Any], data_root: Path) -> dict[str, Any]:
    """Detect recent unqualified results and repair them from retained responses.

    Bounded to the newest fixture-date responses inside REPAIR_WINDOW and run
    only when detection finds a gap; score mismatches and overdue results are
    reported, not repaired, because they need a newer source observation.
    """
    with connection.transaction():
        now = connection.execute("SELECT statement_timestamp()").fetchone()
        assert now is not None
        since = now[0] - REPAIR_WINDOW
        before = incremental_findings(connection, since)
    result: dict[str, Any] = {"window_start": since.isoformat(), "before": before, "repaired": 0}
    if before["finished_without_history"]:
        sync = ProductSync(connection, cast(Any, None), data_root, data_root / "unused-artifact")
        recent = connection.execute(
            """SELECT * FROM (
                 SELECT s.id, s.acquired_at, s.manifest_path, s.manifest_sha256
                 FROM football.source_snapshots s
                 JOIN football.providers p ON p.id = s.provider_id
                 WHERE p.code = %s AND s.source_identity LIKE 'fixtures-%%'
                   AND s.status = 'validated' AND s.acquired_at >= %s
                 ORDER BY s.acquired_at DESC, s.id DESC LIMIT %s) newest
               ORDER BY acquired_at, id""",
            (PROVIDER_CODE, since, REPAIR_SNAPSHOT_LIMIT),
        ).fetchall()
        connection.commit()
        for snapshot_id, acquired_at, path, sha256 in recent:
            try:
                rows = _rows(data_root, path, sha256)
            except (OSError, ValueError) as error:
                result.setdefault("errors", []).append(str(error)[:200])
                continue
            with connection.transaction():
                result["repaired"] += sync._qualify_finished_history(rows, snapshot_id, acquired_at)
        with connection.transaction():
            result["after"] = incremental_findings(connection, since)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="re-qualify retained fixture-date results")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--time-limit", type=float, default=30 * 60)
    args = parser.parse_args(argv)
    state = run(
        args.database_url,
        args.data_root,
        args.checkpoint,
        dry_run=args.dry_run,
        time_limit=args.time_limit,
    )
    print(json.dumps(state, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
