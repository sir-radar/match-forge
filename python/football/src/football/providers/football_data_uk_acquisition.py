from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from football.contracts.source import SourceResource
from football.providers.football_data_uk import (
    FootballDataUkAdapter,
    FootballDataUkResourceTypeV1,
    FootballDataUkSourceResourceV1,
)
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1
from football.storage.raw import ImmutableWrite


class FootballDataUkAcquisitionError(ValueError):
    """A bounded Football-Data acquisition cannot establish source evidence."""


@dataclass(frozen=True, slots=True)
class FootballDataUkAcquiredResourceV1:
    receipt: FootballDataUkSourceResourceV1
    raw_write: ImmutableWrite


@dataclass(frozen=True, slots=True)
class FootballDataUkAcquisitionResultV1:
    resources: tuple[FootballDataUkAcquiredResourceV1, ...]


class FootballDataUkAcquirerV1:
    """Acquire the exact frozen provider corpus before any parsing or normalization."""

    def __init__(
        self,
        adapter: FootballDataUkAdapter,
        raw_store: FootballDataUkRawStoreV1,
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._adapter = adapter
        self._raw_store = raw_store
        self._clock = clock

    def acquire(self) -> FootballDataUkAcquisitionResultV1:
        resources = tuple(
            self._acquire_resource(resource) for resource in self._adapter.frozen_resources()
        )
        return FootballDataUkAcquisitionResultV1(resources=resources)

    def _acquire_resource(self, resource: SourceResource) -> FootballDataUkAcquiredResourceV1:
        request_started_at = self._now()
        response = self._adapter.fetch_with_metadata(resource)
        observed_at = self._now()
        receipt = FootballDataUkSourceResourceV1.from_payload(
            resource_type=_resource_type(resource.path),
            source_path=resource.path,
            payload=response.payload,
            request_started_at=request_started_at,
            observed_by_matchforge_at=observed_at,
            http_status=response.status,
            content_type=response.content_type,
            http_etag=response.etag,
            http_last_modified=response.last_modified,
        )
        return FootballDataUkAcquiredResourceV1(
            receipt=receipt,
            raw_write=self._raw_store.publish(receipt, response.payload),
        )

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise FootballDataUkAcquisitionError(
                "acquisition clock must return a timezone-aware time"
            )
        return value


def _resource_type(path: str) -> FootballDataUkResourceTypeV1:
    return "schema_semantics_and_attribution" if path == "notes.txt" else "historical_league_csv"
