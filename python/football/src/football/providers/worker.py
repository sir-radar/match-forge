from __future__ import annotations

from collections.abc import Callable
from threading import Event


class ProviderSyncWorkerError(RuntimeError):
    """A provider synchronization worker cannot complete its lifecycle."""


class ProviderSyncWorkerV1:
    """Run Python-owned synchronization cycles with cooperative shutdown.

    ``sync_once`` owns acquisition, validation, publication, and durable cursor
    advancement. A cycle returns only after its semantic checkpoint is safe to
    retry, so restarting this loop is at-least-once but does not invent progress.
    """

    def __init__(self, sync_once: Callable[[], None], *, idle_seconds: float = 1.0) -> None:
        if idle_seconds < 0:
            raise ProviderSyncWorkerError("worker idle interval must not be negative")
        self._sync_once = sync_once
        self._idle_seconds = idle_seconds
        self._stop = Event()

    def request_stop(self) -> None:
        """Request shutdown after the current cycle completes."""

        self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def run(self, *, max_cycles: int | None = None) -> int:
        if max_cycles is not None and max_cycles <= 0:
            raise ProviderSyncWorkerError("max_cycles must be positive")
        completed = 0
        while not self.stop_requested and (max_cycles is None or completed < max_cycles):
            self._sync_once()
            completed += 1
            if max_cycles is not None and completed >= max_cycles:
                break
            self._stop.wait(self._idle_seconds)
        return completed
