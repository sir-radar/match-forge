"""Raw response registration and fallback fetchers for the product sync."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from uuid import UUID

from football.product.api_football import (
    ApiResponse,
)
from football.product.domain import (
    stable_id,
)
from football.product.football_data_org import (
    FootballDataOrgError,
    FootballDataResponse,
)
from football.product.identity_crosswalks import FOOTBALL_DATA_COMPETITIONS
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    PROVIDER_CODE,
    ProductSyncBase,
)
from football.storage.raw import ImmutableFileStore, ImmutableWrite


class ProductResponseMixin(ProductSyncBase):
    """Register provider responses as raw snapshots and fetch fallback payloads."""

    def _prepare_response(
        self, provider_code: str, response: ApiResponse | FootballDataResponse
    ) -> ImmutableWrite:
        digest = hashlib.sha256(response.raw).hexdigest()
        relative_path = (
            Path("mvp")
            / provider_code
            / response.fetched_at.strftime("%Y/%m/%d")
            / f"{digest}.json"
        )
        return ImmutableFileStore(self.data_root).publish(str(relative_path), response.raw)

    def _record_response(self, resource_name: str, response: ApiResponse) -> UUID:
        prepared = self._prepare_response(PROVIDER_CODE, response)
        return self._register_response(resource_name, response, prepared)

    def _record_fallback_response(self, resource_name: str, response: FootballDataResponse) -> UUID:
        prepared = self._prepare_response(FALLBACK_PROVIDER_CODE, response)
        return self._register_fallback_response(resource_name, response, prepared)

    def _register_response(
        self, resource_name: str, response: ApiResponse, prepared: ImmutableWrite
    ) -> UUID:
        digest = prepared.sha256
        provider_id = stable_id("provider", PROVIDER_CODE)
        snapshot_id = stable_id("source-snapshot", PROVIDER_CODE, resource_name, digest)
        resource_id = stable_id("source-resource", snapshot_id, resource_name)
        relative_path = prepared.relative_path
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, 'API-Football', 'http_api')
                ON CONFLICT (code) DO NOTHING
                """,
                (provider_id, PROVIDER_CODE),
            )
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, acquired_at,
                    manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    resource_name,
                    digest,
                    response.fetched_at,
                    str(relative_path),
                    digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes,
                    media_type, parse_status, validation_status, acquired_at
                ) VALUES (%s, %s, %s, %s, %s, 'application/json', 'parsed', 'valid', %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                """,
                (
                    resource_id,
                    snapshot_id,
                    response.path.lstrip("/"),
                    digest,
                    len(response.raw),
                    response.fetched_at,
                ),
            )
        return snapshot_id

    def _register_fallback_response(
        self, resource_name: str, response: FootballDataResponse, prepared: ImmutableWrite
    ) -> UUID:
        digest = prepared.sha256
        provider_id = stable_id("provider", FALLBACK_PROVIDER_CODE)
        snapshot_id = stable_id("source-snapshot", FALLBACK_PROVIDER_CODE, resource_name, digest)
        resource_id = stable_id("source-resource", snapshot_id, resource_name)
        relative_path = prepared.relative_path
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, 'football-data.org', 'http_api')
                ON CONFLICT (code) DO NOTHING
                """,
                (provider_id, FALLBACK_PROVIDER_CODE),
            )
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, acquired_at,
                    manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    resource_name,
                    digest,
                    response.fetched_at,
                    str(relative_path),
                    digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes,
                    media_type, parse_status, validation_status, acquired_at
                ) VALUES (%s, %s, %s, %s, %s, 'application/json', 'parsed', 'valid', %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                """,
                (
                    resource_id,
                    snapshot_id,
                    response.path.lstrip("/"),
                    digest,
                    len(response.raw),
                    response.fetched_at,
                ),
            )
        return snapshot_id

    def _fallback_history(self, league_id: int, season: int) -> FootballDataResponse | None:
        competition_code = FOOTBALL_DATA_COMPETITIONS.get(league_id)
        if self.history_fallback is None or competition_code is None:
            return None
        return self.history_fallback.finished_matches(competition_code, season)

    def _fallback_fixtures(self, requested_date: date) -> FootballDataResponse | None:
        if self.history_fallback is None:
            return None
        try:
            return self.history_fallback.fixtures_for_date(requested_date)
        except FootballDataOrgError:
            return None

    def _fallback_standings(self, league_id: int, season: int) -> FootballDataResponse | None:
        competition_code = FOOTBALL_DATA_COMPETITIONS.get(league_id)
        if self.history_fallback is None or competition_code is None:
            return None
        return self.history_fallback.standings(competition_code, season)
