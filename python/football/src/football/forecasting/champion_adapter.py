from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from scipy.stats import poisson

from football.forecasting.model_contracts import (
    FittedModelArtifact,
    ForecastInputSnapshot,
    HistoricalMatch,
    ModelForecast,
    ModelRole,
    ModelStatus,
    distributions,
)
from football.forecasting.pitchapi_v3 import _poisson_forecast
from football.forecasting.pitchapi_v3_evaluation import exact_distribution
from football.product.domain import FinishedMatch, ProductForecast, forecast_from_history

CHAMPION_MODEL_ID = "transferable-rolling-goals-poisson-v1"
CHAMPION_ADAPTER_VERSION = "transferable-rolling-goals-poisson-v1-analytic-adapter-v2"


class TransferableRollingGoalsChampion:
    model_id = CHAMPION_MODEL_ID
    model_family = "MATCHFORGE_TRANSFERABLE_POISSON"
    model_version = CHAMPION_ADAPTER_VERSION
    role = ModelRole.CHAMPION
    supports_unseen_teams = True
    requires_xg = False

    def fit(
        self, training_data: tuple[HistoricalMatch, ...], config: dict[str, object]
    ) -> FittedModelArtifact:
        raise RuntimeError("champion artifact is immutable and must be loaded")

    def predict(
        self, artifact: FittedModelArtifact, fixture: ForecastInputSnapshot
    ) -> ModelForecast:
        if artifact.model_id != self.model_id or not isinstance(artifact.runtime_model, Path):
            raise ValueError("champion artifact identity or runtime path is invalid")
        product = forecast_from_history(
            artifact_path=artifact.runtime_model,
            target_kickoff=fixture.kickoff_at,
            home_team_id=fixture.home_team_id,
            away_team_id=fixture.away_team_id,
            history=tuple(
                FinishedMatch(
                    fixture_id=item.fixture_id,
                    kickoff_at=item.kickoff_at,
                    home_team_id=item.home_team_id,
                    away_team_id=item.away_team_id,
                    home_goals=item.home_goals,
                    away_goals=item.away_goals,
                    home_xg=item.home_xg,
                    away_xg=item.away_xg,
                )
                for item in fixture.qualified_history
            ),
        )
        if product is None:
            raise ValueError("champion could not forecast eligible fixture")
        return product_to_champion_forecast(
            product,
            fixture_id=fixture.fixture_id,
            artifact_sha256=artifact.artifact_sha256,
            football_cutoff=fixture.football_cutoff,
            knowledge_cutoff=fixture.knowledge_cutoff,
            created_at=datetime.now(UTC),
            input_snapshot_sha256=fixture.sha256,
        )


def product_to_champion_forecast(
    product: ProductForecast,
    *,
    fixture_id: UUID,
    artifact_sha256: str,
    football_cutoff: datetime,
    knowledge_cutoff: datetime,
    created_at: datetime,
    input_snapshot_sha256: str,
) -> ModelForecast:
    """Expand the known Poisson control; compact display bins are never exact atoms."""
    canonical = _poisson_forecast(product.expected_home_goals, product.expected_away_goals)
    exact = exact_distribution(canonical)
    size = max(home for home, _, _ in exact.atoms) + 1
    matrix = [[0.0] * size for _ in range(size)]
    for home, away, probability in exact.atoms:
        matrix[home][away] = probability
    frozen = tuple(tuple(row) for row in matrix)
    home_distribution, away_distribution, total_distribution = distributions(frozen)
    home_mean, away_mean = product.expected_home_goals, product.expected_away_goals
    home_tail = float(poisson.sf(size - 1, home_mean))
    away_tail = float(poisson.sf(size - 1, away_mean))
    unresolved = home_tail + float(poisson.cdf(size - 1, home_mean)) * away_tail
    home_tail_moment = home_mean * (
        float(poisson.sf(size - 2, home_mean)) + float(poisson.cdf(size - 2, home_mean)) * away_tail
    )
    away_tail_moment = away_mean * (
        float(poisson.sf(size - 2, away_mean)) + float(poisson.cdf(size - 2, away_mean)) * home_tail
    )
    display_size = math.isqrt(len(product.score_matrix))
    if display_size != 6 or display_size * display_size != len(product.score_matrix):
        raise ValueError("champion compact display support is invalid")
    display = [[0.0] * display_size for _ in range(display_size)]
    for cell in product.score_matrix:
        display[int(cell["home_goals"])][int(cell["away_goals"])] = float(cell["probability"])
    over = sum(product.total_goal_distribution[3:])
    return ModelForecast(
        fixture_id=fixture_id,
        model_id=CHAMPION_MODEL_ID,
        model_family="MATCHFORGE_TRANSFERABLE_POISSON",
        model_version=CHAMPION_ADAPTER_VERSION,
        model_artifact_sha256=artifact_sha256,
        football_cutoff=football_cutoff,
        knowledge_cutoff=knowledge_cutoff,
        created_at=created_at,
        expected_home_goals=home_mean,
        expected_away_goals=away_mean,
        home_probability=product.home_probability,
        draw_probability=product.draw_probability,
        away_probability=product.away_probability,
        score_labels=tuple(str(index) for index in range(size)),
        score_matrix=frozen,
        home_goal_distribution=home_distribution,
        away_goal_distribution=away_distribution,
        total_goal_distribution=total_distribution,
        btts_yes=product.btts_yes,
        btts_no=1.0 - product.btts_yes,
        total_over_2_5=over,
        total_under_2_5=1.0 - over,
        home_clean_sheet=product.home_clean_sheet,
        away_clean_sheet=product.away_clean_sheet,
        status=ModelStatus.SUCCESS,
        warnings=(),
        input_snapshot_sha256=input_snapshot_sha256,
        numerical_contract_version="exact-support-with-tail-v2",
        unresolved_tail_probability=unresolved,
        unresolved_tail_home_expectation=home_tail_moment,
        unresolved_tail_away_expectation=away_tail_moment,
        display_score_labels=("0", "1", "2", "3", "4", "5+"),
        display_score_matrix=tuple(tuple(row) for row in display),
    )


def load_champion_artifact(
    path: Path, training_data: tuple[HistoricalMatch, ...]
) -> FittedModelArtifact:
    if not training_data:
        raise ValueError("champion artifact load requires training lineage")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("algorithm_version") != CHAMPION_MODEL_ID:
        raise ValueError("champion artifact contract is invalid")
    artifact_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    dependency_sha = str(payload.get("dependency_lock_sha256", ""))
    code_sha = str(payload.get("executor_source_commit", ""))
    return FittedModelArtifact(
        model_id=CHAMPION_MODEL_ID,
        model_family="MATCHFORGE_TRANSFERABLE_POISSON",
        model_version=CHAMPION_MODEL_ID,
        artifact_sha256=artifact_sha,
        training_start=min(item.kickoff_at for item in training_data),
        training_cutoff=max(item.kickoff_at for item in training_data),
        dataset_sha256=str(payload.get("development_manifest_sha256", "")),
        configuration=cast(dict[str, object], payload),
        dependency_version=dependency_sha,
        code_commit_sha=code_sha,
        feature_contract=str(payload.get("feature_id", "")),
        random_seed=None,
        runtime_model=path,
    )
