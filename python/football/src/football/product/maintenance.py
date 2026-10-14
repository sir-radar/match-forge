"""Fail-closed local maintenance preflight using socket ownership and durable state."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def quiescence_result(host: dict[str, Any], database: dict[str, Any]) -> dict[str, Any]:
    blocked = bool(
        host.get("errors")
        or host.get("api_listeners")
        or host.get("writer_processes")
        or database.get("sessions")
        or any(database.get("active_jobs", {}).values())
    )
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "status": "BLOCKED_ACTIVE_WRITER_UNCONTROLLED" if blocked else "QUIESCENT",
        "R3_DATABASE_WRITERS_QUIESCENT": not blocked,
        "host": host,
        "database": database,
    }


def _lsof_records(output: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for line in output.splitlines():
        if line.startswith("p"):
            current = {"pid": int(line[1:]), "paths": []}
            records.append(current)
        elif line.startswith("c"):
            current["command"] = line[1:]
        elif line.startswith("n"):
            current["paths"].append(line[1:])
    return records


def _command(arguments: list[str], *, empty_ok: bool = False) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=15, check=False)
    if result.returncode and not (empty_ok and result.returncode == 1 and not result.stderr):
        raise RuntimeError(f"{arguments[0]} signal unavailable (exit {result.returncode})")
    return result.stdout


def _editor_process(pid: int) -> bool:
    arguments = shlex.split(_command(["ps", "-p", str(pid), "-o", "args="]))
    if len(arguments) != 2:
        return False
    script = Path(arguments[1])
    return (
        script.parts[-3:] == ("bundled", "tool", "lsp_server.py")
        and script.parent.parent.parent.name.startswith("ms-python.isort-")
        and script.parent.parent.parent.parent == Path.home() / ".vscode" / "extensions"
    )


def host_signals(root: Path, port: int) -> dict[str, Any]:
    """Identify repo-owned executables without recording arguments or secret environments."""
    result: dict[str, Any] = {"errors": [], "api_listeners": [], "writer_processes": []}
    try:
        result["api_listeners"] = _lsof_records(
            _command(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpcn"], empty_ok=True)
        )
        processes = _lsof_records(_command(["lsof", "-nP", "-d", "cwd", "-Fpcn"]))
        own = {os.getpid(), os.getppid()}
        for process in processes:
            owned = any(Path(path).is_relative_to(root.resolve()) for path in process["paths"])
            executable = process.get("command", "")
            if (
                owned
                and process["pid"] not in own
                and executable
                in {
                    "api",
                    "football-api",
                    "python",
                    "python3",
                    "python3.13",
                    "uv",
                    "go",
                }
            ):
                if _editor_process(process["pid"]):
                    result.setdefault("verified_editor_processes", []).append(process)
                else:
                    result["writer_processes"].append(process)
        services = _command(["launchctl", "list"])
        pids = {p["pid"] for p in result["api_listeners"] + result["writer_processes"]}
        result["owning_services"] = [
            line for line in services.splitlines() if line.split()[0] in {str(p) for p in pids}
        ]
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["errors"].append(str(error))
    return result


def database_signals(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    with connection.cursor(row_factory=dict_row) as cursor:
        clients = cursor.execute(
            """SELECT pid, usename, application_name, backend_type, client_addr, state,
                      backend_start,
                      xact_start, query_start, wait_event_type, wait_event, query='' empty_query
               FROM pg_stat_activity
               WHERE datname=current_database() AND pid<>pg_backend_pid() ORDER BY pid"""
        ).fetchall()
        probes = [client for client in clients if verified_health_probe(client)]
        maintenance = [
            client for client in clients if client["backend_type"] == "autovacuum worker"
        ]
        sessions = [
            client
            for client in clients
            if not verified_health_probe(client) and client["backend_type"] != "autovacuum worker"
        ]
        active = {}
        for table, status in (
            ("product_sync_runs", "status"),
            ("product_history_sync_queue", "job_status"),
            ("product_provider_history_scopes", "status"),
            ("provider_sync_runs", "status"),
            ("acquisition_jobs", "status"),
        ):
            active[table] = cursor.execute(
                f"SELECT * FROM football.{table} WHERE upper({status}::text) "
                "IN ('RUNNING', 'QUEUED', 'CLAIMED', 'ACQUIRING')"
            ).fetchall()
    return {
        "sessions": sessions,
        "verified_health_probes": probes,
        "postgres_maintenance": maintenance,
        "active_jobs": active,
    }


def verified_health_probe(client: dict[str, Any]) -> bool:
    """The compose-owned local pg_isready probe connects without executing SQL."""
    return (
        client.get("application_name") == "pg_isready"
        and client.get("client_addr") is None
        and client.get("xact_start") is None
        and client.get("empty_query") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        options="-c default_transaction_read_only=on -c statement_timeout=30000",
        application_name="matchforge-r3-preflight",
    ) as connection:
        report = quiescence_result(host_signals(args.root, args.port), database_signals(connection))
    report["scheduler_configuration"] = {
        key: os.environ.get(key)
        for key in (
            "MATCHFORGE_OPERATIONAL_SYNC_INTERVAL",
            "MATCHFORGE_HISTORY_SYNC_ENABLED",
            "MATCHFORGE_HISTORY_SYNC_INTERVAL",
            "MATCHFORGE_FOTMOB_ENABLED",
            "MATCHFORGE_PITCHAPI_ENABLED",
        )
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "R3_DATABASE_WRITERS_QUIESCENT")}))
    return 2 if not report["R3_DATABASE_WRITERS_QUIESCENT"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
