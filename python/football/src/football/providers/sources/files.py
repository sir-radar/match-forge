"""Read retained file resources without changing their acquisition or identity."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from football.contracts.source import SHA1_PATTERN, validate_relative_posix_path
from football.product.openfootball import OpenFootballCatalogEntry
from football.providers.base import ProviderConfigurationError
from football.providers.football_data_uk import FootballDataUkSourceResourceV1
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1
from football.providers.sources.contracts import ProviderPayload
from football.storage.raw import ImmutableFileStore


class OpenFootballSource:
    def __init__(
        self,
        entries: Sequence[OpenFootballCatalogEntry],
        *,
        acquired_at: datetime,
    ) -> None:
        self.entries = tuple(entries)
        self.acquired_at = acquired_at

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        matches = [
            entry
            for entry in self.entries
            if (entry.source_file.stem == provider_competition_id and entry.season == season)
        ]
        if len(matches) != 1:
            raise ProviderConfigurationError("OpenFootball scope needs exactly one catalog entry")
        entry = matches[0]
        if not SHA1_PATTERN.fullmatch(entry.source_revision):
            raise ProviderConfigurationError("OpenFootball source revision must be a Git SHA")
        resource_key = validate_relative_posix_path(f"{season}/{entry.source_file.name}")
        try:
            raw = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(entry.source_file.parent.parent),
                    "show",
                    f"{entry.source_revision}:{resource_key}",
                ],
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as error:
            raise ProviderConfigurationError(
                "OpenFootball pinned resource is unavailable"
            ) from error
        return ProviderPayload(
            provider="openfootball",
            resource_key=resource_key,
            acquired_at=self.acquired_at,
            raw=raw,
            media_type="application/json",
            source_revision=entry.source_revision,
        )


class FootballDataUkSource:
    def __init__(self, root: Path, receipt: FootballDataUkSourceResourceV1) -> None:
        if receipt.resource_type != "historical_league_csv":
            raise ProviderConfigurationError("historical CSV receipt is required")
        self.files, self.receipt = ImmutableFileStore(root), receipt

    def results(self, provider_competition_id: str, season: str) -> ProviderPayload:
        receipt = self.receipt
        if (provider_competition_id, season) != (
            receipt.provider_competition_code,
            receipt.provider_season_code,
        ):
            raise ProviderConfigurationError("request differs from the registered CSV scope")
        path = self.files.path_for(FootballDataUkRawStoreV1.relative_path(receipt))
        if path.is_symlink():
            raise ProviderConfigurationError("retained source must not be a symlink")
        result = ProviderPayload(
            provider="football_data_uk",
            resource_key=receipt.source_path,
            acquired_at=receipt.observed_by_matchforge_at,
            raw=path.read_bytes(),
            media_type="text/csv",
        )
        if result.sha256 != receipt.raw_sha256 or len(result.raw) != receipt.raw_byte_size:
            raise ProviderConfigurationError("retained CSV differs from its immutable receipt")
        return result
