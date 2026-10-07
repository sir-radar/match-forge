from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from football.forecasting.model_contracts import (
    FittedModelArtifact,
    ForecastInputSnapshot,
    HistoricalMatch,
    ModelForecast,
    ModelRole,
    ModelStatus,
    derive_markets,
    distributions,
)
from football.product.domain import FinishedMatch, forecast_from_history

CHAMPION_MODEL_ID = "transferable-rolling-goals-poisson-v1"


class TransferableRollingGoalsChampion:
    model_id = CHAMPION_MODEL_ID
    model_family = "MATCHFORGE_TRANSFERABLE_POISSON"
    model_version = CHAMPION_MODEL_ID
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
        size = round(math.sqrt(len(product.score_matrix)))
        matrix = [[0.0] * size for _ in range(size)]
        for cell in product.score_matrix:
            matrix[int(cell["home_goals"])][int(cell["away_goals"])] = float(cell["probability"])
        frozen = tuple(tuple(row) for row in matrix)
        home, away, total = distributions(frozen)
        markets = derive_markets(frozen)
        return ModelForecast(
            fixture_id=fixture.fixture_id,
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            model_artifact_sha256=artifact.artifact_sha256,
            football_cutoff=fixture.football_cutoff,
            knowledge_cutoff=fixture.knowledge_cutoff,
            created_at=datetime.now(UTC),
            expected_home_goals=sum(i * value for i, value in enumerate(home)),
            expected_away_goals=sum(i * value for i, value in enumerate(away)),
            home_probability=markets["home_probability"],
            draw_probability=markets["draw_probability"],
            away_probability=markets["away_probability"],
            score_labels=tuple(str(index) for index in range(size - 1)) + (f"{size - 1}+",),
            score_matrix=frozen,
            home_goal_distribution=home,
            away_goal_distribution=away,
            total_goal_distribution=total,
            btts_yes=markets["btts_yes"],
            btts_no=markets["btts_no"],
            total_over_2_5=markets["total_over_2_5"],
            total_under_2_5=markets["total_under_2_5"],
            home_clean_sheet=markets["home_clean_sheet"],
            away_clean_sheet=markets["away_clean_sheet"],
            status=ModelStatus.SUCCESS,
            warnings=(),
            input_snapshot_sha256=fixture.sha256,
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
