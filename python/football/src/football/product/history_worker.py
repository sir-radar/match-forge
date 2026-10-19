"""Shared-work execution of the existing history provider/fallback workflow."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from football.contracts.source import canonical_json_bytes
from football.product.api_football import ApiFootballClient, ApiResponse
from football.product.football_data_org import FootballDataOrgClient, FootballDataResponse
from football.product.history_work import (
    claim_history_request,
    complete_history_request,
    fail_history_request,
    heartbeat_history_request,
)
from football.product.sync import (
    FALLBACK_PROVIDER_CODE,
    HISTORY_JOB_LEASE,
    PROVIDER_CODE,
    ProductSync,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks
from football.storage.raw import ImmutableFileStore
from football.work.contracts import RetryClassification, WorkClaim, WorkContractError
from football.work.storage import WorkConflict, WorkLeaseLost, WorkRegistry


class HistorySyncWorker(ProductSync):
    """One owned request per worker; provider I/O runs between short publications."""

    def __init__(
        self,
        connection: Connection[Any],
        client: ApiFootballClient,
        data_root: Path,
        artifact_path: Path,
        history_fallback: FootballDataOrgClient | None = None,
        api_football_max_history_season: int | None = None,
        sync_run_id: UUID | None = None,
    ) -> None:
        super().__init__(
            connection,
            client,
            data_root,
            artifact_path,
            history_fallback,
            api_football_max_history_season=api_football_max_history_season,
            sync_run_id=sync_run_id,
        )
        self._owner = f"product-history:{uuid4()}"
        self._claim: WorkClaim | None = None
        self._job_id: UUID | None = None
        self._scope: tuple[int, int] | None = None
        self._sources: set[UUID] = set()
        self._result = (0, 0)
        self._inside_step = False

    def _claim_history_job(self, batch_started_at: datetime) -> tuple[UUID, int, int, int] | None:
        if self._claim is not None:
            raise WorkContractError("history worker already owns a request")
        with self.connection.transaction(), self.connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                """SELECT queue.job_id FROM football.product_history_sync_queue queue
                WHERE queue.updated_at<%s AND (queue.job_status='PENDING' OR
                    (queue.job_status='RUNNING' AND EXISTS (
                        SELECT 1 FROM football.product_history_work binding
                        WHERE binding.job_id=queue.job_id AND binding.queued_at=queue.queued_at)))
                ORDER BY queue.queued_at,queue.job_id""",
                (batch_started_at,),
            )
            candidates = cursor.fetchall()
        for (job_id,) in candidates:
            claim = claim_history_request(
                self.connection,
                job_id,
                self._owner,
                batch_started_at,
                lease_duration=HISTORY_JOB_LEASE,
            )
            if claim is None:
                continue
            with (
                self.connection.transaction(),
                self.connection.cursor(row_factory=tuple_row) as cursor,
            ):
                cursor.execute(
                    """SELECT provider_competition_id,season,attempt_offset
                    FROM football.product_history_work WHERE work_id=%s""",
                    (claim.work_id,),
                )
                bound = cursor.fetchone()
                assert bound is not None
            self._claim = heartbeat_history_request(
                self.connection,
                claim,
                HISTORY_JOB_LEASE,
                sync_run_id=self.sync_run_id,
            )
            self._job_id = job_id
            self._scope = (int(bound[0]), bound[1])
            self._sources = set()
            self._result = (0, 0)
            return job_id, self._scope[0], self._scope[1], bound[2] + claim.attempt_count
        return None

    def _owned(self, job_id: UUID | None = None) -> WorkClaim:
        if self._claim is None or (job_id is not None and job_id != self._job_id):
            raise WorkLeaseLost("history worker does not own this request")
        return self._claim

    def _before_io(self) -> None:
        if self._inside_step:
            raise WorkContractError("history provider/file I/O cannot run inside publication")
        claim = self._owned()
        # Entry to job execution is idle. Writes only occur in _database_step;
        # any transaction here contains this worker's subsequent reads.
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            self.connection.commit()
        self._claim = heartbeat_history_request(
            self.connection,
            claim,
            HISTORY_JOB_LEASE,
            sync_run_id=self.sync_run_id,
        )

    @contextmanager
    def _database_step(self) -> Iterator[None]:
        if self._inside_step:
            yield
            return
        self._before_io()
        with self.connection.transaction():
            acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
            with WorkRegistry(self.connection).progress(self._owned()):
                self._inside_step = True
                try:
                    yield
                finally:
                    self._inside_step = False

    def _sync_history_job(self, league_id: int, season: int) -> tuple[int, int]:
        self._owned()
        if self.connection.info.transaction_status != TransactionStatus.IDLE:
            raise WorkContractError("history execution requires an idle connection")
        if (league_id, season) != self._scope:
            raise WorkConflict("history execution scope differs from its immutable request")
        self._result = super()._sync_history_job(league_id, season)
        return self._result

    def _api_football_history(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        self._before_io()
        return super()._api_football_history(league_id, season)

    def _football_data_org_history(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        self._before_io()
        return super()._football_data_org_history(league_id, season)

    def _fallback_standings(self, league_id: int, season: int) -> FootballDataResponse | None:
        self._before_io()
        return super()._fallback_standings(league_id, season)

    def _local_history_result(
        self, league_id: int, season: int
    ) -> tuple[UUID, datetime, int] | None:
        result = super()._local_history_result(league_id, season)
        if result is not None:
            self._sources.add(result[0])
        return result

    def _record_response(self, resource_name: str, response: ApiResponse) -> UUID:
        self._before_io()
        prepared = self._prepare_response(PROVIDER_CODE, response)
        with self._database_step():
            snapshot = super()._register_response(resource_name, response, prepared)
        self._sources.add(snapshot)
        return snapshot

    def _record_fallback_response(self, resource_name: str, response: FootballDataResponse) -> UUID:
        self._before_io()
        prepared = self._prepare_response(FALLBACK_PROVIDER_CODE, response)
        with self._database_step():
            snapshot = super()._register_fallback_response(resource_name, response, prepared)
        self._sources.add(snapshot)
        return snapshot

    def _store_history(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        count = 0
        for row in rows:
            with self._database_step():
                count += super()._store_history([row], snapshot_id, observed_at)
        return count

    def _store_fallback_history(
        self,
        rows: Sequence[Mapping[str, Any]],
        competition_id: UUID,
        season: int,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> int:
        count = 0
        for row in rows:
            with self._database_step():
                count += super()._store_fallback_history(
                    [row], competition_id, season, snapshot_id, observed_at
                )
        return count

    def _competition_id(self, provider_competition_id: str, snapshot_id: UUID) -> UUID:
        with self._database_step():
            return super()._competition_id(provider_competition_id, snapshot_id)

    def _store_standings(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        with self._database_step():
            return super()._store_standings(rows, snapshot_id, observed_at)

    def _store_fallback_standings(
        self,
        rows: Sequence[Mapping[str, Any]],
        competition_id: UUID,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> int:
        with self._database_step():
            return super()._store_fallback_standings(rows, competition_id, snapshot_id, observed_at)

    def _calculate_standings(self, competition_id: UUID, season: int, observed_at: datetime) -> int:
        with self._database_step():
            return super()._calculate_standings(competition_id, season, observed_at)

    def _record_history_sync_attempt(
        self,
        league_id: int,
        season: int,
        attempted_at: datetime,
        status: str,
        resolution_path: Sequence[str],
        provider_codes: Sequence[str],
    ) -> None:
        with self._database_step():
            super()._record_history_sync_attempt(
                league_id,
                season,
                attempted_at,
                status,
                resolution_path,
                provider_codes,
            )

    def _complete_history_job(self, job_id: UUID) -> None:
        self._before_io()
        claim = self._owned(job_id)
        with self.connection.transaction(), self.connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                """SELECT id,source_snapshot_id,sha256 FROM football.source_resources
                WHERE source_snapshot_id=ANY(%s::uuid[]) ORDER BY id""",
                (list(self._sources),),
            )
            resources = [
                {
                    "source_resource_id": str(row[0]),
                    "source_snapshot_id": str(row[1]),
                    "sha256": row[2],
                }
                for row in cursor.fetchall()
            ]
        receipt = canonical_json_bytes(
            {
                "work_id": str(claim.work_id),
                "input_hash": claim.input_hash,
                "source_snapshot_ids": [str(value) for value in sorted(self._sources)],
                "source_resources": resources,
                "history_matches": self._result[0],
                "standings_rows": self._result[1],
            }
        )
        digest = hashlib.sha256(receipt).hexdigest()
        ImmutableFileStore(self.data_root).publish(f"work/history/{digest}.json", receipt)
        complete_history_request(self.connection, claim, result_hash=digest)
        self._claim = None
        self._job_id = None

    def _retry_history_job(self, job_id: UUID, attempt_count: int, error: Exception) -> None:
        self._failure(job_id, error, RetryClassification.RETRYABLE)

    def _fail_history_job(self, job_id: UUID, error: Exception) -> None:
        self._failure(job_id, error, RetryClassification.NON_RETRYABLE)

    def _failure(self, job_id: UUID, error: Exception, classification: RetryClassification) -> None:
        fail_history_request(
            self.connection,
            self._owned(job_id),
            classification,
            error_code=type(error).__name__,
            error_message=str(error) or type(error).__name__,
        )
        self._claim = None
        self._job_id = None
