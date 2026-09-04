from __future__ import annotations

import re

from football.contracts.source import SourceResource
from football.providers.base import (
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
        if resource == self.notes():
            return self._get(resource)
        if resource.media_type == "text/csv" and _CSV_PATH_PATTERN.fullmatch(resource.path):
            return self._get(resource)
        raise ProviderConfigurationError(
            f"unsupported Football-Data resource path: {resource.path}"
        )

    def _get(self, resource: SourceResource) -> bytes:
        return self._transport.get(
            f"{self.repository}/{resource.path}",
            timeout_seconds=self.timeout_seconds,
            max_bytes=self.max_resource_bytes,
        )
