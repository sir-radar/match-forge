from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.retirement import ArtifactRetirementError, PostgresArtifactRetirementStore
from psycopg import Connection
from psycopg.errors import CheckViolation

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def test_unknown_retirement_target_fails_closed(connection: Connection[Any]) -> None:
    with pytest.raises(ArtifactRetirementError, match="not registered"):
        PostgresArtifactRetirementStore(connection).retire_forecast(
            uuid4(),
            evidence_reference="test",
            recorded_at=datetime(2026, 9, 5, 17, 0, tzinfo=UTC),
            code_commit_sha="a" * 40,
        )


def test_database_rejects_invalid_retirement_object_kind(connection: Connection[Any]) -> None:
    with (
        pytest.raises(CheckViolation, match="artifact_retirement_events_object_kind_check"),
        connection.transaction(),
        connection.cursor() as cursor,
    ):
        cursor.execute(
            """
            INSERT INTO football.artifact_retirement_events
                (object_kind, object_id, retirement_scope, reason, evidence_reference,
                 recorded_at, code_commit_sha)
            VALUES ('DATASET', %s, 'TEST_ONLY_HARD_GATE_EXCLUSION',
                    'SYNTHETIC_TEST_LINEAGE', 'test', %s, %s)
            """,
            (uuid4(), datetime(2026, 9, 5, 17, 0, tzinfo=UTC), "a" * 40),
        )
