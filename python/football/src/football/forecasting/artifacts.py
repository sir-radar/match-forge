from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection, Cursor

from football.contracts.source import canonical_json_bytes, sha256_bytes
from football.forecasting.contracts import (
    ArtifactCompatibilityV1,
    ArtifactFileV1,
    ModelArtifactManifestV1,
    ModelFitSpecV1,
)
from football.forecasting.corner import (
    CornerDistribution,
    CornerFeatures,
    CornerFit,
    CornerModelConfig,
    CornerParameters,
)
from football.forecasting.dixon_coles import (
    DixonColesConfig,
    DixonColesFit,
    DixonColesParameters,
)
from football.forecasting.elo import EloConfig, EloRun, RatedEloMatch
from football.storage.raw import ImmutableFileStore

ArtifactPublicationStatus = Literal["published", "verified_existing"]


class ArtifactPublicationError(RuntimeError):
    """Portable artifact bytes or registry rows conflict with immutable state."""


@dataclass(frozen=True, slots=True)
class PublishedModelArtifactV1:
    manifest: ModelArtifactManifestV1
    manifest_path: str
    manifest_sha256: str
    status: ArtifactPublicationStatus


@dataclass(frozen=True, slots=True)
class LoadedPortableModelStateV1:
    manifest: ModelArtifactManifestV1
    state: dict[str, object]


class PortableModelArtifactStore:
    """Publish canonical, implementation-independent model state and its manifest."""

    def __init__(self, data_root: Path) -> None:
        self._files = ImmutableFileStore(data_root)

    def publish(
        self,
        *,
        model_artifact_id: UUID,
        fit_spec: ModelFitSpecV1,
        state: Mapping[str, object],
        created_at: datetime,
    ) -> PublishedModelArtifactV1:
        _aware(created_at, "created_at")
        portable_state = {
            "contract": "PortableModelStateV1",
            "model_family": fit_spec.model_family,
            "algorithm_version": fit_spec.algorithm_version,
            "fit_spec_sha256": fit_spec.sha256,
            "state": _portable_json(dict(state), "state"),
        }
        state_payload = canonical_json_bytes(portable_state) + b"\n"
        state_sha256 = sha256_bytes(canonical_json_bytes(portable_state))
        artifact_root = (
            f"models/family={fit_spec.model_family.lower()}/artifact={model_artifact_id}"
        )
        state_write = self._files.publish(f"{artifact_root}/model-state-v1.json", state_payload)
        manifest = ModelArtifactManifestV1(
            model_artifact_id=model_artifact_id,
            model_family=fit_spec.model_family,
            fit_spec_sha256=fit_spec.sha256,
            schema_version="model-artifact-v1",
            algorithm_version=fit_spec.algorithm_version,
            serializer_version="canonical-json-v1",
            compatibility=ArtifactCompatibilityV1(
                runtime="python",
                runtime_version=">=3.13,<3.14",
                loader_version="canonical-json-loader-v1",
                feature_contract_version=fit_spec.scope.feature_set_version,
            ),
            logical_model_state_sha256=state_sha256,
            created_at=created_at,
            files=(
                ArtifactFileV1(
                    relative_path=state_write.relative_path,
                    media_type="application/json",
                    size_bytes=state_write.size_bytes,
                    physical_sha256=state_write.sha256,
                ),
            ),
        )
        manifest_path = f"{artifact_root}/model-artifact-manifest-v1.json"
        manifest_write = self._files.publish(manifest_path, manifest.to_bytes())
        status: ArtifactPublicationStatus = (
            "published"
            if "acquired" in (state_write.status, manifest_write.status)
            else "verified_existing"
        )
        return PublishedModelArtifactV1(
            manifest=manifest,
            manifest_path=manifest_path,
            manifest_sha256=manifest_write.sha256,
            status=status,
        )

    def load(
        self,
        publication: PublishedModelArtifactV1,
        *,
        expected_feature_contract_version: str,
    ) -> LoadedPortableModelStateV1:
        manifest = publication.manifest
        _validate_compatibility(manifest, expected_feature_contract_version)
        _verify_manifest(self._files, publication)
        if len(manifest.files) != 1:
            raise ArtifactPublicationError("model artifact schema requires one state file")
        envelope = _load_state_envelope(self._files, manifest.files[0])
        if sha256_bytes(canonical_json_bytes(envelope)) != manifest.logical_model_state_sha256:
            raise ArtifactPublicationError("logical model state checksum mismatch")
        expected_identity = {
            "contract": "PortableModelStateV1",
            "model_family": manifest.model_family,
            "algorithm_version": manifest.algorithm_version,
            "fit_spec_sha256": manifest.fit_spec_sha256,
        }
        if any(envelope.get(key) != value for key, value in expected_identity.items()):
            raise ArtifactPublicationError("model state envelope conflicts with manifest")
        state = dict(_object_mapping(envelope.get("state"), "model state"))
        return LoadedPortableModelStateV1(manifest=manifest, state=state)


class PostgresModelArtifactRegistry:
    """Register immutable artifact lineage with conflict-detecting retries."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(
        self,
        artifact: PublishedModelArtifactV1,
        fit_spec: ModelFitSpecV1,
    ) -> ArtifactPublicationStatus:
        manifest = artifact.manifest
        if manifest.fit_spec_sha256 != fit_spec.sha256:
            raise ArtifactPublicationError("artifact manifest does not match fit specification")
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"model-artifact:{fit_spec.sha256}",),
            )
            inserted = self._register_artifact(cursor, artifact)
            for file in manifest.files:
                inserted += self._register_file(cursor, manifest.model_artifact_id, file)
            inserted += self._register_input(cursor, manifest.model_artifact_id, fit_spec)
        return "published" if inserted else "verified_existing"

    @staticmethod
    def _register_artifact(cursor: Cursor[Any], artifact: PublishedModelArtifactV1) -> int:
        manifest = artifact.manifest
        inserted = cursor.execute(
            """
            INSERT INTO football.model_artifacts
                (id, model_family, fit_spec_sha256, logical_model_state_sha256,
                 schema_version, algorithm_version, serializer_version,
                 manifest_path, manifest_sha256, status, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', %s)
            ON CONFLICT (fit_spec_sha256) DO NOTHING
            """,
            (
                manifest.model_artifact_id,
                manifest.model_family,
                manifest.fit_spec_sha256,
                manifest.logical_model_state_sha256,
                manifest.schema_version,
                manifest.algorithm_version,
                manifest.serializer_version,
                artifact.manifest_path,
                artifact.manifest_sha256,
                manifest.created_at,
            ),
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, model_family, fit_spec_sha256, logical_model_state_sha256,
                   schema_version, algorithm_version, serializer_version,
                   manifest_path, manifest_sha256, status, published_at
            FROM football.model_artifacts WHERE fit_spec_sha256 = %s
            """,
            (manifest.fit_spec_sha256,),
        ).fetchone()
        expected = (
            manifest.model_artifact_id,
            manifest.model_family,
            manifest.fit_spec_sha256,
            manifest.logical_model_state_sha256,
            manifest.schema_version,
            manifest.algorithm_version,
            manifest.serializer_version,
            artifact.manifest_path,
            artifact.manifest_sha256,
            "published",
            manifest.created_at,
        )
        if row != expected:
            raise ArtifactPublicationError(
                f"model artifact conflicts with registered fit: {manifest.fit_spec_sha256}"
            )
        return inserted

    @staticmethod
    def _register_file(cursor: Cursor[Any], model_artifact_id: UUID, file: ArtifactFileV1) -> int:
        inserted = cursor.execute(
            """
            INSERT INTO football.model_artifact_files
                (model_artifact_id, relative_path, media_type, physical_sha256, size_bytes)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (model_artifact_id, relative_path) DO NOTHING
            """,
            (
                model_artifact_id,
                file.relative_path,
                file.media_type,
                file.physical_sha256,
                file.size_bytes,
            ),
        ).rowcount
        row = cursor.execute(
            """
            SELECT relative_path, media_type, physical_sha256, size_bytes
            FROM football.model_artifact_files
            WHERE model_artifact_id = %s AND relative_path = %s
            """,
            (model_artifact_id, file.relative_path),
        ).fetchone()
        if row != (
            file.relative_path,
            file.media_type,
            file.physical_sha256,
            file.size_bytes,
        ):
            raise ArtifactPublicationError(
                f"model artifact file conflicts with registry: {file.relative_path}"
            )
        return inserted

    @staticmethod
    def _register_input(
        cursor: Cursor[Any], model_artifact_id: UUID, fit_spec: ModelFitSpecV1
    ) -> int:
        scope = fit_spec.scope
        inserted = cursor.execute(
            """
            INSERT INTO football.model_artifact_inputs
                (model_artifact_id, dataset_version_id, source_snapshot_id,
                 feature_set_version, football_cutoff, knowledge_cutoff, knowledge_mode,
                 quality_policy_sha256, target_set_sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_artifact_id, dataset_version_id) DO NOTHING
            """,
            (
                model_artifact_id,
                scope.dataset_version_id,
                scope.source_snapshot_id,
                scope.feature_set_version,
                scope.football_cutoff,
                scope.knowledge_cutoff,
                scope.knowledge_mode,
                scope.quality_policy_sha256,
                scope.target_set_sha256,
            ),
        ).rowcount
        row = cursor.execute(
            """
            SELECT dataset_version_id, source_snapshot_id, feature_set_version,
                   football_cutoff, knowledge_cutoff, knowledge_mode, quality_policy_sha256,
                   target_set_sha256
            FROM football.model_artifact_inputs
            WHERE model_artifact_id = %s AND dataset_version_id = %s
            """,
            (model_artifact_id, scope.dataset_version_id),
        ).fetchone()
        expected = (
            scope.dataset_version_id,
            scope.source_snapshot_id,
            scope.feature_set_version,
            scope.football_cutoff,
            scope.knowledge_cutoff,
            scope.knowledge_mode,
            scope.quality_policy_sha256,
            scope.target_set_sha256,
        )
        if row != expected:
            raise ArtifactPublicationError(
                f"model artifact input conflicts with registry: {model_artifact_id}"
            )
        return inserted


class ModelArtifactPublisher:
    """Publish portable bytes before atomically reconciling their database identity."""

    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._store = PortableModelArtifactStore(data_root)

    def publish(
        self,
        *,
        model_artifact_id: UUID,
        fit_spec: ModelFitSpecV1,
        state: Mapping[str, object],
        created_at: datetime,
    ) -> PublishedModelArtifactV1:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"model-artifact:{fit_spec.sha256}",),
            )
            existing = cursor.execute(
                """
                SELECT id, published_at FROM football.model_artifacts
                WHERE fit_spec_sha256 = %s
                """,
                (fit_spec.sha256,),
            ).fetchone()
            resolved_id = model_artifact_id if existing is None else UUID(str(existing[0]))
            resolved_created_at = created_at if existing is None else existing[1]
            artifact = self._store.publish(
                model_artifact_id=resolved_id,
                fit_spec=fit_spec,
                state=state,
                created_at=resolved_created_at,
            )
            inserted = PostgresModelArtifactRegistry._register_artifact(cursor, artifact)
            for file in artifact.manifest.files:
                inserted += PostgresModelArtifactRegistry._register_file(cursor, resolved_id, file)
            inserted += PostgresModelArtifactRegistry._register_input(cursor, resolved_id, fit_spec)
        if artifact.status == "verified_existing" and not inserted:
            return artifact
        return PublishedModelArtifactV1(
            manifest=artifact.manifest,
            manifest_path=artifact.manifest_path,
            manifest_sha256=artifact.manifest_sha256,
            status="published",
        )


def _validate_compatibility(
    manifest: ModelArtifactManifestV1, expected_feature_contract_version: str
) -> None:
    compatibility = manifest.compatibility
    if manifest.schema_version != "model-artifact-v1":
        raise ArtifactPublicationError("unsupported artifact schema version")
    if manifest.serializer_version != "canonical-json-v1":
        raise ArtifactPublicationError("unsupported artifact serializer version")
    if compatibility.runtime != "python" or compatibility.loader_version != (
        "canonical-json-loader-v1"
    ):
        raise ArtifactPublicationError("unsupported artifact compatibility declaration")
    if compatibility.feature_contract_version != expected_feature_contract_version:
        raise ArtifactPublicationError("unsupported artifact feature contract")


def _verify_manifest(files: ImmutableFileStore, publication: PublishedModelArtifactV1) -> None:
    path = files.path_for(publication.manifest_path)
    if not path.is_file() or path.is_symlink():
        raise ArtifactPublicationError("model artifact manifest is missing")
    payload = path.read_bytes()
    if payload != publication.manifest.to_bytes() or sha256_bytes(payload) != (
        publication.manifest_sha256
    ):
        raise ArtifactPublicationError("model artifact manifest checksum mismatch")


def _load_state_envelope(files: ImmutableFileStore, file: ArtifactFileV1) -> Mapping[str, object]:
    path = files.path_for(file.relative_path)
    if not path.is_file() or path.is_symlink():
        raise ArtifactPublicationError("model artifact state file is missing")
    payload = path.read_bytes()
    if len(payload) != file.size_bytes or sha256_bytes(payload) != file.physical_sha256:
        raise ArtifactPublicationError("model artifact state checksum mismatch")
    try:
        return _object_mapping(json.loads(payload), "model state envelope")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ArtifactPublicationError("model artifact state is not valid JSON") from error


def serialize_elo_run(run: EloRun) -> dict[str, object]:
    return {
        "contract": "EloModelStateV1",
        "config": run.config.to_dict(),
        "matches": [
            {
                "match_id": str(match.match_id),
                "competition_id": str(match.competition_id),
                "kickoff_at": _utc(match.kickoff_at),
                "home_team_id": str(match.home_team_id),
                "away_team_id": str(match.away_team_id),
                "home_score": match.home_score,
                "away_score": match.away_score,
                "home_pre_match_rating": match.home_pre_match_rating,
                "away_pre_match_rating": match.away_pre_match_rating,
                "expected_home_score": match.expected_home_score,
                "actual_home_score": match.actual_home_score,
                "home_post_match_rating": match.home_post_match_rating,
                "away_post_match_rating": match.away_post_match_rating,
            }
            for match in run.matches
        ],
        "ratings": _serialize_elo_ratings(run),
    }


def _serialize_elo_ratings(run: EloRun) -> list[dict[str, object]]:
    return [
        {
            "match_id": str(rating.match_id),
            "competition_id": str(rating.competition_id),
            "team_id": str(rating.team_id),
            "opponent_team_id": str(rating.opponent_team_id),
            "rating_timestamp": _utc(rating.rating_timestamp),
            "is_home": rating.is_home,
            "pre_match_rating": rating.pre_match_rating,
            "rating": rating.rating,
            "expected_score": rating.expected_score,
            "actual_score": rating.actual_score,
        }
        for rating in run.history
    ]


def deserialize_elo_run(state: Mapping[str, object]) -> EloRun:
    if state.get("contract") != "EloModelStateV1":
        raise ArtifactPublicationError("unsupported Elo model state")
    config_values = _object_mapping(state.get("config"), "Elo config")
    config = EloConfig(
        model_version=_string(config_values, "model_version"),
        initial_rating=_float(config_values, "initial_rating"),
        k_factor=_float(config_values, "k_factor"),
        home_advantage=_float(config_values, "home_advantage"),
        time_decay_half_life_days=_optional_float(config_values, "time_decay_half_life_days"),
        competition_weights=_uuid_float_mapping(config_values, "competition_weights"),
    )
    raw_matches = state.get("matches")
    if not isinstance(raw_matches, list):
        raise ArtifactPublicationError("Elo model state matches must be a list")
    matches = tuple(_deserialize_rated_elo_match(value) for value in raw_matches)
    run = EloRun(config=config, matches=matches)
    if state.get("ratings") != _serialize_elo_ratings(run):
        raise ArtifactPublicationError("Elo rating history conflicts with match state")
    return run


def _deserialize_rated_elo_match(value: object) -> RatedEloMatch:
    match = _object_mapping(value, "rated Elo match")
    return RatedEloMatch(
        match_id=_uuid(match, "match_id"),
        competition_id=_uuid(match, "competition_id"),
        kickoff_at=_datetime(match, "kickoff_at"),
        home_team_id=_uuid(match, "home_team_id"),
        away_team_id=_uuid(match, "away_team_id"),
        home_score=_integer(match, "home_score"),
        away_score=_integer(match, "away_score"),
        home_pre_match_rating=_float(match, "home_pre_match_rating"),
        away_pre_match_rating=_float(match, "away_pre_match_rating"),
        expected_home_score=_float(match, "expected_home_score"),
        actual_home_score=_float(match, "actual_home_score"),
        home_post_match_rating=_float(match, "home_post_match_rating"),
        away_post_match_rating=_float(match, "away_post_match_rating"),
    )


def serialize_dixon_coles_fit(fit: DixonColesFit) -> dict[str, object]:
    if fit.config.sha256 != fit.config_sha256:
        raise ArtifactPublicationError("Dixon-Coles config checksum does not match fitted state")
    return {
        "contract": "DixonColesModelStateV1",
        "model_version": fit.model_version,
        "config": fit.config.to_dict(),
        "config_sha256": fit.config_sha256,
        "training_sha256": fit.training_sha256,
        "training_match_count": fit.training_match_count,
        "training_cutoff": _utc(fit.training_cutoff),
        "negative_log_likelihood": fit.negative_log_likelihood,
        "converged": fit.converged,
        "parameters": {
            "attack_strengths": _uuid_mapping(fit.parameters.attack_strengths),
            "defense_strengths": _uuid_mapping(fit.parameters.defense_strengths),
            "home_advantage": fit.parameters.home_advantage,
            "low_score_correlation": fit.parameters.low_score_correlation,
        },
    }


def serialize_corner_fit(fit: CornerFit) -> dict[str, object]:
    if fit.config.sha256 != fit.config_sha256:
        raise ArtifactPublicationError("corner config checksum does not match fitted state")
    return {
        "contract": "CornerModelStateV1",
        "model_version": fit.model_version,
        "config": fit.config.to_dict(),
        "config_sha256": fit.config_sha256,
        "training_sha256": fit.training_sha256,
        "training_match_count": fit.training_match_count,
        "training_cutoff": _utc(fit.training_cutoff),
        "distribution": fit.distribution,
        "negative_log_likelihood": fit.negative_log_likelihood,
        "aic": fit.aic,
        "converged": fit.converged,
        "parameters": _corner_parameters(fit.parameters),
    }


def deserialize_dixon_coles_fit(state: Mapping[str, object]) -> DixonColesFit:
    if state.get("contract") != "DixonColesModelStateV1":
        raise ArtifactPublicationError("unsupported Dixon-Coles model state")
    config_values = _object_mapping(state.get("config"), "Dixon-Coles config")
    config = DixonColesConfig(
        model_version=_string(config_values, "model_version"),
        time_decay_half_life_days=_optional_float(config_values, "time_decay_half_life_days"),
        score_matrix_tail_start=_integer(config_values, "score_matrix_tail_start"),
        max_iterations=_integer(config_values, "max_iterations"),
        tolerance=_float(config_values, "tolerance"),
    )
    config_sha256 = _string(state, "config_sha256")
    if config.sha256 != config_sha256:
        raise ArtifactPublicationError("Dixon-Coles config checksum mismatch")
    parameters = _object_mapping(state.get("parameters"), "Dixon-Coles parameters")
    return DixonColesFit(
        model_version=_string(state, "model_version"),
        config=config,
        config_sha256=config_sha256,
        training_sha256=_string(state, "training_sha256"),
        training_match_count=_integer(state, "training_match_count"),
        training_cutoff=_datetime(state, "training_cutoff"),
        parameters=DixonColesParameters(
            attack_strengths=_uuid_float_mapping(parameters, "attack_strengths"),
            defense_strengths=_uuid_float_mapping(parameters, "defense_strengths"),
            home_advantage=_float(parameters, "home_advantage"),
            low_score_correlation=_float(parameters, "low_score_correlation"),
        ),
        negative_log_likelihood=_float(state, "negative_log_likelihood"),
        converged=_boolean(state, "converged"),
    )


def deserialize_corner_fit(state: Mapping[str, object]) -> CornerFit:
    if state.get("contract") != "CornerModelStateV1":
        raise ArtifactPublicationError("unsupported corner model state")
    config_values = _object_mapping(state.get("config"), "corner config")
    config = CornerModelConfig(
        model_version=_string(config_values, "model_version"),
        time_decay_half_life_days=_optional_float(config_values, "time_decay_half_life_days"),
        max_iterations=_integer(config_values, "max_iterations"),
        tolerance=_float(config_values, "tolerance"),
    )
    config_sha256 = _string(state, "config_sha256")
    if config.sha256 != config_sha256:
        raise ArtifactPublicationError("corner config checksum mismatch")
    parameters = _object_mapping(state.get("parameters"), "corner parameters")
    distribution_value = _string(state, "distribution")
    if distribution_value not in ("poisson", "negative_binomial"):
        raise ArtifactPublicationError("unsupported corner distribution")
    return CornerFit(
        model_version=_string(state, "model_version"),
        config=config,
        config_sha256=config_sha256,
        training_sha256=_string(state, "training_sha256"),
        training_match_count=_integer(state, "training_match_count"),
        training_cutoff=_datetime(state, "training_cutoff"),
        distribution=cast(CornerDistribution, distribution_value),
        parameters=CornerParameters(
            intercept=_float(parameters, "intercept"),
            team_corner_strengths=_uuid_float_mapping(parameters, "team_corner_strengths"),
            opponent_concession_strengths=_uuid_float_mapping(
                parameters, "opponent_concession_strengths"
            ),
            competition_effects=_uuid_float_mapping(parameters, "competition_effects"),
            home_advantage=_float(parameters, "home_advantage"),
            possession_coefficient=_float(parameters, "possession_coefficient"),
            shot_coefficient=_float(parameters, "shot_coefficient"),
            cross_coefficient=_float(parameters, "cross_coefficient"),
            recent_coefficient=_float(parameters, "recent_coefficient"),
            feature_means=_corner_features(parameters, "feature_means"),
            feature_scales=_corner_features(parameters, "feature_scales"),
            dispersion=_optional_float(parameters, "dispersion"),
        ),
        negative_log_likelihood=_float(state, "negative_log_likelihood"),
        aic=_float(state, "aic"),
        converged=_boolean(state, "converged"),
    )


def _corner_parameters(parameters: CornerParameters) -> dict[str, object]:
    return {
        "intercept": parameters.intercept,
        "team_corner_strengths": _uuid_mapping(parameters.team_corner_strengths),
        "opponent_concession_strengths": _uuid_mapping(parameters.opponent_concession_strengths),
        "competition_effects": _uuid_mapping(parameters.competition_effects),
        "home_advantage": parameters.home_advantage,
        "possession_coefficient": parameters.possession_coefficient,
        "shot_coefficient": parameters.shot_coefficient,
        "cross_coefficient": parameters.cross_coefficient,
        "recent_coefficient": parameters.recent_coefficient,
        "feature_means": parameters.feature_means.values,
        "feature_scales": parameters.feature_scales.values,
        "dispersion": parameters.dispersion,
    }


def _uuid_mapping(values: Mapping[UUID, float]) -> dict[str, float]:
    return {str(key): values[key] for key in sorted(values, key=str)}


def _object_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ArtifactPublicationError(f"{path} must be a JSON object")
    return cast(dict[str, object], value)


def _string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str):
        raise ArtifactPublicationError(f"model state {key} must be a string")
    return value


def _float(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ArtifactPublicationError(f"model state {key} must be finite")
    return float(value)


def _optional_float(values: Mapping[str, object], key: str) -> float | None:
    if values.get(key) is None:
        return None
    return _float(values, key)


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ArtifactPublicationError(f"model state {key} must be an integer")
    return value


def _boolean(values: Mapping[str, object], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ArtifactPublicationError(f"model state {key} must be a boolean")
    return value


def _datetime(values: Mapping[str, object], key: str) -> datetime:
    value = _string(values, key)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ArtifactPublicationError(f"model state {key} must be a timestamp") from error
    _aware(parsed, key)
    return parsed


def _uuid(values: Mapping[str, object], key: str) -> UUID:
    value = _string(values, key)
    try:
        return UUID(value)
    except ValueError as error:
        raise ArtifactPublicationError(f"model state {key} must be a UUID") from error


def _uuid_float_mapping(values: Mapping[str, object], key: str) -> dict[UUID, float]:
    raw = _object_mapping(values.get(key), key)
    parsed: dict[UUID, float] = {}
    for identifier, value in raw.items():
        try:
            parsed[UUID(identifier)] = _float({key: value}, key)
        except ValueError as error:
            raise ArtifactPublicationError(f"model state {key} contains an invalid UUID") from error
    return parsed


def _corner_features(values: Mapping[str, object], key: str) -> CornerFeatures:
    features = _object_mapping(values.get(key), key)
    return CornerFeatures(
        possession_tendency=_float(features, "possession_tendency"),
        shot_rate=_float(features, "shot_rate"),
        cross_rate=_float(features, "cross_rate"),
        recent_corners=_float(features, "recent_corners"),
    )


def _portable_json(value: object, path: str) -> object:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ArtifactPublicationError(f"portable model state contains non-finite {path}")
        return value
    if isinstance(value, Mapping):
        portable: dict[str, object] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise ArtifactPublicationError(
                    f"portable model state contains a non-string key at {path}"
                )
            portable[key] = _portable_json(child, f"{path}.{key}")
        return portable
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_portable_json(child, f"{path}[{index}]") for index, child in enumerate(value)]
    raise ArtifactPublicationError(
        f"portable model state contains unsupported value at {path}: {type(value).__name__}"
    )


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ArtifactPublicationError(f"{field_name} must include a timezone")


def _utc(value: datetime) -> str:
    _aware(value, "timestamp")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
