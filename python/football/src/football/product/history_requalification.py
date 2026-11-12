"""Replay retained API-Football fixture responses through reconciliation and qualification.

Results that the dated fixture request stored before the P02 fix never reached
history qualification. This command re-reads the retained, checksum-verified
response bytes and passes them to the same steps the live sync uses, so every
change cites the snapshot that shows it.

Two phases run in order:

1. **Reconcile overdue fixtures.** A fixture still unresolved hours after
   kickoff is updated from the latest retained response for it, but only when
   that response was acquired after kickoff, reports a terminal provider status
   and is newer than the stored row. Anything else is classified, never guessed.
2. **Qualify finished results.** Every fixture-shaped response (dated requests,
   league-season history, and ad hoc recovery or single-fixture requests) is
   replayed oldest first through ``_qualify_finished_history``.

Decisions are append-only and stamped with the replay time, so no earlier
knowledge cutoff gains facts. Each snapshot (and each reconciled fixture) is its
own transaction; a stopped run resumes after the last committed snapshot.
``--dry-run`` runs everything in one transaction and rolls it back, so its
counts equal those of a real run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from psycopg import Connection

from football.product.integrity_audit import UNRESOLVED, incremental_findings
from football.product.sync import ProductSync
from football.product.sync_support import PROVIDER_CODE

REQUALIFICATION_VERSION = "p02-history-requalification-v2"
TERMINAL_PROVIDER_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"})
OVERDUE_AFTER = timedelta(hours=4)


def _snapshots(
    connection: Connection[Any], after: tuple[str, str] | None, since: datetime | None = None
) -> list[tuple[Any, ...]]:
    return connection.execute(
        """SELECT s.id, s.acquired_at, s.manifest_path, s.manifest_sha256, s.source_identity
           FROM football.source_snapshots s
           JOIN football.providers p ON p.id = s.provider_id
           WHERE p.code = %s AND s.status = 'validated'
             AND (%s::timestamptz IS NULL OR s.acquired_at >= %s)
             AND (%s::timestamptz IS NULL OR (s.acquired_at, s.id) > (%s::timestamptz, %s::uuid))
           ORDER BY s.acquired_at, s.id""",
        (
            PROVIDER_CODE,
            since,
            since,
            after[0] if after else None,
            after[0] if after else None,
            after[1] if after else None,
        ),
    ).fetchall()


def _fixture_shaped(row: Any) -> bool:
    if not isinstance(row, Mapping):
        return False
    fixture = row.get("fixture")
    return (
        isinstance(fixture, Mapping)
        and isinstance(fixture.get("id"), int)
        and not isinstance(fixture.get("id"), bool)
        and isinstance(fixture.get("status"), Mapping)
        and isinstance(row.get("teams"), Mapping)
        and isinstance(row.get("league"), Mapping)
        and isinstance(row.get("goals"), Mapping)
    )


def _rows(data_root: Path, path: str, sha256: str) -> tuple[Any, ...]:
    """Checksum-verified fixture rows of one retained response; () if not fixture-shaped."""
    raw = (data_root / path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(f"retained response checksum mismatch: {path}")
    payload = json.loads(raw)
    rows = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if _fixture_shaped(row))


def _short(row: Mapping[str, Any]) -> str:
    return str(row["fixture"]["status"].get("short"))


def _finished(rows: Sequence[Any]) -> int:
    return sum(1 for row in rows if _short(row) == "FT")


def _kind(source_identity: str) -> str:
    return source_identity.split("-", 1)[0]


def _latest_retained(
    data_root: Path,
    snapshots: Sequence[tuple[Any, ...]],
    wanted: set[str],
) -> tuple[dict[str, tuple[Any, ...]], list[str]]:
    """Latest retained row per wanted provider fixture ID across the given snapshots."""
    latest: dict[str, tuple[Any, ...]] = {}
    missing: list[str] = []
    for snapshot_id, acquired_at, path, sha256, identity in snapshots:
        try:
            rows = _rows(data_root, path, sha256)
        except FileNotFoundError:
            missing.append(path)
            continue
        for row in rows:
            key = str(row["fixture"]["id"])
            if key in wanted:
                latest[key] = (snapshot_id, acquired_at, identity, row)
    return latest, missing


def _overdue(connection: Connection[Any]) -> list[tuple[Any, ...]]:
    return connection.execute(
        """SELECT m.provider_match_id, f.fixture_id, f.kickoff_at, f.updated_at, f.status
           FROM football.product_fixtures f
           JOIN football.match_provider_mappings m ON m.match_id = f.fixture_id
             AND m.valid_to IS NULL
           JOIN football.providers p ON p.id = m.provider_id AND p.code = %s
           WHERE f.status = ANY(%s) AND f.kickoff_at < statement_timestamp() - %s
           ORDER BY f.kickoff_at, f.fixture_id""",
        (PROVIDER_CODE, list(UNRESOLVED), OVERDUE_AFTER),
    ).fetchall()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


def reconcile_overdue(
    connection: Connection[Any],
    sync: ProductSync,
    data_root: Path,
    snapshots: Sequence[tuple[Any, ...]],
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Apply retained terminal provider states to overdue fixtures; classify the rest.

    With ``commit`` false the caller owns an enclosing transaction (the dry run)
    and each fixture becomes a savepoint inside it.
    """
    overdue = _overdue(connection)
    if commit:
        connection.commit()
    latest, missing = _latest_retained(data_root, snapshots, {row[0] for row in overdue})
    outcome: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    errors: list[str] = []
    applied: list[str] = []
    for provider_id, fixture_id, kickoff_at, updated_at, _status in overdue:
        found = latest.get(provider_id)
        if found is None:
            outcome["NOT_IN_RETAINED_RESPONSES"] += 1
            continue
        snapshot_id, acquired_at, identity, row = found
        short = _short(row)
        provider_kickoff = _parse(str(row["fixture"]["date"]))
        if acquired_at <= max(kickoff_at, provider_kickoff):
            outcome["NO_RETAINED_OBSERVATION_AFTER_KICKOFF"] += 1
            continue
        if short not in TERMINAL_PROVIDER_STATUSES:
            outcome["PROVIDER_NOT_TERMINAL_AT_LAST_RETAINED_OBSERVATION"] += 1
            continue
        if updated_at > acquired_at:
            outcome["STORED_ROW_NEWER_THAN_RETAINED_EVIDENCE"] += 1
            continue
        try:
            with connection.transaction():
                sync._store_fixtures((row,), cast(UUID, snapshot_id), acquired_at)
        except psycopg.Error as error:
            outcome["APPLY_ERROR"] += 1
            errors.append(f"{fixture_id}: {str(error).splitlines()[0][:160]}")
            continue
        outcome["APPLIED_FROM_RETAINED_TERMINAL_RESPONSE"] += 1
        by_status[short] += 1
        by_kind[_kind(str(identity))] += 1
        applied.append(str(fixture_id))
    return {
        "overdue_api_football": len(overdue),
        "outcome": dict(sorted(outcome.items())),
        "applied_by_provider_status": dict(sorted(by_status.items())),
        "applied_by_snapshot_kind": dict(sorted(by_kind.items())),
        "applied_fixture_ids_sha256": hashlib.sha256(
            "\n".join(sorted(applied)).encode()
        ).hexdigest(),
        "missing_files": missing,
        "errors": errors[:50],
    }


def _replay(
    connection: Connection[Any],
    sync: ProductSync,
    data_root: Path,
    state: dict[str, Any],
    save: Any,
    dry_run: bool,
    started: float,
    time_limit: float,
) -> None:
    if state["reconciliation"] is None:
        snapshots = _snapshots(connection, None)
        if not dry_run:
            connection.commit()
        state["reconciliation"] = reconcile_overdue(
            connection, sync, data_root, snapshots, commit=not dry_run
        )
        save()
    after = (state["after"][0], state["after"][1]) if state["after"] else None
    kinds: Counter[str] = Counter(state["qualified_by_snapshot_kind"])
    for snapshot_id, acquired_at, path, sha256, identity in _snapshots(connection, after):
        if not dry_run:
            connection.commit()
        if time.monotonic() - started > time_limit:
            break
        try:
            rows = _rows(data_root, path, sha256)
        except FileNotFoundError:
            state["missing_files"].append(path)
            rows = ()
        if rows:
            with connection.transaction():
                qualified = sync._qualify_finished_history(rows, snapshot_id, acquired_at)
            state["finished_rows"] += _finished(rows)
            state["qualified"] += qualified
            kinds[_kind(str(identity))] += qualified
            state["identity_conflicts"] += sync.history_identity_conflicts
            sync.history_identity_conflicts = 0
        else:
            state["non_fixture_snapshots"] += 1
        state["snapshots"] += 1
        state["qualified_by_snapshot_kind"] = dict(sorted(kinds.items()))
        state["after"] = [acquired_at.isoformat(), str(snapshot_id)]
        save()
    else:
        state["complete"] = True


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
            "reconciliation": None,
            "after": None,
            "snapshots": 0,
            "non_fixture_snapshots": 0,
            "finished_rows": 0,
            "qualified": 0,
            "qualified_by_snapshot_kind": {},
            "identity_conflicts": 0,
            "missing_files": [],
        }
    )
    if state["version"] != REQUALIFICATION_VERSION:
        raise ValueError("checkpoint was written by another re-qualification version")

    def save() -> None:
        if not dry_run:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps(state, sort_keys=True, indent=1))

    with psycopg.connect(database_url) as connection:
        sync = ProductSync(connection, cast(Any, None), data_root, data_root / "unused-artifact")
        state["complete"] = False
        # A dry run is one transaction that is rolled back at the end, so later
        # snapshots see what earlier ones would have written and the counts
        # equal those of a real run. A real run commits per fixture and snapshot.
        with connection.transaction(force_rollback=True) if dry_run else nullcontext():
            _replay(connection, sync, data_root, state, save, dry_run, started, time_limit)
    return state


REPAIR_WINDOW = timedelta(hours=72)
REPAIR_SNAPSHOT_LIMIT = 32


def maintain_history(connection: Connection[Any], data_root: Path) -> dict[str, Any]:
    """Detect recent unqualified or unreconciled results and repair them from retained responses.

    Bounded to the newest fixture-shaped responses inside REPAIR_WINDOW (of any
    request kind) and run only when detection finds a gap. Score mismatches and
    overdue results without retained terminal evidence are reported, not
    repaired, because they need a newer source observation.
    """
    with connection.transaction():
        now = connection.execute("SELECT statement_timestamp()").fetchone()
        assert now is not None
        since = now[0] - REPAIR_WINDOW
        before = incremental_findings(connection, since)
    result: dict[str, Any] = {"window_start": since.isoformat(), "before": before, "repaired": 0}
    if not (before["finished_without_history"] or before["overdue_api_football"]):
        return result
    sync = ProductSync(connection, cast(Any, None), data_root, data_root / "unused-artifact")
    recent = connection.execute(
        """SELECT * FROM (
             SELECT s.id, s.acquired_at, s.manifest_path, s.manifest_sha256, s.source_identity
             FROM football.source_snapshots s
             JOIN football.providers p ON p.id = s.provider_id
             WHERE p.code = %s AND s.status = 'validated' AND s.acquired_at >= %s
             ORDER BY s.acquired_at DESC, s.id DESC LIMIT %s) newest
           ORDER BY acquired_at, id""",
        (PROVIDER_CODE, since, REPAIR_SNAPSHOT_LIMIT),
    ).fetchall()
    connection.commit()
    readable = []
    for snapshot in recent:
        try:
            rows = _rows(data_root, snapshot[2], snapshot[3])
        except (OSError, ValueError) as error:
            result.setdefault("errors", []).append(str(error)[:200])
            continue
        if rows:
            readable.append((snapshot, rows))
    if before["overdue_api_football"]:
        reconciled = reconcile_overdue(connection, sync, data_root, [item[0] for item in readable])
        result["reconciled"] = reconciled["outcome"].get(
            "APPLIED_FROM_RETAINED_TERMINAL_RESPONSE", 0
        )
    for (snapshot_id, acquired_at, _path, _sha256, _identity), rows in readable:
        if rows:
            with connection.transaction():
                result["repaired"] += sync._qualify_finished_history(rows, snapshot_id, acquired_at)
    with connection.transaction():
        result["after"] = incremental_findings(connection, since)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="reconcile and re-qualify retained API-Football fixture results"
    )
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
