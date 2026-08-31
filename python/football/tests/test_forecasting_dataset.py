from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from football.forecasting.contracts import PointInTimeScopeV1
from football.forecasting.dataset import (
    RETROSPECTIVE_OUTCOME_AVAILABILITY_LAG,
    CompletedMatchV1,
    EligibleForecastTargetV1,
    EvaluationMatchOutcomeV1,
    ForecastingDatasetError,
    ForecastMatchContextV1,
    ImmutableWalkForwardTargetPlanStore,
    PointInTimeMatchDatasetProvider,
    WalkForwardDatasetSpecV1,
    WalkForwardTargetBatchV1,
    build_walk_forward_target_plan,
)
from football.forecasting.kickoff import (
    KICKOFF_CLAIM_VERSION,
    KICKOFF_TIMEZONE,
    TZDATA_VERSION,
)
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION
from jsonschema import Draft202012Validator, FormatChecker
from psycopg import Connection

DATASET = UUID(int=1)
SNAPSHOT = UUID(int=2)
COMPETITION = UUID(int=3)
SEASON = UUID(int=4)
MATCH = UUID(int=5)
HOME = UUID(int=6)
AWAY = UUID(int=7)
THIRD = UUID(int=8)
FOURTH = UUID(int=9)
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
    assert "lifecycle.known_from <= %s" in query.statement
    assert "lifecycle.claim_version = %s" in query.statement
    assert "kickoff.known_from <= %s" in query.statement
    assert query.parameters == (
        KICKOFF_CLAIM_VERSION,
        KICKOFF_TIMEZONE,
        TZDATA_VERSION,
        CUTOFF,
        CUTOFF,
        DATASET,
        LIFECYCLE_CLAIM_VERSION,
        COMPETITION,
        SEASON,
        CUTOFF,
        "bitemporal",
        timedelta(hours=2),
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


def test_walk_forward_plan_uses_only_prior_batches_for_history_eligibility() -> None:
    first = CUTOFF
    second = CUTOFF.replace(day=2)
    third = CUTOFF.replace(day=3)
    contexts = (
        ForecastMatchContextV1(UUID(int=10), COMPETITION, SEASON, first, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=11), COMPETITION, SEASON, second, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=12), COMPETITION, SEASON, second, THIRD, FOURTH),
        ForecastMatchContextV1(UUID(int=13), COMPETITION, SEASON, third, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=14), COMPETITION, SEASON, third, THIRD, FOURTH),
    )

    plan = build_walk_forward_target_plan(
        _walk_forward_spec(minimum_team_history=2, minimum_competition_history=2),
        COMPETITION,
        SEASON,
        tuple(reversed(contexts)),
    )

    assert plan.corpus_match_count == 5
    assert plan.excluded_target_count == 4
    assert len(plan.batches) == 1
    assert plan.batches[0].kickoff_at == third
    assert plan.batches[0].targets == (EligibleForecastTargetV1(contexts[3], 2, 2, 3),)
    assert len(plan.target_set_sha256) == 64
    repeated = build_walk_forward_target_plan(
        _walk_forward_spec(minimum_team_history=2, minimum_competition_history=2),
        COMPETITION,
        SEASON,
        contexts,
    )
    assert repeated == plan


def test_retrospective_plan_excludes_outcomes_not_available_before_cutoff() -> None:
    first = CUTOFF
    overlapping = first + timedelta(minutes=10)
    later = first + timedelta(hours=2, minutes=10)
    contexts = (
        ForecastMatchContextV1(UUID(int=20), COMPETITION, SEASON, first, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=21), COMPETITION, SEASON, overlapping, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=22), COMPETITION, SEASON, later, HOME, AWAY),
    )

    plan = build_walk_forward_target_plan(
        _walk_forward_spec(minimum_team_history=1, minimum_competition_history=1),
        COMPETITION,
        SEASON,
        contexts,
    )

    assert plan.excluded_target_count == 2
    assert plan.batches == (
        WalkForwardTargetBatchV1(
            later,
            (EligibleForecastTargetV1(contexts[2], 1, 1, 1),),
        ),
    )


def test_walk_forward_plan_query_is_label_free_and_outcomes_are_revealed_separately() -> None:
    context = ForecastMatchContextV1(MATCH, COMPETITION, SEASON, CUTOFF, HOME, AWAY)
    outcome = EvaluationMatchOutcomeV1(MATCH, CUTOFF, 2, 1, 7, 4, CUTOFF)
    connection = _Connection(
        [
            _Cursor(one=("published",)),
            _Cursor(many=[context]),
            _Cursor(one=("published",)),
            _Cursor(many=[outcome]),
        ]
    )
    provider = PointInTimeMatchDatasetProvider(cast(Connection[Any], connection))
    spec = _walk_forward_spec(minimum_team_history=1, minimum_competition_history=1)

    plan = provider.walk_forward_plan(spec, COMPETITION, SEASON)
    revealed = provider.reveal_outcomes(spec, (MATCH,))

    assert plan.corpus_match_count == 1
    assert plan.batches == ()
    plan_query = connection.used[1].statement
    plan_select = plan_query.split("FROM football.matches", maxsplit=1)[0]
    assert "home_score" not in plan_select
    assert "away_score" not in plan_select
    assert "corners" not in plan_select
    outcome_query = connection.used[3].statement
    assert "home_score" in outcome_query
    assert "home_corners" in outcome_query
    assert "match_corner_labels" in outcome_query
    assert "kickoff.kickoff_at + %s" in outcome_query
    assert connection.used[3].parameters[:2] == (
        "retrospective-fixed-snapshot-v1",
        timedelta(hours=2),
    )
    assert timedelta(hours=2) == RETROSPECTIVE_OUTCOME_AVAILABILITY_LAG
    assert revealed == (outcome,)


def test_walk_forward_plan_rejects_same_batch_team_reuse_and_invalid_thresholds() -> None:
    same_batch = (
        ForecastMatchContextV1(MATCH, COMPETITION, SEASON, CUTOFF, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=10), COMPETITION, SEASON, CUTOFF, HOME, THIRD),
    )
    with pytest.raises(ForecastingDatasetError, match="team appears more than once"):
        build_walk_forward_target_plan(
            _walk_forward_spec(minimum_team_history=1, minimum_competition_history=1),
            COMPETITION,
            SEASON,
            same_batch,
        )

    with pytest.raises(ForecastingDatasetError, match="minimum_team_history"):
        WalkForwardDatasetSpecV1(
            dataset_version_id=DATASET,
            source_snapshot_id=SNAPSHOT,
            feature_set_version="sprint2-team-counts-v1",
            knowledge_cutoff=CUTOFF,
            knowledge_mode="retrospective-fixed-snapshot-v1",
            quality_policy_sha256="a" * 64,
            minimum_team_history=0,
            minimum_competition_history=100,
        )


def test_outcome_reveal_rejects_missing_or_duplicate_target_identity() -> None:
    provider = PointInTimeMatchDatasetProvider(
        cast(
            Connection[Any],
            _Connection([_Cursor(one=("published",)), _Cursor(many=[])]),
        )
    )
    with pytest.raises(ForecastingDatasetError, match="outcome evidence covers 0 of 1"):
        provider.reveal_outcomes(_walk_forward_spec(), (MATCH,))

    duplicate = PointInTimeMatchDatasetProvider(cast(Connection[Any], _Connection([])))
    with pytest.raises(ForecastingDatasetError, match="duplicate outcome target"):
        duplicate.reveal_outcomes(_walk_forward_spec(), (MATCH, MATCH))


def test_target_plan_publishes_immutable_schema_valid_evidence(tmp_path: Path) -> None:
    first = CUTOFF
    second = CUTOFF.replace(day=2)
    contexts = (
        ForecastMatchContextV1(UUID(int=10), COMPETITION, SEASON, first, HOME, AWAY),
        ForecastMatchContextV1(UUID(int=11), COMPETITION, SEASON, second, HOME, AWAY),
    )
    plan = build_walk_forward_target_plan(
        _walk_forward_spec(minimum_team_history=1, minimum_competition_history=1),
        COMPETITION,
        SEASON,
        contexts,
    )
    store = ImmutableWalkForwardTargetPlanStore(tmp_path)

    published = store.publish(plan)
    repeated = store.publish(plan)

    assert published.status == "published"
    assert repeated.status == "verified_existing"
    assert repeated.relative_path == published.relative_path
    payload = plan.to_dict()
    schema_path = (
        Path(__file__).parents[3] / "schemas/contracts/walk-forward-target-plan-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)


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


def _walk_forward_spec(
    *, minimum_team_history: int = 10, minimum_competition_history: int = 100
) -> WalkForwardDatasetSpecV1:
    return WalkForwardDatasetSpecV1(
        dataset_version_id=DATASET,
        source_snapshot_id=SNAPSHOT,
        feature_set_version="sprint2-team-counts-v1",
        knowledge_cutoff=CUTOFF,
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="a" * 64,
        minimum_team_history=minimum_team_history,
        minimum_competition_history=minimum_competition_history,
    )
