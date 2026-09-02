from __future__ import annotations

import pytest
from football.providers import ProviderSyncWorkerError, ProviderSyncWorkerV1


def test_worker_runs_bounded_cycles_and_can_stop_cooperatively() -> None:
    calls: list[int] = []

    def sync_once() -> None:
        calls.append(len(calls) + 1)

    worker = ProviderSyncWorkerV1(sync_once, idle_seconds=0)
    assert worker.run(max_cycles=3) == 3
    assert calls == [1, 2, 3]
    assert not worker.stop_requested

    worker.request_stop()
    assert worker.run(max_cycles=3) == 0


def test_worker_stop_request_after_cycle_preserves_completed_work() -> None:
    calls: list[int] = []
    worker: ProviderSyncWorkerV1

    def sync_once() -> None:
        calls.append(1)
        worker.request_stop()

    worker = ProviderSyncWorkerV1(sync_once, idle_seconds=0)
    assert worker.run() == 1
    assert worker.stop_requested


def test_worker_rejects_invalid_limits() -> None:
    with pytest.raises(ProviderSyncWorkerError, match="idle interval"):
        ProviderSyncWorkerV1(lambda: None, idle_seconds=-1)
    with pytest.raises(ProviderSyncWorkerError, match="max_cycles"):
        ProviderSyncWorkerV1(lambda: None).run(max_cycles=0)
