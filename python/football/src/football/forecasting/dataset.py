from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import class_row

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.contracts import PointInTimeScopeV1
from football.forecasting.corner_labels import CORNER_LABEL_VERSION
from football.forecasting.kickoff import (
    KICKOFF_CLAIM_VERSION,
    KICKOFF_TIMEZONE,
    TZDATA_VERSION,
)
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION
from football.storage.raw import ImmutableFileStore


class ForecastingDatasetError(RuntimeError):
    """A point-in-time forecasting dataset cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class CompletedMatchV1:
    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID
    home_score: int
    away_score: int


@dataclass(frozen=True, slots=True)
class WalkForwardDatasetSpecV1:
    dataset_version_id: UUID
    source_snapshot_id: UUID
    feature_set_version: str
    knowledge_cutoff: datetime
    knowledge_mode: str
    quality_policy_sha256: str
    minimum_team_history: int = 10
    minimum_competition_history: int = 100
    contract: str = "WalkForwardDatasetSpecV1"

    def __post_init__(self) -> None:
        if self.contract != "WalkForwardDatasetSpecV1":
            raise ForecastingDatasetError("unsupported walk-forward dataset specification")
        for field_name, value in (
            ("minimum_team_history", self.minimum_team_history),
            ("minimum_competition_history", self.minimum_competition_history),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ForecastingDatasetError(f"{field_name} must be a positive integer")
        self.scope(self.knowledge_cutoff, "0" * 64)

    def scope(self, football_cutoff: datetime, target_set_sha256: str) -> PointInTimeScopeV1:
        return PointInTimeScopeV1(
            dataset_version_id=self.dataset_version_id,
            source_snapshot_id=self.source_snapshot_id,
            feature_set_version=self.feature_set_version,
            football_cutoff=football_cutoff,
            knowledge_cutoff=self.knowledge_cutoff,
            knowledge_mode=self.knowledge_mode,
            quality_policy_sha256=self.quality_policy_sha256,
            target_set_sha256=target_set_sha256,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "dataset_version_id": str(self.dataset_version_id),
            "source_snapshot_id": str(self.source_snapshot_id),
            "feature_set_version": self.feature_set_version,
            "knowledge_cutoff": _utc(self.knowledge_cutoff),
            "knowledge_mode": self.knowledge_mode,
            "quality_policy_sha256": self.quality_policy_sha256,
            "minimum_team_history": self.minimum_team_history,
            "minimum_competition_history": self.minimum_competition_history,
        }


@dataclass(frozen=True, slots=True)
class ForecastMatchContextV1:
    match_id: UUID
    competition_id: UUID
    season_id: UUID
    kickoff_at: datetime
    home_team_id: UUID
    away_team_id: UUID

    def __post_init__(self) -> None:
        if self.kickoff_at.tzinfo is None or self.kickoff_at.utcoffset() is None:
            raise ForecastingDatasetError("forecast kickoff_at must include a timezone")
        if self.home_team_id == self.away_team_id:
            raise ForecastingDatasetError("forecast home and away teams must differ")

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.to_dict()))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "ForecastMatchContextV1",
            "match_id": str(self.match_id),
            "competition_id": str(self.competition_id),
            "season_id": str(self.season_id),
            "kickoff_at": self.kickoff_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "home_team_id": str(self.home_team_id),
            "away_team_id": str(self.away_team_id),
        }


@dataclass(frozen=True, slots=True)
class ForecastBatchV1:
    scope: PointInTimeScopeV1
    matches: tuple[ForecastMatchContextV1, ...]

    def __post_init__(self) -> None:
        if not self.matches:
            raise ForecastingDatasetError("forecast batch must contain at least one match")
        identifiers = [match.match_id for match in self.matches]
        if len(identifiers) != len(set(identifiers)):
            raise ForecastingDatasetError("forecast batch contains duplicate matches")
        if any(match.kickoff_at != self.scope.football_cutoff for match in self.matches):
            raise ForecastingDatasetError("forecast batch kickoff must equal football cutoff")


@dataclass(frozen=True, slots=True)
class EligibleForecastTargetV1:
    context: ForecastMatchContextV1
    home_history_matches: int
    away_history_matches: int
    competition_history_matches: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("home_history_matches", self.home_history_matches),
            ("away_history_matches", self.away_history_matches),
            ("competition_history_matches", self.competition_history_matches),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ForecastingDatasetError(f"{field_name} must be a non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "context": self.context.to_dict(),
            "home_history_matches": self.home_history_matches,
            "away_history_matches": self.away_history_matches,
            "competition_history_matches": self.competition_history_matches,
        }


@dataclass(frozen=True, slots=True)
class WalkForwardTargetBatchV1:
    kickoff_at: datetime
    targets: tuple[EligibleForecastTargetV1, ...]

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "walk-forward batch kickoff_at")
        if not self.targets:
            raise ForecastingDatasetError("walk-forward target batch must not be empty")
        if any(target.context.kickoff_at != self.kickoff_at for target in self.targets):
            raise ForecastingDatasetError("walk-forward target batch mixes kickoff times")
        identifiers = [target.context.match_id for target in self.targets]
        if len(identifiers) != len(set(identifiers)):
            raise ForecastingDatasetError("walk-forward target batch contains duplicate matches")

    def to_dict(self) -> dict[str, object]:
        return {
            "kickoff_at": _utc(self.kickoff_at),
            "targets": [target.to_dict() for target in self.targets],
        }


@dataclass(frozen=True, slots=True)
class WalkForwardTargetPlanV1:
    spec: WalkForwardDatasetSpecV1
    competition_id: UUID
    season_id: UUID
    batches: tuple[WalkForwardTargetBatchV1, ...]
    corpus_match_count: int
    excluded_target_count: int
    contract: str = "WalkForwardTargetPlanV1"

    def __post_init__(self) -> None:
        if self.contract != "WalkForwardTargetPlanV1":
            raise ForecastingDatasetError("unsupported walk-forward target plan")
        if self.corpus_match_count < 0 or self.excluded_target_count < 0:
            raise ForecastingDatasetError("walk-forward target counts must not be negative")
        kickoffs = [batch.kickoff_at for batch in self.batches]
        if kickoffs != sorted(kickoffs) or len(kickoffs) != len(set(kickoffs)):
            raise ForecastingDatasetError(
                "walk-forward batches must have unique chronological times"
            )
        target_count = sum(len(batch.targets) for batch in self.batches)
        if target_count + self.excluded_target_count != self.corpus_match_count:
            raise ForecastingDatasetError("walk-forward target coverage does not reconcile")

    @property
    def target_set_sha256(self) -> str:
        identity = {
            "contract": "WalkForwardTargetSetV1",
            "targets": [
                target.context.to_dict() for batch in self.batches for target in batch.targets
            ],
        }
        return sha256_bytes(canonical_json_bytes(identity))

    @property
    def target_count(self) -> int:
        return sum(len(batch.targets) for batch in self.batches)

    def scope_for(self, batch: WalkForwardTargetBatchV1) -> PointInTimeScopeV1:
        if batch not in self.batches:
            raise ForecastingDatasetError("walk-forward batch is outside target plan")
        return self.spec.scope(batch.kickoff_at, self.target_set_sha256)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "spec": self.spec.to_dict(),
            "competition_id": str(self.competition_id),
            "season_id": str(self.season_id),
            "target_set_sha256": self.target_set_sha256,
            "corpus_match_count": self.corpus_match_count,
            "target_count": self.target_count,
            "excluded_target_count": self.excluded_target_count,
            "batches": [batch.to_dict() for batch in self.batches],
        }

    def to_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"


@dataclass(frozen=True, slots=True)
class PublishedWalkForwardTargetPlanV1:
    plan: WalkForwardTargetPlanV1
    relative_path: str
    physical_sha256: str
    size_bytes: int
    status: str


class ImmutableWalkForwardTargetPlanStore:
    def __init__(self, root: Path) -> None:
        self._files = ImmutableFileStore(root)

    def publish(self, plan: WalkForwardTargetPlanV1) -> PublishedWalkForwardTargetPlanV1:
        relative_path = f"target-set={plan.target_set_sha256}/WalkForwardTargetPlanV1.json"
        write = self._files.publish(relative_path, plan.to_bytes())
        return PublishedWalkForwardTargetPlanV1(
            plan=plan,
            relative_path=write.relative_path,
            physical_sha256=write.sha256,
            size_bytes=write.size_bytes,
            status="published" if write.status == "acquired" else "verified_existing",
        )


@dataclass(frozen=True, slots=True)
class EvaluationMatchOutcomeV1:
    match_id: UUID
    kickoff_at: datetime
    home_score: int
    away_score: int
    home_corners: int
    away_corners: int
    outcome_known_at: datetime

    def __post_init__(self) -> None:
        _aware(self.kickoff_at, "evaluation outcome kickoff_at")
        _aware(self.outcome_known_at, "evaluation outcome known_at")
        if self.outcome_known_at < self.kickoff_at:
            raise ForecastingDatasetError("evaluation outcome cannot be known before kickoff")
        for field_name, value in (
            ("home_score", self.home_score),
            ("away_score", self.away_score),
            ("home_corners", self.home_corners),
            ("away_corners", self.away_corners),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ForecastingDatasetError(f"{field_name} must be a non-negative integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "EvaluationMatchOutcomeV1",
            "match_id": str(self.match_id),
            "kickoff_at": _utc(self.kickoff_at),
            "home_score": self.home_score,
            "away_score": self.away_score,
            "home_corners": self.home_corners,
            "away_corners": self.away_corners,
            "outcome_known_at": _utc(self.outcome_known_at),
        }


class PointInTimeMatchDatasetProvider:
    """Resolve immutable history and label-free targets at explicit dual cutoffs."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def completed_history(
        self,
        scope: PointInTimeScopeV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> tuple[CompletedMatchV1, ...]:
        self._verify_scope(scope)
        with self._connection.cursor(row_factory=class_row(CompletedMatchV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, match.competition_id, match.season_id,
                       resolved.kickoff_at, observation.home_team_id,
                       observation.away_team_id, observation.home_score,
                       observation.away_score
                FROM football.matches AS match
                JOIN LATERAL (
                    SELECT kickoff.kickoff_at, kickoff.match_observation_id
                    FROM football.match_kickoff_claims AS kickoff
                    JOIN football.match_lifecycle_claims AS lifecycle
                      ON lifecycle.id = kickoff.lifecycle_claim_id
                    WHERE kickoff.match_id = match.id
                      AND kickoff.claim_version = %s
                      AND kickoff.timezone_name = %s
                      AND kickoff.tzdata_version = %s
                      AND kickoff.known_from <= %s
                      AND lifecycle.known_from <= %s
                      AND lifecycle.dataset_version_id = %s
                      AND lifecycle.claim_version = %s
                    ORDER BY kickoff.known_from DESC, kickoff.id DESC
                    LIMIT 1
                ) AS resolved ON TRUE
                JOIN football.match_observations AS observation
                  ON observation.id = resolved.match_observation_id
                WHERE match.competition_id = %s
                  AND match.season_id = %s
                  AND resolved.kickoff_at < %s
                  AND observation.home_team_id IS NOT NULL
                  AND observation.away_team_id IS NOT NULL
                  AND observation.home_score IS NOT NULL
                  AND observation.away_score IS NOT NULL
                ORDER BY resolved.kickoff_at, match.id
                """,
                (
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    scope.knowledge_cutoff,
                    scope.knowledge_cutoff,
                    scope.dataset_version_id,
                    LIFECYCLE_CLAIM_VERSION,
                    competition_id,
                    season_id,
                    scope.football_cutoff,
                ),
            ).fetchall()
        return tuple(rows)

    def forecast_batch(
        self,
        scope: PointInTimeScopeV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> ForecastBatchV1:
        self._verify_scope(scope)
        with self._connection.cursor(row_factory=class_row(ForecastMatchContextV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, match.competition_id, match.season_id,
                       resolved.kickoff_at, observation.home_team_id,
                       observation.away_team_id
                FROM football.matches AS match
                JOIN LATERAL (
                    SELECT kickoff.kickoff_at, kickoff.match_observation_id
                    FROM football.match_kickoff_claims AS kickoff
                    JOIN football.match_lifecycle_claims AS lifecycle
                      ON lifecycle.id = kickoff.lifecycle_claim_id
                    WHERE kickoff.match_id = match.id
                      AND kickoff.claim_version = %s
                      AND kickoff.timezone_name = %s
                      AND kickoff.tzdata_version = %s
                      AND kickoff.known_from <= %s
                      AND lifecycle.known_from <= %s
                      AND lifecycle.dataset_version_id = %s
                      AND lifecycle.claim_version = %s
                    ORDER BY kickoff.known_from DESC, kickoff.id DESC
                    LIMIT 1
                ) AS resolved ON TRUE
                JOIN football.match_observations AS observation
                  ON observation.id = resolved.match_observation_id
                WHERE match.competition_id = %s
                  AND match.season_id = %s
                  AND resolved.kickoff_at = %s
                  AND observation.home_team_id IS NOT NULL
                  AND observation.away_team_id IS NOT NULL
                ORDER BY match.id
                """,
                (
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    scope.knowledge_cutoff,
                    scope.knowledge_cutoff,
                    scope.dataset_version_id,
                    LIFECYCLE_CLAIM_VERSION,
                    competition_id,
                    season_id,
                    scope.football_cutoff,
                ),
            ).fetchall()
        if not rows:
            raise ForecastingDatasetError("point-in-time scope contains no forecast targets")
        return ForecastBatchV1(scope=scope, matches=tuple(rows))

    def walk_forward_plan(
        self,
        spec: WalkForwardDatasetSpecV1,
        competition_id: UUID,
        season_id: UUID,
    ) -> WalkForwardTargetPlanV1:
        self._verify_dataset(spec.dataset_version_id, spec.source_snapshot_id)
        with self._connection.cursor(row_factory=class_row(ForecastMatchContextV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, match.competition_id, match.season_id,
                       resolved.kickoff_at, observation.home_team_id,
                       observation.away_team_id
                FROM football.matches AS match
                JOIN LATERAL (
                    SELECT kickoff.kickoff_at, kickoff.match_observation_id
                    FROM football.match_kickoff_claims AS kickoff
                    JOIN football.match_lifecycle_claims AS lifecycle
                      ON lifecycle.id = kickoff.lifecycle_claim_id
                    WHERE kickoff.match_id = match.id
                      AND kickoff.claim_version = %s
                      AND kickoff.timezone_name = %s
                      AND kickoff.tzdata_version = %s
                      AND kickoff.known_from <= %s
                      AND lifecycle.known_from <= %s
                      AND lifecycle.dataset_version_id = %s
                      AND lifecycle.claim_version = %s
                    ORDER BY kickoff.known_from DESC, kickoff.id DESC
                    LIMIT 1
                ) AS resolved ON TRUE
                JOIN football.match_observations AS observation
                  ON observation.id = resolved.match_observation_id
                WHERE match.competition_id = %s
                  AND match.season_id = %s
                  AND observation.home_team_id IS NOT NULL
                  AND observation.away_team_id IS NOT NULL
                ORDER BY resolved.kickoff_at, match.id
                """,
                (
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    spec.knowledge_cutoff,
                    spec.knowledge_cutoff,
                    spec.dataset_version_id,
                    LIFECYCLE_CLAIM_VERSION,
                    competition_id,
                    season_id,
                ),
            ).fetchall()
        return build_walk_forward_target_plan(spec, competition_id, season_id, tuple(rows))

    def reveal_outcomes(
        self,
        spec: WalkForwardDatasetSpecV1,
        match_ids: tuple[UUID, ...],
    ) -> tuple[EvaluationMatchOutcomeV1, ...]:
        if not match_ids:
            raise ForecastingDatasetError("outcome reveal requires at least one target")
        if len(match_ids) != len(set(match_ids)):
            raise ForecastingDatasetError("duplicate outcome target")
        self._verify_dataset(spec.dataset_version_id, spec.source_snapshot_id)
        with self._connection.cursor(row_factory=class_row(EvaluationMatchOutcomeV1)) as cursor:
            rows = cursor.execute(
                """
                SELECT match.id AS match_id, kickoff.kickoff_at,
                       observation.home_score, observation.away_score,
                       corner.home_corners, corner.away_corners,
                       GREATEST(lifecycle.known_from, corner.known_from) AS outcome_known_at
                FROM football.matches AS match
                JOIN football.match_kickoff_claims AS kickoff
                  ON kickoff.match_id = match.id
                 AND kickoff.claim_version = %s
                 AND kickoff.timezone_name = %s
                 AND kickoff.tzdata_version = %s
                JOIN football.match_lifecycle_claims AS lifecycle
                  ON lifecycle.id = kickoff.lifecycle_claim_id
                 AND lifecycle.dataset_version_id = %s
                 AND lifecycle.claim_version = %s
                JOIN football.match_observations AS observation
                  ON observation.id = lifecycle.match_observation_id
                JOIN football.match_corner_labels AS corner
                  ON corner.lifecycle_claim_id = lifecycle.id
                 AND corner.match_id = match.id
                 AND corner.claim_version = %s
                WHERE match.id = ANY(%s)
                  AND kickoff.known_from <= %s
                  AND lifecycle.known_from <= %s
                  AND corner.known_from <= %s
                  AND observation.home_score IS NOT NULL
                  AND observation.away_score IS NOT NULL
                ORDER BY kickoff.kickoff_at, match.id
                """,
                (
                    KICKOFF_CLAIM_VERSION,
                    KICKOFF_TIMEZONE,
                    TZDATA_VERSION,
                    spec.dataset_version_id,
                    LIFECYCLE_CLAIM_VERSION,
                    CORNER_LABEL_VERSION,
                    list(match_ids),
                    spec.knowledge_cutoff,
                    spec.knowledge_cutoff,
                    spec.knowledge_cutoff,
                ),
            ).fetchall()
        outcomes = tuple(rows)
        actual_ids = {outcome.match_id for outcome in outcomes}
        if len(outcomes) != len(match_ids) or actual_ids != set(match_ids):
            raise ForecastingDatasetError(
                f"outcome evidence covers {len(actual_ids)} of {len(match_ids)} targets"
            )
        return outcomes

    def _verify_scope(self, scope: PointInTimeScopeV1) -> None:
        self._verify_dataset(scope.dataset_version_id, scope.source_snapshot_id)

    def _verify_dataset(self, dataset_version_id: UUID, source_snapshot_id: UUID) -> None:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT status
                FROM football.dataset_versions
                WHERE id = %s AND source_snapshot_id = %s
                """,
                (dataset_version_id, source_snapshot_id),
            ).fetchone()
        if row != ("published",):
            raise ForecastingDatasetError(
                "point-in-time scope does not reference one published dataset/source pair"
            )


def build_walk_forward_target_plan(
    spec: WalkForwardDatasetSpecV1,
    competition_id: UUID,
    season_id: UUID,
    contexts: tuple[ForecastMatchContextV1, ...],
) -> WalkForwardTargetPlanV1:
    identifiers = [context.match_id for context in contexts]
    if len(identifiers) != len(set(identifiers)):
        raise ForecastingDatasetError("walk-forward corpus contains duplicate matches")
    if any(
        context.competition_id != competition_id or context.season_id != season_id
        for context in contexts
    ):
        raise ForecastingDatasetError("walk-forward context is outside requested corpus")
    ordered = sorted(contexts, key=lambda context: (context.kickoff_at, str(context.match_id)))
    grouped: list[list[ForecastMatchContextV1]] = []
    for context in ordered:
        if not grouped or grouped[-1][0].kickoff_at != context.kickoff_at:
            grouped.append([context])
        else:
            grouped[-1].append(context)
    team_history: defaultdict[UUID, int] = defaultdict(int)
    competition_history = 0
    batches: list[WalkForwardTargetBatchV1] = []
    excluded = 0
    for group in grouped:
        _require_distinct_batch_teams(group)
        targets = tuple(
            EligibleForecastTargetV1(
                context=context,
                home_history_matches=team_history[context.home_team_id],
                away_history_matches=team_history[context.away_team_id],
                competition_history_matches=competition_history,
            )
            for context in group
            if competition_history >= spec.minimum_competition_history
            and team_history[context.home_team_id] >= spec.minimum_team_history
            and team_history[context.away_team_id] >= spec.minimum_team_history
        )
        excluded += len(group) - len(targets)
        if targets:
            batches.append(WalkForwardTargetBatchV1(group[0].kickoff_at, targets))
        for context in group:
            team_history[context.home_team_id] += 1
            team_history[context.away_team_id] += 1
        competition_history += len(group)
    return WalkForwardTargetPlanV1(
        spec=spec,
        competition_id=competition_id,
        season_id=season_id,
        batches=tuple(batches),
        corpus_match_count=len(contexts),
        excluded_target_count=excluded,
    )


def _require_distinct_batch_teams(group: list[ForecastMatchContextV1]) -> None:
    team_ids = [
        team_id for context in group for team_id in (context.home_team_id, context.away_team_id)
    ]
    if len(team_ids) != len(set(team_ids)):
        raise ForecastingDatasetError("one team appears more than once in a chronological batch")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ForecastingDatasetError(f"{field_name} must include a timezone")


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
