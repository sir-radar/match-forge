from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

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

_TAIL_TOLERANCE = 1e-10
_INITIAL_SUPPORT = 12
_MAX_SUPPORT = 96
PENALTYBLOG_MODEL_IDS = (
    "pb-dixon-coles-v1",
    "pb-hierarchical-bayes-v1",
    "pb-negative-binomial-v1",
    "pb-weibull-copula-v1",
)


class PenaltyblogModelError(RuntimeError):
    pass


class PenaltyblogGoalModel:
    role = ModelRole.CHALLENGER
    supports_unseen_teams = False
    requires_xg = False

    def __init__(
        self,
        model_id: str,
        model_family: str,
        model_version: str,
        model_class: type[Any],
        *,
        normalize_score_grid: bool = False,
    ):
        self.model_id = model_id
        self.model_family = model_family
        self.model_version = model_version
        self._model_class = model_class
        self._normalize_score_grid = normalize_score_grid

    def fit(
        self, training_data: tuple[HistoricalMatch, ...], config: dict[str, object]
    ) -> FittedModelArtifact:
        if len(training_data) < 2:
            raise PenaltyblogModelError("penaltyblog fit requires at least two matches")
        ordered = tuple(
            sorted(training_data, key=lambda row: (row.kickoff_at, str(row.fixture_id)))
        )
        teams = {team for row in ordered for team in (row.home_team_id, row.away_team_id)}
        if len(teams) < 2:
            raise PenaltyblogModelError("penaltyblog fit requires at least two teams")
        half_life = _float_value(config.get("half_life_days", 365.0), "half_life_days")
        if not math.isfinite(half_life) or half_life <= 0:
            raise PenaltyblogModelError("half_life_days must be finite and positive")
        cutoff = ordered[-1].kickoff_at
        weights = np.array(
            [
                math.pow(0.5, (cutoff - row.kickoff_at).total_seconds() / 86_400.0 / half_life)
                for row in ordered
            ],
            dtype=float,
        )
        model = self._model_class(
            [row.home_goals for row in ordered],
            [row.away_goals for row in ordered],
            [str(row.home_team_id) for row in ordered],
            [str(row.away_team_id) for row in ordered],
            weights=weights,
        )
        seed = _optional_int(config.get("random_seed"), "random_seed")
        fit_options = config.get("fit_options", {})
        if not isinstance(fit_options, dict):
            raise PenaltyblogModelError("fit_options must be an object")
        with _numpy_seed(seed):
            model.fit(**fit_options)
        diagnostics = _diagnostics(model, config)
        dataset_sha = _dataset_sha256(ordered)
        code_commit_sha = str(config.get("code_commit_sha", ""))
        if re.fullmatch(r"[0-9a-f]{40}", code_commit_sha) is None:
            raise PenaltyblogModelError("code_commit_sha must be a 40-character lowercase Git SHA")
        manifest = {
            "model_id": self.model_id,
            "model_family": self.model_family,
            "model_version": self.model_version,
            "training_start": ordered[0].kickoff_at.astimezone(UTC).isoformat(),
            "training_cutoff": cutoff.astimezone(UTC).isoformat(),
            "dataset_sha256": dataset_sha,
            "configuration": config,
            "dependency_version": importlib.metadata.version("penaltyblog"),
            "code_commit_sha": code_commit_sha,
            "feature_contract": str(config.get("feature_contract", "forecast-input-snapshot-v1")),
            "random_seed": seed,
            "parameters": _json_safe(model.get_params()),
            "diagnostics": diagnostics,
            "score_grid_normalization": (
                "PENALTYBLOG_PUBLIC_NORMALIZE" if self._normalize_score_grid else "NONE"
            ),
        }
        artifact_sha = hashlib.sha256(_canonical_json(manifest)).hexdigest()
        return FittedModelArtifact(
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            artifact_sha256=artifact_sha,
            training_start=ordered[0].kickoff_at,
            training_cutoff=cutoff,
            dataset_sha256=dataset_sha,
            configuration=dict(config),
            dependency_version=importlib.metadata.version("penaltyblog"),
            code_commit_sha=code_commit_sha,
            feature_contract=str(config.get("feature_contract", "forecast-input-snapshot-v1")),
            random_seed=seed,
            runtime_model=model,
            diagnostics=diagnostics,
        )

    def predict(
        self, artifact: FittedModelArtifact, fixture: ForecastInputSnapshot
    ) -> ModelForecast:
        if artifact.model_id != self.model_id:
            raise PenaltyblogModelError("artifact model identity does not match adapter")
        runtime_model: Any = artifact.runtime_model
        trained_teams = {str(team) for team in runtime_model.teams}
        requested = {str(fixture.home_team_id), str(fixture.away_team_id)}
        if not requested.issubset(trained_teams):
            raise PenaltyblogModelError("UNSEEN_TEAM")
        try:
            labels, matrix = _score_matrix(
                runtime_model,
                str(fixture.home_team_id),
                str(fixture.away_team_id),
                normalize=self._normalize_score_grid,
            )
        except (KeyError, ValueError) as error:
            if "team" in str(error).casefold():
                raise PenaltyblogModelError("UNSEEN_TEAM") from error
            raise
        markets = derive_markets(matrix)
        home_goals, away_goals, total_goals = distributions(matrix)
        expected_home = sum(index * probability for index, probability in enumerate(home_goals))
        expected_away = sum(index * probability for index, probability in enumerate(away_goals))
        return ModelForecast(
            fixture_id=fixture.fixture_id,
            model_id=self.model_id,
            model_family=self.model_family,
            model_version=self.model_version,
            model_artifact_sha256=artifact.artifact_sha256,
            football_cutoff=fixture.football_cutoff,
            knowledge_cutoff=fixture.knowledge_cutoff,
            created_at=datetime.now(UTC),
            expected_home_goals=expected_home,
            expected_away_goals=expected_away,
            score_labels=labels,
            score_matrix=matrix,
            home_goal_distribution=home_goals,
            away_goal_distribution=away_goals,
            total_goal_distribution=total_goals,
            status=ModelStatus.SUCCESS,
            warnings=(
                ("PENALTYBLOG_PUBLIC_SCORE_GRID_NORMALIZATION",)
                if self._normalize_score_grid
                else ("UNRESOLVED_TAIL_BELOW_1E-10",)
            ),
            input_snapshot_sha256=fixture.sha256,
            home_probability=markets["home_probability"],
            draw_probability=markets["draw_probability"],
            away_probability=markets["away_probability"],
            btts_yes=markets["btts_yes"],
            btts_no=markets["btts_no"],
            total_over_2_5=markets["total_over_2_5"],
            total_under_2_5=markets["total_under_2_5"],
            home_clean_sheet=markets["home_clean_sheet"],
            away_clean_sheet=markets["away_clean_sheet"],
        )

    def load_trusted_runtime(self, path: Path) -> object:
        """Load a checksum-verified, trusted-local penaltyblog execution cache."""
        return self._model_class.load(str(path))


def default_penaltyblog_models() -> tuple[PenaltyblogGoalModel, ...]:
    from penaltyblog import models

    return (
        PenaltyblogGoalModel(
            "pb-dixon-coles-v1",
            "PENALTYBLOG_DIXON_COLES",
            "pb-dixon-coles-v1",
            models.DixonColesGoalModel,
        ),
        PenaltyblogGoalModel(
            "pb-hierarchical-bayes-v1",
            "PENALTYBLOG_HIERARCHICAL_BAYES",
            "pb-hierarchical-bayes-v1",
            models.HierarchicalBayesianGoalModel,
            normalize_score_grid=True,
        ),
        PenaltyblogGoalModel(
            "pb-negative-binomial-v1",
            "PENALTYBLOG_NEGATIVE_BINOMIAL",
            "pb-negative-binomial-v1",
            models.NegativeBinomialGoalModel,
        ),
        PenaltyblogGoalModel(
            "pb-weibull-copula-v1",
            "PENALTYBLOG_WEIBULL_COPULA",
            "pb-weibull-copula-v1",
            models.WeibullCopulaGoalsModel,
        ),
    )


def persist_research_artifact(artifact: FittedModelArtifact, directory: Path) -> tuple[Path, Path]:
    """Persist a checksummed manifest plus penaltyblog's public pickle runtime cache.

    Pickle is explicitly non-authoritative and must never be loaded from an untrusted location.
    The JSON manifest is the artifact identity; the pickle is a local research execution cache.
    """
    directory.mkdir(parents=True, exist_ok=True)
    runtime_path = directory / f"{artifact.artifact_sha256}.trusted-local.pkl"
    manifest_path = directory / f"{artifact.artifact_sha256}.json"
    runtime_model: Any = artifact.runtime_model
    runtime_model.save(str(runtime_path))
    runtime_sha = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
    manifest = {
        "contract": "PenaltyblogResearchArtifactV1",
        "model_id": artifact.model_id,
        "model_family": artifact.model_family,
        "model_version": artifact.model_version,
        "artifact_sha256": artifact.artifact_sha256,
        "training_start": artifact.training_start.astimezone(UTC).isoformat(),
        "training_cutoff": artifact.training_cutoff.astimezone(UTC).isoformat(),
        "dataset_sha256": artifact.dataset_sha256,
        "configuration": artifact.configuration,
        "dependency_version": artifact.dependency_version,
        "code_commit_sha": artifact.code_commit_sha,
        "feature_contract": artifact.feature_contract,
        "random_seed": artifact.random_seed,
        "diagnostics": artifact.diagnostics,
        "runtime_cache": {
            "format": "PENALTYBLOG_PUBLIC_PICKLE_TRUSTED_LOCAL_ONLY",
            "filename": runtime_path.name,
            "sha256": runtime_sha,
        },
    }
    manifest_path.write_bytes(_canonical_json(manifest) + b"\n")
    return manifest_path, runtime_path


def _score_matrix(
    model: Any, home_team: str, away_team: str, *, normalize: bool
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    if normalize:
        support = _INITIAL_SUPPORT * 2
        prediction = model.predict(home_team, away_team, max_goals=support, normalize=True)
        normalized_grid = np.asarray(prediction.goal_matrix, dtype=float)
        if (
            normalized_grid.shape != (support, support)
            or np.any(~np.isfinite(normalized_grid))
            or np.any(normalized_grid < -_TAIL_TOLERANCE)
            or float(normalized_grid.sum()) <= 0.0
        ):
            raise PenaltyblogModelError("penaltyblog returned an invalid normalized score matrix")
        normalized_grid = np.maximum(normalized_grid, 0.0)
        normalized_grid /= float(normalized_grid.sum())
        labels = tuple(str(index) for index in range(support))
        return labels, tuple(tuple(float(value) for value in row) for row in normalized_grid)
    support = _INITIAL_SUPPORT
    raw: np.ndarray[Any, Any] | None = None
    unresolved = math.inf
    while support <= _MAX_SUPPORT:
        prediction = model.predict(home_team, away_team, max_goals=support, normalize=False)
        raw = np.asarray(prediction.goal_matrix, dtype=float)
        if (
            raw.shape != (support, support)
            or np.any(~np.isfinite(raw))
            or np.any(raw < -_TAIL_TOLERANCE)
        ):
            raise PenaltyblogModelError("penaltyblog returned an invalid score matrix")
        # Weibull-Copula can emit machine-epsilon negatives. Treat only values inside
        # the declared numerical tolerance as zero; materially negative mass fails above.
        raw = np.maximum(raw, 0.0)
        unresolved = 1.0 - float(raw.sum())
        if -_TAIL_TOLERANCE <= unresolved <= _TAIL_TOLERANCE:
            unresolved = max(0.0, unresolved)
            break
        if unresolved < 0:
            raise PenaltyblogModelError("penaltyblog score mass exceeds one")
        support *= 2
    if raw is None or unresolved > _TAIL_TOLERANCE:
        raise PenaltyblogModelError("score support could not capture required probability mass")
    matrix = np.zeros((support + 1, support + 1), dtype=float)
    matrix[:support, :support] = raw
    matrix[support, support] = unresolved
    labels = tuple(str(index) for index in range(support)) + (f"{support}+",)
    return labels, tuple(tuple(float(value) for value in row) for row in matrix)


def _diagnostics(model: Any, config: dict[str, object]) -> dict[str, object]:
    if not hasattr(model, "get_diagnostics"):
        return {}
    frame = model.get_diagnostics()
    numeric = frame.select_dtypes(include=["number"])
    values = numeric.to_numpy(dtype=float)
    if values.size == 0 or np.any(~np.isfinite(values)):
        raise PenaltyblogModelError("Bayesian diagnostics are missing or non-finite")
    result = _json_safe(frame.to_dict(orient="index"))
    max_rhat = _float_value(config.get("maximum_rhat", 1.1), "maximum_rhat")
    minimum_ess = _float_value(
        config.get("minimum_effective_sample_size", 100.0),
        "minimum_effective_sample_size",
    )
    for column in frame.columns:
        normalized = str(column).casefold().replace("-", "_")
        column_values = frame[column].to_numpy(dtype=float)
        if ("rhat" in normalized or "r_hat" in normalized) and float(
            np.max(column_values)
        ) > max_rhat:
            raise PenaltyblogModelError("Bayesian R-hat exceeds configured maximum")
        if "ess" in normalized and float(np.min(column_values)) < minimum_ess:
            raise PenaltyblogModelError("Bayesian ESS is below configured minimum")
    return result if isinstance(result, dict) else {}


@contextmanager
def _numpy_seed(seed: int | None) -> Iterator[None]:
    if seed is None:
        yield
        return
    state = np.random.get_state()
    np.random.seed(seed)
    try:
        yield
    finally:
        np.random.set_state(state)


def _dataset_sha256(rows: tuple[HistoricalMatch, ...]) -> str:
    payload = [
        {
            "fixture_id": str(row.fixture_id),
            "competition_id": str(row.competition_id),
            "kickoff_at": row.kickoff_at.astimezone(UTC).isoformat(),
            "known_at": row.known_at.astimezone(UTC).isoformat(),
            "home_team_id": str(row.home_team_id),
            "away_team_id": str(row.away_team_id),
            "home_goals": row.home_goals,
            "away_goals": row.away_goals,
        }
        for row in rows
    ]
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PenaltyblogModelError(f"{name} must be an integer or null")
    return value


def _float_value(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PenaltyblogModelError(f"{name} must be numeric")
    return float(value)


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        _json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
