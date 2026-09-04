from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from football.contracts.source import SHA256_PATTERN, SourceResource, sha256_bytes
from football.providers.base import (
    HttpResponseV1,
    HttpTransport,
    ProviderConfigurationError,
    UrllibHttpTransport,
)
from football.providers.capabilities import (
    ProviderCapabilityV1,
    ProviderResourceCapabilityV1,
    ProviderScopeV1,
)
from football.providers.schema_contract import ProviderResourceContractV1

_CSV_PATH_PATTERN = re.compile(r"^mmz4281/(1516|2526)/E0\.csv$")
_NOTES_PATH = "notes.txt"

FootballDataUkResourceTypeV1 = Literal["schema_semantics_and_attribution", "historical_league_csv"]
_ResourceMetadata = tuple[str | None, str | None, str]
_RESOURCE_METADATA: dict[tuple[FootballDataUkResourceTypeV1, str], _ResourceMetadata] = {
    ("schema_semantics_and_attribution", _NOTES_PATH): (None, None, "FootballDataUkNotesV1"),
    ("historical_league_csv", "mmz4281/2526/E0.csv"): (
        "E0",
        "2526",
        "FootballDataUkHistoricalLeagueCsvV1",
    ),
    ("historical_league_csv", "mmz4281/1516/E0.csv"): (
        "E0",
        "1516",
        "FootballDataUkHistoricalLeagueCsvV1",
    ),
}


class FootballDataUkSourceResourceError(ValueError):
    """A frozen Football-Data source resource lacks trustworthy lineage."""


@dataclass(frozen=True, slots=True)
class FootballDataUkSourceResourceV1:
    """Content-addressed source evidence for one Phase 1B provider resource."""

    resource_type: FootballDataUkResourceTypeV1
    source_path: str
    observed_by_matchforge_at: datetime
    http_status: int
    content_type: str
    raw_byte_size: int
    raw_sha256: str
    request_started_at: datetime | None = None
    http_etag: str | None = None
    http_last_modified: str | None = None
    provider_id: str = field(default="football_data_uk", init=False)
    source_host: str = field(default="www.football-data.co.uk", init=False)
    provider_schema_version: None = field(default=None, init=False)
    adapter_version: str = field(default="football-data-uk-v1", init=False)
    parser_version: str = field(default="football-data-uk-csv-parser-v1", init=False)
    normalizer_version: str = field(default="football-data-uk-normalizer-v1", init=False)
    contract: str = "FootballDataUkSourceResourceV1"

    def __post_init__(self) -> None:
        if self.contract != "FootballDataUkSourceResourceV1":
            raise FootballDataUkSourceResourceError("unsupported source resource contract")
        if (self.resource_type, self.source_path) not in _RESOURCE_METADATA:
            raise FootballDataUkSourceResourceError(
                "resource is outside the frozen Phase 1B corpus"
            )
        observed_at = self.observed_by_matchforge_at
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise FootballDataUkSourceResourceError("observed time must include a timezone")
        request_started_at = self.request_started_at or observed_at
        if request_started_at.tzinfo is None or request_started_at.utcoffset() is None:
            raise FootballDataUkSourceResourceError("request start time must include a timezone")
        if request_started_at > observed_at:
            raise FootballDataUkSourceResourceError("request start time follows observation time")
        object.__setattr__(self, "request_started_at", request_started_at)
        if self.http_status != 200 or not self.content_type:
            raise FootballDataUkSourceResourceError(
                "successful source acquisition requires HTTP 200 and content type"
            )
        if self.raw_byte_size <= 0:
            raise FootballDataUkSourceResourceError("raw byte size must be positive")
        if not SHA256_PATTERN.fullmatch(self.raw_sha256):
            raise FootballDataUkSourceResourceError("raw SHA-256 is invalid")
        metadata = (self.http_etag, self.http_last_modified)
        if any(value == "" for value in metadata if value is not None):
            raise FootballDataUkSourceResourceError("HTTP metadata must not be empty when present")

    @classmethod
    def from_payload(
        cls,
        *,
        resource_type: FootballDataUkResourceTypeV1,
        source_path: str,
        payload: bytes,
        observed_by_matchforge_at: datetime,
        request_started_at: datetime | None = None,
        http_status: int,
        content_type: str,
        http_etag: str | None = None,
        http_last_modified: str | None = None,
    ) -> FootballDataUkSourceResourceV1:
        return cls(
            resource_type=resource_type,
            source_path=source_path,
            observed_by_matchforge_at=observed_by_matchforge_at,
            request_started_at=request_started_at,
            http_status=http_status,
            content_type=content_type,
            raw_byte_size=len(payload),
            raw_sha256=sha256_bytes(payload),
            http_etag=http_etag,
            http_last_modified=http_last_modified,
        )

    @property
    def resource_identity(self) -> str:
        return f"{self.provider_id}/{self.source_path}/sha256/{self.raw_sha256}"

    @property
    def provider_competition_code(self) -> str | None:
        return _RESOURCE_METADATA[(self.resource_type, self.source_path)][0]

    @property
    def provider_season_code(self) -> str | None:
        return _RESOURCE_METADATA[(self.resource_type, self.source_path)][1]

    @property
    def provider_resource_contract_version(self) -> str:
        return _RESOURCE_METADATA[(self.resource_type, self.source_path)][2]

    @property
    def knowledge_mode(self) -> Literal["retrospective"]:
        return "retrospective"

    @property
    def known_from(self) -> datetime:
        return self.observed_by_matchforge_at

    @property
    def historical_provider_known_at(self) -> None:
        return None

    def to_dict(self) -> dict[str, object]:
        request_started_at = self.request_started_at
        if request_started_at is None:
            raise AssertionError("validated source receipt lacks request start time")
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "resource_type": self.resource_type,
            "source_host": self.source_host,
            "source_path": self.source_path,
            "provider_competition_code": self.provider_competition_code,
            "provider_season_code": self.provider_season_code,
            "observed_by_matchforge_at": self.observed_by_matchforge_at.isoformat(),
            "request_started_at": request_started_at.isoformat(),
            "http_status": self.http_status,
            "content_type": self.content_type,
            "http_etag": self.http_etag,
            "http_last_modified": self.http_last_modified,
            "raw_byte_size": self.raw_byte_size,
            "raw_sha256": self.raw_sha256,
            "provider_schema_version": self.provider_schema_version,
            "provider_resource_contract_version": self.provider_resource_contract_version,
            "adapter_version": self.adapter_version,
            "parser_version": self.parser_version,
            "normalizer_version": self.normalizer_version,
            "knowledge_mode": self.knowledge_mode,
        }


FootballDataUkHistoricalLeagueCsvV1 = ProviderResourceContractV1(
    provider_id="football_data_uk",
    resource="historical_league_csv",
    schema_version="FootballDataUkHistoricalLeagueCsvV1",
    adapter_version="football-data-uk-v1",
    parser_version="football-data-uk-csv-parser-v1",
    normalizer_version="football-data-uk-normalizer-v1",
    required_fields=(
        "Div",
        "Date",
        "HomeTeam",
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "HTHG",
        "HTAG",
        "HTR",
    ),
    optional_fields=(
        "Time",
        "Referee",
        "HS",
        "AS",
        "HST",
        "AST",
        "HC",
        "AC",
        "HF",
        "AF",
        "HO",
        "AO",
        "HY",
        "AY",
        "HR",
        "AR",
        "HFKC",
        "AFKC",
        "HBP",
        "ABP",
        "Attendance",
        "HHW",
        "AHW",
    ),
    enum_fields={},
)


class FootballDataUkAdapter:
    """Frozen public-resource adapter for the bounded Phase 1B proof only."""

    provider_code = "football_data_uk"
    repository = "https://www.football-data.co.uk"
    timeout_seconds = 60.0
    max_resource_bytes = 32 * 1024 * 1024
    capability = ProviderCapabilityV1(
        provider_id=provider_code,
        enabled=True,
        terms_status="approved_internal_non_commercial_research",
        supported_scopes=(
            ProviderScopeV1("E0", "2526", ("historical_league_csv",)),
            ProviderScopeV1("E0", "1516", ("historical_league_csv",)),
        ),
        resources=(
            ProviderResourceCapabilityV1("historical_league_csv"),
            ProviderResourceCapabilityV1("schema_semantics_and_attribution"),
        ),
        update_semantics="mutable_csv_content_hashed_on_acquisition",
        incremental_cursor_support=False,
        webhook_support=False,
        rate_limit_per_minute=None,
        credential_ref=None,
        adapter_version="football-data-uk-v1",
        roles=("tier_b",),
    )

    def __init__(self, *, transport: HttpTransport | None = None) -> None:
        self._transport = transport or UrllibHttpTransport(
            "football-forecasting/0.1 football-data-uk-acquisition"
        )

    def notes(self) -> SourceResource:
        return SourceResource("notes.txt", "text/plain")

    def historical_league_csv(self, *, division: str, season_code: str) -> SourceResource:
        path = f"mmz4281/{season_code}/{division}.csv"
        if not _CSV_PATH_PATTERN.fullmatch(path):
            raise ProviderConfigurationError(
                "resource is outside the frozen Phase 1B corpus: " + path
            )
        return SourceResource(path, "text/csv")

    def fetch(self, resource: SourceResource) -> bytes:
        return self._get(resource)

    def fetch_with_metadata(self, resource: SourceResource) -> HttpResponseV1:
        self._validate_resource(resource)
        get_response = getattr(self._transport, "get_response", None)
        if not callable(get_response):
            raise ProviderConfigurationError("transport cannot capture HTTP response metadata")
        response = get_response(
            f"{self.repository}/{resource.path}",
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_resource_bytes,
        )
        if not isinstance(response, HttpResponseV1):
            raise ProviderConfigurationError("transport returned invalid HTTP response metadata")
        return response

    def frozen_resources(self) -> tuple[SourceResource, ...]:
        return (
            self.notes(),
            self.historical_league_csv(division="E0", season_code="2526"),
            self.historical_league_csv(division="E0", season_code="1516"),
        )

    def _validate_resource(self, resource: SourceResource) -> None:
        if resource == self.notes():
            return
        if resource.media_type == "text/csv" and _CSV_PATH_PATTERN.fullmatch(resource.path):
            return
        raise ProviderConfigurationError(
            f"unsupported Football-Data resource path: {resource.path}"
        )

    def _get(self, resource: SourceResource) -> bytes:
        self._validate_resource(resource)
        return self._transport.get(
            f"{self.repository}/{resource.path}",
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_resource_bytes,
        )
