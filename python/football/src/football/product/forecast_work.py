"""Drive affected-fixture generations through the shared work state machine."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row, tuple_row

from football.product.domain import sha256_json
from football.work.contracts import RetryPolicy, WorkClaim, WorkRequest, WorkType
from football.work.storage import WorkRegistry, claim_from_record


def claim_forecast_generations(
    connection: Connection[Any],
    fixture_ids: list[UUID],
    *,
    expected_generations: dict[UUID, int] | None = None,
) -> list[tuple[UUID, int, WorkClaim]]:
    """Join canonical ownership; acquire shared work before nonblocking detail locks."""
    with connection.cursor(row_factory=tuple_row) as cursor:
        cursor.execute(
            """SELECT fixture_id,generation,requested_at
            FROM football.product_forecast_refresh_work
            WHERE fixture_id=ANY(%s::uuid[]) AND generation>completed_generation""",
            (fixture_ids,),
        )
        requests = [
            (
                fixture,
                generation,
                WorkRequest(
                    work_type=WorkType.FORECAST_REFRESH,
                    semantic_key=f"product-forecast:{fixture}:{generation}",
                    input_hash=sha256_json({"fixture_id": str(fixture), "generation": generation}),
                    priority=0,
                    available_at=requested_at,
                    max_attempts=2**31 - 1,
                    retry_policy=RetryPolicy(
                        timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()
                    ),
                ),
            )
            for fixture, generation, requested_at in cursor.fetchall()
            if expected_generations is None or expected_generations.get(fixture) == generation
        ]
    claims: list[tuple[UUID, int, WorkClaim]] = []
    registry = WorkRegistry(connection)
    for fixture, generation, request in sorted(requests, key=lambda value: value[2].work_id):
        connection.execute(
            "SELECT football.record_transaction_lock(50,%s)", (f"work:{request.work_id}",)
        )
        registry.enqueue(request)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM football.claim_work(%s,%s,%s,%s)",
                (
                    f"forecast-refresh:{request.work_id}",
                    timedelta(minutes=30),
                    [WorkType.FORECAST_REFRESH.value],
                    [request.work_id],
                ),
            )
            row = cursor.fetchone()
        if row is not None:
            claims.append((fixture, generation, claim_from_record(row)))
    selected = []
    for fixture, generation, claim in sorted(claims, key=lambda value: value[0]):
        connection.execute(
            "SELECT football.record_transaction_lock(51,%s)", (f"forecast-refresh:{fixture}",)
        )
        with connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                """SELECT generation FROM football.product_forecast_refresh_work
                WHERE fixture_id=%s FOR UPDATE SKIP LOCKED""",
                (fixture,),
            )
            current = cursor.fetchone()
        if current == (generation,):
            selected.append((fixture, generation, claim))
        else:
            connection.execute(
                "SELECT football.fail_work(%s,%s,%s,%s,%s,%s,%s,NULL,NULL)",
                (
                    claim.work_id,
                    claim.lease_owner,
                    claim.lease_token,
                    claim.generation,
                    "RETRYABLE" if current is None else "CANCELLED",
                    "DETAIL_BUSY" if current is None else "SUPERSEDED_GENERATION",
                    "Forecast generation changed or is being updated",
                ),
            )
    return selected


def complete_forecast_generations(
    connection: Connection[Any], claims: list[tuple[UUID, int, WorkClaim]]
) -> None:
    """Publish completion with the exact generation and existing forecast receipts."""
    registry = WorkRegistry(connection)
    for fixture, generation, claim in sorted(claims, key=lambda value: value[2].work_id):
        with connection.cursor(row_factory=tuple_row) as cursor:
            cursor.execute(
                """SELECT forecast_id,payload_sha256 FROM football.product_forecasts
                WHERE fixture_id=%s ORDER BY forecast_id""",
                (fixture,),
            )
            receipts = [(str(row[0]), row[1]) for row in cursor.fetchall()]
        digest = sha256_json(
            {"fixture_id": str(fixture), "generation": generation, "forecasts": receipts}
        )
        with registry.publication(claim, result_hash=digest):
            connection.execute(
                """UPDATE football.product_forecast_refresh_work
                SET completed_generation=greatest(completed_generation,%s),
                    completed_at=clock_timestamp() WHERE fixture_id=%s""",
                (generation, fixture),
            )
