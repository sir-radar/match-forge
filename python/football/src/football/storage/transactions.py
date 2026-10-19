"""Transaction ownership checks for operations that commit bounded database steps."""

from typing import Any

from psycopg import Connection
from psycopg.pq import TransactionStatus


def require_idle_connection(connection: Connection[Any], operation: str) -> None:
    """Reject borrowed work without committing or rolling it back."""
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError(f"{operation} requires an idle connection")
