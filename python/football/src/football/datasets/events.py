from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection, Cursor

from football.contracts.dependencies import DependencyNodeV1
from football.contracts.source import canonical_json_bytes
from football.datasets.contracts import DatasetManifest, DatasetManifestFile
from football.ingestion.acquisition import AcquisitionResult
from football.ingestion.dependencies import PostgresDependencyStoreV1
from football.ingestion.registration import VerifiedSource, verify_acquisition
from football.normalization.statsbomb_events import (
    EVENT_SCHEMA_SHA256,
    EVENT_SCHEMA_VERSION,
    NORMALIZER_VERSION,
    CanonicalEventReference,
    logical_sha256,
    normalize_statsbomb_events,
)
from football.storage.parquet import ImmutableEventParquetStore, PublishedParquetFile
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore

_EVENT_PATH = re.compile(r"^data/events/([1-9][0-9]*)\.json$")
_DATASET_NAMESPACE = UUID("6f57ba57-984c-4c42-877d-d355561742ea")


class DatasetPublicationError(RuntimeError):
    """Normalized dataset cannot be safely published or registered."""


@dataclass(frozen=True)
class EventDatasetPublicationResult:
    dataset_version_id: UUID
    source_snapshot_id: UUID
    manifest_path: Path
    manifest_sha256: str
    files: tuple[PublishedParquetFile, ...]
    status: str


@dataclass(frozen=True)
class _RegisteredSource:
    provider_id: UUID
    snapshot_id: UUID
    resource_ids: dict[str, UUID]


@dataclass(frozen=True)
class _MatchContext:
    provider_match_id: str
    canonical_competition_id: UUID
    canonical_season_id: UUID
    canonical_match_id: UUID
    source_path: str
    source_resource_id: UUID
    references: dict[str, CanonicalEventReference]


@dataclass(frozen=True)
class _PreparedMatch:
    context: _MatchContext
    rows: tuple[dict[str, Any], ...]
    logical_sha256: str


class StatsBombEventDatasetPublisher:
    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()

    def publish(self, acquisition: AcquisitionResult) -> EventDatasetPublicationResult:
        source = verify_acquisition(self._data_root, acquisition)
        event_paths = _event_paths(source)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            registered = _resolve_registered_source(cursor, source, event_paths)
            team_mappings = _entity_mappings(cursor, registered.provider_id, "team")
            player_mappings = _entity_mappings(cursor, registered.provider_id, "player")
            contexts = tuple(
                _match_context(cursor, registered, path, provider_match_id)
                for path, provider_match_id in event_paths
            )
        prepared = tuple(
            _prepare_match(source, context, team_mappings, player_mappings) for context in contexts
        )
        identity_hash = _identity_hash(source, prepared)
        dataset_id = uuid5(_DATASET_NAMESPACE, identity_hash)
        files = self._publish_files(dataset_id, prepared)
        manifest_path, manifest_sha256, manifest_status = self._publish_manifest(
            source,
            dataset_id,
            files,
        )
        with self._connection.transaction(), self._connection.cursor() as cursor:
            _register_dataset(
                cursor,
                registered,
                dataset_id,
                identity_hash,
                manifest_path.relative_to(self._data_root).as_posix(),
                manifest_sha256,
                files,
            )
        status = (
            "published"
            if manifest_status == "acquired" or any(file.status == "published" for file in files)
            else "verified_published"
        )
        return EventDatasetPublicationResult(
            dataset_version_id=dataset_id,
            source_snapshot_id=registered.snapshot_id,
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha256,
            files=files,
            status=status,
        )

    def _publish_files(
        self,
        dataset_id: UUID,
        prepared: tuple[_PreparedMatch, ...],
    ) -> tuple[PublishedParquetFile, ...]:
        store = ImmutableEventParquetStore(self._data_root)
        return tuple(
            store.publish(_dataset_path(dataset_id, match.context), match.rows)
            for match in prepared
        )

    def _publish_manifest(
        self,
        source: VerifiedSource,
        dataset_id: UUID,
        files: tuple[PublishedParquetFile, ...],
    ) -> tuple[Path, str, str]:
        manifest = DatasetManifest(
            dataset_version_id=dataset_id,
            dataset_name="events",
            schema_version=EVENT_SCHEMA_VERSION,
            schema_sha256=EVENT_SCHEMA_SHA256,
            source_git_sha=source.manifest.snapshot.source_git_sha,
            normalizer_version=NORMALIZER_VERSION,
            files=tuple(
                DatasetManifestFile(
                    relative_path=file.relative_path,
                    row_count=file.row_count,
                    size_bytes=file.size_bytes,
                    physical_sha256=file.physical_sha256,
                    logical_sha256=file.logical_sha256,
                )
                for file in files
            ),
        )
        relative_path = f"manifests/datasets/dataset={dataset_id}/dataset-manifest-v1.json"
        try:
            published = ImmutableFileStore(self._data_root).publish(
                relative_path,
                manifest.to_bytes(),
            )
        except ImmutableFileConflict as error:
            raise DatasetPublicationError(
                f"immutable dataset manifest conflicts: {relative_path}"
            ) from error
        return published.path, published.sha256, published.status


def _event_paths(source: VerifiedSource) -> tuple[tuple[str, str], ...]:
    paths = tuple(
        (path, match.group(1))
        for path in sorted(source.payloads)
        if (match := _EVENT_PATH.fullmatch(path)) is not None
    )
    if not paths:
        raise DatasetPublicationError("source manifest has no StatsBomb event resources")
    return paths


def _resolve_registered_source(
    cursor: Cursor[Any],
    source: VerifiedSource,
    event_paths: tuple[tuple[str, str], ...],
) -> _RegisteredSource:
    source_identity = source.manifest_path.rsplit("/", 1)[0]
    row = cursor.execute(
        """
        SELECT provider.id, snapshot.id, snapshot.acquired_at,
               snapshot.manifest_path, snapshot.manifest_sha256
        FROM football.providers AS provider
        JOIN football.source_snapshots AS snapshot ON snapshot.provider_id = provider.id
        WHERE provider.code = %s AND snapshot.source_identity = %s
          AND snapshot.source_revision = %s
        """,
        (
            source.manifest.snapshot.provider,
            source_identity,
            source.manifest.snapshot.source_git_sha,
        ),
    ).fetchone()
    expected = (
        source.manifest.acquired_at,
        source.manifest_path,
        source.manifest_sha256,
    )
    if row is None or row[2:] != expected:
        raise DatasetPublicationError(
            "dataset publication requires a registered canonical source snapshot"
        )
    provider_id = UUID(str(row[0]))
    snapshot_id = UUID(str(row[1]))
    resources = list(
        cursor.execute(
            """
            SELECT id, provider_path, sha256, size_bytes, media_type,
                   parse_status, validation_status, acquired_at
            FROM football.source_resources
            WHERE source_snapshot_id = %s AND provider_path = ANY(%s)
            ORDER BY provider_path
            """,
            (snapshot_id, [resource.path for resource in source.manifest.resources]),
        )
    )
    manifest_resources = {resource.path: resource for resource in source.manifest.resources}
    event_path_set = {path for path, _match_id in event_paths}
    resources_match = all(
        resource[1] in manifest_resources
        and resource[2:5]
        == (
            manifest_resources[str(resource[1])].sha256,
            manifest_resources[str(resource[1])].size_bytes,
            manifest_resources[str(resource[1])].media_type,
        )
        and resource[7] == source.manifest.acquired_at
        and (
            resource[1] not in event_path_set
            or (resource[5] == "parsed" and resource[6] in ("valid", "warnings"))
        )
        for resource in resources
    )
    if len(resources) != len(source.manifest.resources) or not resources_match:
        raise DatasetPublicationError(
            "dataset publication requires the registered source scope and parsed event resources"
        )
    resource_ids = {str(resource[1]): UUID(str(resource[0])) for resource in resources}
    return _RegisteredSource(provider_id, snapshot_id, resource_ids)


def _entity_mappings(cursor: Cursor[Any], provider_id: UUID, entity: str) -> dict[str, UUID]:
    if entity == "team":
        rows = cursor.execute(
            """
            SELECT provider_team_id, team_id FROM football.team_provider_mappings
            WHERE provider_id = %s AND valid_to IS NULL
            """,
            (provider_id,),
        )
    elif entity == "player":
        rows = cursor.execute(
            """
            SELECT provider_player_id, player_id FROM football.player_provider_mappings
            WHERE provider_id = %s AND valid_to IS NULL
            """,
            (provider_id,),
        )
    else:
        raise AssertionError(entity)
    return {str(row[0]): UUID(str(row[1])) for row in rows}


def _match_context(
    cursor: Cursor[Any],
    source: _RegisteredSource,
    source_path: str,
    provider_match_id: str,
) -> _MatchContext:
    match_row = cursor.execute(
        """
        SELECT mapping.match_id, match.competition_id, match.season_id
        FROM football.match_provider_mappings AS mapping
        JOIN football.matches AS match ON match.id = mapping.match_id
        WHERE mapping.provider_id = %s AND mapping.provider_match_id = %s
          AND mapping.valid_to IS NULL
        """,
        (source.provider_id, provider_match_id),
    ).fetchone()
    if match_row is None:
        raise DatasetPublicationError(
            f"canonical match mapping is missing for event resource {source_path}"
        )
    canonical_match_id = UUID(str(match_row[0]))
    event_rows = list(
        cursor.execute(
            """
            SELECT event_id, match_id, provider_event_id, event_index,
                   provider_event_type, period, event_clock, team_id, player_id
            FROM football.event_observations
            WHERE source_snapshot_id = %s AND source_resource_id = %s
              AND provider_id = %s AND provider_match_id = %s
            ORDER BY event_index
            """,
            (
                source.snapshot_id,
                source.resource_ids[source_path],
                source.provider_id,
                provider_match_id,
            ),
        )
    )
    references: dict[str, CanonicalEventReference] = {}
    for row in event_rows:
        if UUID(str(row[1])) != canonical_match_id:
            raise DatasetPublicationError(
                f"event catalogue match conflicts for event resource {source_path}"
            )
        reference = CanonicalEventReference(
            canonical_event_id=UUID(str(row[0])),
            canonical_match_id=canonical_match_id,
            provider_event_id=str(row[2]),
            event_index=int(row[3]),
            provider_event_type=str(row[4]),
            period=int(row[5]),
            event_clock=row[6],
            canonical_team_id=UUID(str(row[7])) if row[7] is not None else None,
            canonical_player_id=UUID(str(row[8])) if row[8] is not None else None,
        )
        references[reference.provider_event_id] = reference
    return _MatchContext(
        provider_match_id=provider_match_id,
        canonical_competition_id=UUID(str(match_row[1])),
        canonical_season_id=UUID(str(match_row[2])),
        canonical_match_id=canonical_match_id,
        source_path=source_path,
        source_resource_id=source.resource_ids[source_path],
        references=references,
    )


def _prepare_match(
    source: VerifiedSource,
    context: _MatchContext,
    team_mappings: dict[str, UUID],
    player_mappings: dict[str, UUID],
) -> _PreparedMatch:
    rows = normalize_statsbomb_events(
        source.payloads[context.source_path],
        context.provider_match_id,
        context.references,
        team_mappings,
        player_mappings,
    )
    return _PreparedMatch(context, rows, logical_sha256(rows))


def _identity_hash(source: VerifiedSource, prepared: tuple[_PreparedMatch, ...]) -> str:
    identity = {
        "dataset_name": "events",
        "layer": "normalized",
        "schema_version": EVENT_SCHEMA_VERSION,
        "schema_sha256": EVENT_SCHEMA_SHA256,
        "normalizer_version": NORMALIZER_VERSION,
        "provider": source.manifest.snapshot.provider,
        "source_revision": source.manifest.snapshot.source_git_sha,
        "source_scope": [
            {
                "path": resource.path,
                "sha256": resource.sha256,
                "size_bytes": resource.size_bytes,
                "media_type": resource.media_type,
            }
            for resource in sorted(source.manifest.resources, key=lambda item: item.path)
        ],
        "matches": [
            {
                "provider_match_id": match.context.provider_match_id,
                "canonical_competition_id": str(match.context.canonical_competition_id),
                "canonical_season_id": str(match.context.canonical_season_id),
                "canonical_match_id": str(match.context.canonical_match_id),
                "logical_sha256": match.logical_sha256,
            }
            for match in prepared
        ],
    }
    return hashlib.sha256(canonical_json_bytes(identity)).hexdigest()


def _dataset_path(dataset_id: UUID, context: _MatchContext) -> str:
    return (
        f"normalized/events/schema={EVENT_SCHEMA_VERSION}/dataset={dataset_id}/"
        f"competition_id={context.canonical_competition_id}/"
        f"season_id={context.canonical_season_id}/match_id={context.canonical_match_id}/"
        "events.parquet"
    )


def _register_dataset(
    cursor: Cursor[Any],
    source: _RegisteredSource,
    dataset_id: UUID,
    identity_hash: str,
    manifest_path: str,
    manifest_sha256: str,
    files: tuple[PublishedParquetFile, ...],
) -> None:
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"dataset:{identity_hash}",),
    )
    published_at = datetime.now(UTC)
    cursor.execute(
        """
        INSERT INTO football.dataset_versions
            (id, source_snapshot_id, dataset_name, layer, identity_hash,
             schema_version, schema_sha256, normalizer_version, manifest_path,
             manifest_sha256, status, published_at)
        VALUES (%s, %s, 'events', 'normalized', %s, %s, %s, %s, %s, %s,
                'published', %s)
        ON CONFLICT (identity_hash) DO NOTHING
        """,
        (
            dataset_id,
            source.snapshot_id,
            identity_hash,
            EVENT_SCHEMA_VERSION,
            EVENT_SCHEMA_SHA256,
            NORMALIZER_VERSION,
            manifest_path,
            manifest_sha256,
            published_at,
        ),
    )
    version = cursor.execute(
        """
        SELECT id, source_snapshot_id, dataset_name, layer, schema_version,
               schema_sha256, normalizer_version, manifest_path, manifest_sha256, status
        FROM football.dataset_versions WHERE identity_hash = %s
        """,
        (identity_hash,),
    ).fetchone()
    expected_version = (
        dataset_id,
        source.snapshot_id,
        "events",
        "normalized",
        EVENT_SCHEMA_VERSION,
        EVENT_SCHEMA_SHA256,
        NORMALIZER_VERSION,
        manifest_path,
        manifest_sha256,
        "published",
    )
    if version != expected_version:
        raise DatasetPublicationError("dataset version conflicts with immutable registration")
    for source_resource_id in source.resource_ids.values():
        cursor.execute(
            """
            INSERT INTO football.dataset_inputs
                (dataset_version_id, source_snapshot_id, source_resource_id, input_role)
            VALUES (%s, %s, %s, 'source')
            ON CONFLICT (dataset_version_id, source_resource_id) DO NOTHING
            """,
            (dataset_id, source.snapshot_id, source_resource_id),
        )
    _register_files(cursor, dataset_id, files)
    _verify_registration(cursor, dataset_id, source, files)
    dependency_store = PostgresDependencyStoreV1()
    dataset = DependencyNodeV1("DATASET", dataset_id)
    for source_resource_id in source.resource_ids.values():
        dependency_store.register_dependency(
            cursor,
            upstream=DependencyNodeV1("SOURCE_RESOURCE", source_resource_id),
            relationship="INPUT_TO",
            downstream=dataset,
        )


def _register_files(
    cursor: Cursor[Any],
    dataset_id: UUID,
    files: tuple[PublishedParquetFile, ...],
) -> None:
    for file in files:
        cursor.execute(
            """
            INSERT INTO football.dataset_files
                (dataset_version_id, relative_path, physical_sha256, logical_sha256,
                 row_count, size_bytes, schema_sha256)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dataset_version_id, relative_path) DO NOTHING
            """,
            (
                dataset_id,
                file.relative_path,
                file.physical_sha256,
                file.logical_sha256,
                file.row_count,
                file.size_bytes,
                EVENT_SCHEMA_SHA256,
            ),
        )


def _verify_registration(
    cursor: Cursor[Any],
    dataset_id: UUID,
    source: _RegisteredSource,
    files: tuple[PublishedParquetFile, ...],
) -> None:
    inputs = {
        UUID(str(row[0]))
        for row in cursor.execute(
            "SELECT source_resource_id FROM football.dataset_inputs WHERE dataset_version_id = %s",
            (dataset_id,),
        )
    }
    if inputs != set(source.resource_ids.values()):
        raise DatasetPublicationError("dataset inputs conflict with immutable registration")
    rows = list(
        cursor.execute(
            """
            SELECT relative_path, physical_sha256, logical_sha256,
                   row_count, size_bytes, schema_sha256
            FROM football.dataset_files WHERE dataset_version_id = %s
            ORDER BY relative_path
            """,
            (dataset_id,),
        )
    )
    expected = sorted(
        (
            file.relative_path,
            file.physical_sha256,
            file.logical_sha256,
            file.row_count,
            file.size_bytes,
            EVENT_SCHEMA_SHA256,
        )
        for file in files
    )
    if rows != expected:
        raise DatasetPublicationError("dataset files conflict with immutable registration")
