from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from football.forecasting.contracts import PointInTimeScopeV1
from football.forecasting.dataset import (
    CompletedMatchV1,
    ForecastingDatasetError,
    ForecastMatchContextV1,
    PointInTimeMatchDatasetProvider,
)
from football.forecasting.kickoff import (
    KICKOFF_CLAIM_VERSION,
    KICKOFF_TIMEZONE,
    TZDATA_VERSION,
)
from psycopg import Connection

DATASET = UUID(int=1)
SNAPSHOT = UUID(int=2)
COMPETITION = UUID(int=3)
SEASON = UUID(int=4)
MATCH = UUID(int=5)
HOME = UUID(int=6)
AWAY = UUID(int=7)
CUTOFF = datetime(2026, 1, 1, 15, 0, tzinfo=UTC)


class _Cursor:
    def __init__(self, *, one: object = None, many: list[object] | None = None) -> None:
        self.one = one
        self.many = [] if many is None else many
        self.statement = ""
        self.parameters: tuple[object, ...] = ()

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[object, ...]) -> _Cursor:
        self.statement = statement
        self.parameters = parameters
        return self

    def fetchone(self) -> object:
        return self.one

    def fetchall(self) -> list[object]:
        return self.many


class _Connection:
    def __init__(self, cursors: list[_Cursor]) -> None:
        self.cursors = cursors
        self.used: list[_Cursor] = []

    def cursor(self, **_kwargs: object) -> _Cursor:
        cursor = self.cursors.pop(0)
        self.used.append(cursor)
        return cursor


def test_completed_history_uses_strict_football_cutoff_and_exact_lineage() -> None:
    match = CompletedMatchV1(MATCH, COMPETITION, SEASON, CUTOFF, HOME, AWAY, 2, 1)
    connection = _Connection([_Cursor(one=("published",)), _Cursor(many=[match])])
    provider = PointInTimeMatchDatasetProvider(cast(Connection[Any], connection))

    result = provider.completed_history(_scope(), COMPETITION, SEASON)

    assert result == (match,)
    query = connection.used[1]
    assert "resolved.kickoff_at < %s" in query.statement
    assert "lifecycle.dataset_version_id = %s" in query.statement
    assert "kickoff.known_from <= %s" in query.statement
    assert query.parameters == (
        KICKOFF_CLAIM_VERSION,
        KICKOFF_TIMEZONE,
        TZDATA_VERSION,
        CUTOFF,
        DATASET,
        COMPETITION,
        SEASON,
        CUTOFF,
    )


def test_forecast_batch_is_label_free_and_groups_same_time_targets() -> None:
    context = ForecastMatchContextV1(MATCH, COMPETITION, SEASON, CUTOFF, HOME, AWAY)
    connection = _Connection([_Cursor(one=("published",)), _Cursor(many=[context])])
    provider = PointInTimeMatchDatasetProvider(cast(Connection[Any], connection))

    batch = provider.forecast_batch(_scope(), COMPETITION, SEASON)

    assert batch.matches == (context,)
    target_query = connection.used[1].statement
    select_clause = target_query.split("FROM football.matches", maxsplit=1)[0]
    assert "home_score" not in select_clause
    assert "away_score" not in select_clause
    assert "resolved.kickoff_at = %s" in target_query
    assert "lifecycle.dataset_version_id = %s" in target_query
    assert "score" not in context.to_dict()
    assert len(context.sha256) == 64


def test_provider_fails_closed_for_unregistered_scope_or_empty_batch() -> None:
    missing = _Connection([_Cursor(one=None)])
    provider = PointInTimeMatchDatasetProvider(cast(Connection[Any], missing))
    with pytest.raises(ForecastingDatasetError, match="published dataset/source"):
        provider.completed_history(_scope(), COMPETITION, SEASON)

    empty = _Connection([_Cursor(one=("published",)), _Cursor(many=[])])
    provider = PointInTimeMatchDatasetProvider(cast(Connection[Any], empty))
    with pytest.raises(ForecastingDatasetError, match="no forecast targets"):
        provider.forecast_batch(_scope(), COMPETITION, SEASON)


def _scope() -> PointInTimeScopeV1:
    return PointInTimeScopeV1(
        dataset_version_id=DATASET,
        source_snapshot_id=SNAPSHOT,
        feature_set_version="features-v1",
        football_cutoff=CUTOFF,
        knowledge_cutoff=CUTOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256="a" * 64,
        target_set_sha256="b" * 64,
    )
