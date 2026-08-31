from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection, Cursor

from football.forecasting.contracts import BaselineForecastV1, forecast_payload_bytes
from football.storage.raw import ImmutableFileStore

ForecastPublicationStatus = Literal["published", "verified_existing"]


class ForecastPublicationError(RuntimeError):
    """Forecast bytes or registry rows conflict with immutable published state."""


@dataclass(frozen=True, slots=True)
class PublishedBaselineForecastV1:
    forecast: BaselineForecastV1
    relative_path: str
    physical_sha256: str
    size_bytes: int
    published_at: datetime
    status: ForecastPublicationStatus


class ImmutableForecastStore:
    def __init__(self, data_root: Path) -> None:
        self._files = ImmutableFileStore(data_root)

    def publish(
        self, forecast: BaselineForecastV1, published_at: datetime
    ) -> PublishedBaselineForecastV1:
        _aware(published_at, "published_at")
        cutoff = forecast.prediction_cutoff.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        relative_path = (
            f"forecasts/match={forecast.match_id}/cutoff={cutoff}/"
            f"variant={forecast.probability_variant.lower()}/forecast={forecast.forecast_id}.json"
        )
        write = self._files.publish(
            relative_path,
            forecast_payload_bytes(
                forecast.match_result,
                goal=forecast.goal,
                corners=forecast.corners,
            ),
        )
        if write.sha256 != forecast.payload_sha256:
            raise ForecastPublicationError("published payload checksum does not match forecast")
        return PublishedBaselineForecastV1(
            forecast=forecast,
            relative_path=write.relative_path,
            physical_sha256=write.sha256,
            size_bytes=write.size_bytes,
            published_at=published_at,
            status="published" if write.status == "acquired" else "verified_existing",
        )


class PostgresForecastRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register(self, publication: PublishedBaselineForecastV1) -> ForecastPublicationStatus:
        forecast = publication.forecast
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"baseline-forecast:{forecast.semantic_sha256}",),
            )
            inserted = self._register_forecast(cursor, publication)
            for artifact_id in forecast.model_artifact_ids:
                inserted += self._register_artifact(
                    cursor, forecast.forecast_id, artifact_id, "PRIMARY"
                )
            if forecast.calibrator_artifact_id is not None:
                inserted += self._register_artifact(
                    cursor,
                    forecast.forecast_id,
                    forecast.calibrator_artifact_id,
                    "CALIBRATOR",
                )
        return "published" if inserted else "verified_existing"

    @staticmethod
    def _register_forecast(cursor: Cursor[Any], publication: PublishedBaselineForecastV1) -> int:
        forecast = publication.forecast
        scope = forecast.scope
        inserted = cursor.execute(
            """
            INSERT INTO football.baseline_forecasts
                (id, semantic_sha256, match_id, prediction_cutoff, dataset_version_id,
                 source_snapshot_id, feature_set_version, probability_variant,
                 payload_path, payload_sha256, target_set_sha256, knowledge_cutoff,
                 knowledge_mode, quality_policy_sha256, forecast_context_sha256,
                 probability_contract_version, output_version, status, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, 'published', %s)
            ON CONFLICT (semantic_sha256) DO NOTHING
            """,
            (
                forecast.forecast_id,
                forecast.semantic_sha256,
                forecast.match_id,
                forecast.prediction_cutoff,
                scope.dataset_version_id,
                scope.source_snapshot_id,
                scope.feature_set_version,
                forecast.probability_variant,
                publication.relative_path,
                forecast.payload_sha256,
                scope.target_set_sha256,
                scope.knowledge_cutoff,
                scope.knowledge_mode,
                scope.quality_policy_sha256,
                forecast.forecast_context_sha256,
                forecast.probability_contract_version,
                forecast.output_version,
                publication.published_at,
            ),
        ).rowcount
        row = cursor.execute(
            """
            SELECT id, semantic_sha256, match_id, prediction_cutoff, dataset_version_id,
                   source_snapshot_id, feature_set_version, probability_variant,
                   payload_path, payload_sha256, target_set_sha256, knowledge_cutoff,
                   knowledge_mode, quality_policy_sha256, forecast_context_sha256,
                   probability_contract_version, output_version, status, published_at
            FROM football.baseline_forecasts WHERE semantic_sha256 = %s
            """,
            (forecast.semantic_sha256,),
        ).fetchone()
        expected = (
            forecast.forecast_id,
            forecast.semantic_sha256,
            forecast.match_id,
            forecast.prediction_cutoff,
            scope.dataset_version_id,
            scope.source_snapshot_id,
            scope.feature_set_version,
            forecast.probability_variant,
            publication.relative_path,
            forecast.payload_sha256,
            scope.target_set_sha256,
            scope.knowledge_cutoff,
            scope.knowledge_mode,
            scope.quality_policy_sha256,
            forecast.forecast_context_sha256,
            forecast.probability_contract_version,
            forecast.output_version,
            "published",
            publication.published_at,
        )
        if row != expected:
            raise ForecastPublicationError(
                f"forecast conflicts with registered semantics: {forecast.semantic_sha256}"
            )
        return inserted

    @staticmethod
    def _register_artifact(
        cursor: Cursor[Any],
        forecast_id: UUID,
        artifact_id: UUID,
        role: Literal["PRIMARY", "CALIBRATOR"],
    ) -> int:
        inserted = cursor.execute(
            """
            INSERT INTO football.forecast_artifacts
                (forecast_id, model_artifact_id, artifact_role)
            VALUES (%s, %s, %s)
            ON CONFLICT (forecast_id, model_artifact_id) DO NOTHING
            """,
            (forecast_id, artifact_id, role),
        ).rowcount
        row = cursor.execute(
            """
            SELECT artifact_role FROM football.forecast_artifacts
            WHERE forecast_id = %s AND model_artifact_id = %s
            """,
            (forecast_id, artifact_id),
        ).fetchone()
        if row != (role,):
            raise ForecastPublicationError(
                f"forecast artifact role conflicts with registry: {forecast_id} {artifact_id}"
            )
        return inserted


class BaselineForecastPublisher:
    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._store = ImmutableForecastStore(data_root)

    def publish(
        self, forecast: BaselineForecastV1, published_at: datetime
    ) -> PublishedBaselineForecastV1:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"baseline-forecast:{forecast.semantic_sha256}",),
            )
            existing = cursor.execute(
                """
                SELECT id, published_at FROM football.baseline_forecasts
                WHERE semantic_sha256 = %s
                """,
                (forecast.semantic_sha256,),
            ).fetchone()
            resolved_forecast = forecast
            resolved_published_at = published_at
            if existing is not None:
                resolved_forecast = replace(forecast, forecast_id=UUID(str(existing[0])))
                resolved_published_at = existing[1]
            publication = self._store.publish(resolved_forecast, resolved_published_at)
            inserted = PostgresForecastRegistry._register_forecast(cursor, publication)
            for artifact_id in resolved_forecast.model_artifact_ids:
                inserted += PostgresForecastRegistry._register_artifact(
                    cursor, resolved_forecast.forecast_id, artifact_id, "PRIMARY"
                )
            if resolved_forecast.calibrator_artifact_id is not None:
                inserted += PostgresForecastRegistry._register_artifact(
                    cursor,
                    resolved_forecast.forecast_id,
                    resolved_forecast.calibrator_artifact_id,
                    "CALIBRATOR",
                )
        if publication.status == "verified_existing" and not inserted:
            return publication
        return PublishedBaselineForecastV1(
            forecast=publication.forecast,
            relative_path=publication.relative_path,
            physical_sha256=publication.physical_sha256,
            size_bytes=publication.size_bytes,
            published_at=publication.published_at,
            status="published",
        )


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ForecastPublicationError(f"{field_name} must include a timezone")
