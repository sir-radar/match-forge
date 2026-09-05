from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.datasets import StatsBombEventDatasetPublisher
from football.forecasting.corner_labels import (
    CornerLabelPublicationResult,
    Sprint2CornerLabelPublisher,
)
from football.forecasting.evidence import Sprint2EvidenceProvenanceV1
from football.forecasting.gate import Sprint2GateService, Sprint2GateSummary
from football.forecasting.kickoff import (
    KickoffClaimPublicationResult,
    Sprint2KickoffClaimPublisher,
)
from football.forecasting.lifecycle import (
    LifecycleClaimPublicationResult,
    Sprint2LifecycleClaimPublisher,
)
from football.ingestion import SourceAcquirer, StatsBombCanonicalIngestor
from football.integrity import (
    IntegrityArtifactKind,
    IntegrityVerificationResult,
    PostgresIntegrityVerifier,
)
from football.providers import (
    FootballDataProvider,
    PostgresProviderObservabilityStoreV1,
    ProviderObservabilitySnapshotV1,
    ProviderSyncPolicyRegistryV1,
)
from football.reports import (
    ReportSource,
    publish_competition_ingestion_report,
    publish_season_ingestion_report,
)
from football.validation import QualityPolicy, StatsBombDatasetValidator


class SeasonLookupError(ValueError):
    """A provider season cannot be resolved to one usable canonical season."""


@dataclass(frozen=True)
class CompetitionIngestionSummary:
    source_snapshot_id: UUID
    competitions: int
    seasons: int
    report_json_path: Path
    report_markdown_path: Path
    report_status: str


@dataclass(frozen=True)
class SeasonIngestionSummary:
    season_id: int
    competition_id: int
    source_snapshot_id: UUID
    matches: int
    events: int
    dataset_version_id: UUID | None
    validation_run_id: UUID | None
    validation_status: str | None
    findings: int
    report_json_path: Path
    report_markdown_path: Path
    report_status: str


@dataclass(frozen=True)
class SeasonValidationSummary:
    season_id: int
    dataset_version_id: UUID
    validation_run_id: UUID
    status: str
    findings: int


@dataclass(frozen=True)
class ProviderStatusSummary:
    snapshot: ProviderObservabilitySnapshotV1
    policy_version: str
    policy_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "policy_sha256": self.policy_sha256,
            "snapshot": self.snapshot.to_dict(),
        }


class FootballApplication:
    def __init__(
        self,
        connection: Connection[Any],
        data_root: Path,
        provider: FootballDataProvider | None,
        quality_policy_path: Path,
        report_root: Path,
        evaluation_provenance: Sprint2EvidenceProvenanceV1 | None = None,
        provider_sync_policies: ProviderSyncPolicyRegistryV1 | None = None,
    ) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()
        self._provider = provider
        self._quality_policy_path = quality_policy_path.resolve()
        self._report_root = report_root.resolve()
        self._evaluation_provenance = evaluation_provenance
        self._provider_sync_policies = provider_sync_policies

    def evaluate_sprint2(self) -> Sprint2GateSummary:
        return Sprint2GateService(
            self._connection,
            self._report_root,
            data_root=self._data_root,
            provenance=self._evaluation_provenance,
        ).evaluate()

    def resolve_sprint2_lifecycle(self) -> LifecycleClaimPublicationResult:
        return Sprint2LifecycleClaimPublisher(self._connection).publish()

    def resolve_sprint2_kickoffs(self) -> KickoffClaimPublicationResult:
        return Sprint2KickoffClaimPublisher(self._connection).publish()

    def resolve_sprint2_corners(self) -> CornerLabelPublicationResult:
        return Sprint2CornerLabelPublisher(self._connection, self._data_root).publish()

    def verify_integrity(
        self, artifact_kind: IntegrityArtifactKind, artifact_id: UUID
    ) -> IntegrityVerificationResult:
        verifier = PostgresIntegrityVerifier(self._connection, self._data_root)
        if artifact_kind == "RAW_RESOURCE":
            return verifier.verify_raw_resource(artifact_id)
        if artifact_kind == "DATASET":
            return verifier.verify_dataset(artifact_id)
        return verifier.verify_model_artifact(artifact_id)

    def provider_status(
        self,
        provider_id: str,
        resource_key: str,
        scope_key: str,
        observed_at: datetime,
    ) -> ProviderStatusSummary:
        if self._provider_sync_policies is None:
            raise ValueError("provider sync policy is unresolved for provider/resource/scope")
        registration = self._provider_sync_policies.resolve(provider_id, resource_key, scope_key)
        with self._connection.cursor() as cursor:
            snapshot = PostgresProviderObservabilityStoreV1().snapshot(
                cursor,
                policies=self._provider_sync_policies,
                provider_id=provider_id,
                resource_key=resource_key,
                scope_key=scope_key,
                observed_at=observed_at,
            )
        return ProviderStatusSummary(
            snapshot=snapshot,
            policy_version=registration.policy_version,
            policy_sha256=registration.policy.sha256,
        )

    def ingest_competitions(self) -> CompetitionIngestionSummary:
        provider = self._require_provider()
        acquisition = SourceAcquirer(self._data_root).acquire(provider, (provider.competitions(),))
        result = StatsBombCanonicalIngestor(self._connection, self._data_root).ingest(acquisition)
        report = publish_competition_ingestion_report(
            self._data_root,
            ReportSource("catalog", acquisition, result.source_snapshot_id),
            result,
        )
        return CompetitionIngestionSummary(
            source_snapshot_id=result.source_snapshot_id,
            competitions=result.competitions_seen,
            seasons=result.seasons_seen,
            report_json_path=report.json_path,
            report_markdown_path=report.markdown_path,
            report_status=report.status,
        )

    def ingest_season(
        self, season_id: int, competition_id: int | None = None
    ) -> SeasonIngestionSummary:
        provider = self._require_provider()
        catalog = SourceAcquirer(self._data_root).acquire(provider, (provider.competitions(),))
        catalog_result = StatsBombCanonicalIngestor(self._connection, self._data_root).ingest(
            catalog
        )
        competition_id = self._competition_for_season(
            catalog_result.source_snapshot_id, season_id, competition_id
        )

        matches_acquisition = SourceAcquirer(self._data_root).acquire(
            provider,
            (provider.matches(competition_id=competition_id, season_id=season_id),),
        )
        matches_result = StatsBombCanonicalIngestor(self._connection, self._data_root).ingest(
            matches_acquisition
        )
        match_ids = self._match_ids(matches_result.source_snapshot_id)
        if not match_ids:
            report = publish_season_ingestion_report(
                self._data_root,
                competition_id=competition_id,
                season_id=season_id,
                sources=(
                    ReportSource("catalog", catalog, catalog_result.source_snapshot_id),
                    ReportSource("matches", matches_acquisition, matches_result.source_snapshot_id),
                ),
                catalog=catalog_result,
                matches=matches_result,
                details=None,
                dataset=None,
                validation=None,
            )
            return SeasonIngestionSummary(
                season_id=season_id,
                competition_id=competition_id,
                source_snapshot_id=matches_result.source_snapshot_id,
                matches=0,
                events=0,
                dataset_version_id=None,
                validation_run_id=None,
                validation_status=None,
                findings=0,
                report_json_path=report.json_path,
                report_markdown_path=report.markdown_path,
                report_status=report.status,
            )

        resources = tuple(
            resource
            for match_id in match_ids
            for resource in (
                provider.lineups(match_id=match_id),
                provider.events(match_id=match_id),
            )
        )
        detail_acquisition = SourceAcquirer(self._data_root).acquire(provider, resources)
        detail_result = StatsBombCanonicalIngestor(self._connection, self._data_root).ingest(
            detail_acquisition
        )
        dataset = StatsBombEventDatasetPublisher(self._connection, self._data_root).publish(
            detail_acquisition
        )
        validation = StatsBombDatasetValidator(
            self._connection,
            self._data_root,
            QualityPolicy.from_path(self._quality_policy_path),
        ).validate(dataset.dataset_version_id)
        report = publish_season_ingestion_report(
            self._data_root,
            competition_id=competition_id,
            season_id=season_id,
            sources=(
                ReportSource("catalog", catalog, catalog_result.source_snapshot_id),
                ReportSource("matches", matches_acquisition, matches_result.source_snapshot_id),
                ReportSource("details", detail_acquisition, detail_result.source_snapshot_id),
            ),
            catalog=catalog_result,
            matches=matches_result,
            details=detail_result,
            dataset=dataset,
            validation=validation,
        )
        return SeasonIngestionSummary(
            season_id=season_id,
            competition_id=competition_id,
            source_snapshot_id=detail_result.source_snapshot_id,
            matches=len(match_ids),
            events=detail_result.events_seen,
            dataset_version_id=dataset.dataset_version_id,
            validation_run_id=validation.validation_run_id,
            validation_status=validation.status,
            findings=len(validation.findings),
            report_json_path=report.json_path,
            report_markdown_path=report.markdown_path,
            report_status=report.status,
        )

    def validate_season(
        self, season_id: int, competition_id: int | None = None
    ) -> SeasonValidationSummary:
        canonical_season_id = self._canonical_season_id(season_id, competition_id)
        dataset_version_id = self._latest_dataset(canonical_season_id, season_id)
        policy = QualityPolicy.from_path(self._quality_policy_path)
        result = StatsBombDatasetValidator(
            self._connection,
            self._data_root,
            policy,
        ).validate(dataset_version_id)
        return SeasonValidationSummary(
            season_id=season_id,
            dataset_version_id=result.dataset_version_id,
            validation_run_id=result.validation_run_id,
            status=result.status,
            findings=len(result.findings),
        )

    def _require_provider(self) -> FootballDataProvider:
        if self._provider is None:
            raise RuntimeError("ingestion provider is not configured")
        return self._provider

    def _competition_for_season(
        self, source_snapshot_id: UUID, season_id: int, competition_id: int | None
    ) -> int:
        if competition_id is not None:
            return competition_id
        with self._connection.cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT provider_competition_id
                FROM football.season_observations
                WHERE source_snapshot_id = %s AND provider_season_id = %s
                ORDER BY provider_competition_id
                """,
                (source_snapshot_id, str(season_id)),
            ).fetchall()
        if not rows:
            raise SeasonLookupError(f"StatsBomb season {season_id} was not found")
        competition_ids = {int(row[0]) for row in rows}
        if len(competition_ids) != 1:
            raise SeasonLookupError(
                f"StatsBomb season {season_id} belongs to multiple competitions"
            )
        return competition_ids.pop()

    def _match_ids(self, source_snapshot_id: UUID) -> tuple[int, ...]:
        with self._connection.cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT provider_match_id
                FROM football.match_observations
                WHERE source_snapshot_id = %s
                ORDER BY provider_match_id::bigint
                """,
                (source_snapshot_id,),
            ).fetchall()
        return tuple(int(row[0]) for row in rows)

    def _canonical_season_id(
        self, provider_season_id: int, provider_competition_id: int | None
    ) -> UUID:
        with self._connection.cursor() as cursor:
            rows = cursor.execute(
                """
                SELECT DISTINCT mapping.season_id
                FROM football.season_provider_mappings AS mapping
                JOIN football.providers AS provider ON provider.id = mapping.provider_id
                WHERE provider.code = 'statsbomb_open_data'
                  AND mapping.provider_season_id = %s
                  AND (%s::text IS NULL OR mapping.provider_competition_id = %s)
                  AND mapping.valid_to IS NULL
                ORDER BY mapping.season_id
                """,
                (
                    str(provider_season_id),
                    str(provider_competition_id) if provider_competition_id else None,
                    str(provider_competition_id) if provider_competition_id else None,
                ),
            ).fetchall()
        if not rows:
            if provider_competition_id is not None:
                raise SeasonLookupError(
                    f"StatsBomb competition {provider_competition_id} season "
                    f"{provider_season_id} is not ingested"
                )
            raise SeasonLookupError(f"StatsBomb season {provider_season_id} is not ingested")
        if len(rows) != 1:
            if provider_competition_id is not None:
                raise SeasonLookupError(
                    f"StatsBomb competition {provider_competition_id} season "
                    f"{provider_season_id} maps to multiple canonical seasons"
                )
            raise SeasonLookupError(
                f"StatsBomb season {provider_season_id} maps to multiple canonical seasons"
            )
        return UUID(str(rows[0][0]))

    def _latest_dataset(self, season_id: UUID, provider_season_id: int) -> UUID:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT DISTINCT dataset.id, snapshot.acquired_at, dataset.published_at
                FROM football.dataset_versions AS dataset
                JOIN football.source_snapshots AS snapshot
                  ON snapshot.id = dataset.source_snapshot_id
                JOIN football.event_observations AS event
                  ON event.source_snapshot_id = dataset.source_snapshot_id
                JOIN football.matches AS match ON match.id = event.match_id
                WHERE dataset.dataset_name = 'events'
                  AND dataset.layer = 'normalized'
                  AND dataset.status = 'published'
                  AND match.season_id = %s
                ORDER BY snapshot.acquired_at DESC, dataset.published_at DESC, dataset.id DESC
                LIMIT 1
                """,
                (season_id,),
            ).fetchone()
        if row is None:
            raise SeasonLookupError(
                f"StatsBomb season {provider_season_id} has no published event dataset"
            )
        return UUID(str(row[0]))
