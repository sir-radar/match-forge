"""Read-only Prometheus text exposition of shared SQL work observations."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import tuple_row

from football.work.contracts import WorkType

_METRICS = {
    "work_pending": ("gauge", "Current pending work items."),
    "work_running": ("gauge", "Current running work items, including expired leases."),
    "work_retry_wait": ("gauge", "Current work items waiting for retry."),
    "work_failed": ("gauge", "Current terminal failed work items."),
    "work_blocked": ("gauge", "Current externally blocked work items."),
    "work_claim_latency": (
        "summary",
        "Seconds after the configured ready deadline before claim, since instrumentation.",
    ),
    "work_execution_duration": ("summary", "Seconds in completed attempts since instrumentation."),
    "work_retry_count": ("counter", "Replacement attempts claimed since instrumentation."),
    "work_lease_expirations": ("counter", "Expired attempts observed by committed transitions."),
    "work_fencing_rejections": ("counter", "Rejected shared lease checks, including rollbacks."),
    "work_deadlocks": ("counter", "Deadlocks detected in shared coordinator or work row locks."),
    "work_lock_wait_duration": (
        "summary",
        "Seconds acquiring shared coordinator and work row locks in committed transactions.",
    ),
}


def render_metrics(connection: Connection[Any]) -> str:
    """Join the caller's transaction; never claim work or advance a counter."""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            "SELECT name,work_type,value FROM football.work_metrics ORDER BY name,work_type"
        )
        samples = cursor.fetchall()
    lines = [
        line
        for name, (kind, description) in _METRICS.items()
        for line in (f"# HELP {name} {description}", f"# TYPE {name} {kind}")
    ]
    for name, work_type, value in samples:
        base = name.removesuffix("_sum").removesuffix("_count")
        if name not in _METRICS and (base not in _METRICS or _METRICS[base][0] != "summary"):
            raise ValueError("unsupported work metric")
        label = f'{{work_type="{WorkType(work_type).value}"}}' if work_type else ""
        lines.append(f"{name}{label} {float(value):.17g}")
    return "\n".join(lines) + "\n"
