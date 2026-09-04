from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from football.contracts.source import SourceResource
from football.providers import (
    FootballDataUkAdapter,
    FootballDataUkHistoricalLeagueCsvV1,
    ProviderConfigurationError,
)


@dataclass
class RecordingTransport:
    payload: bytes = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\n"
    urls: list[str] = field(default_factory=list)

    def get(self, url: str, *, timeout_seconds: float, max_bytes: int) -> bytes:
        self.urls.append(url)
        assert timeout_seconds == 60
        assert max_bytes == 32 * 1024 * 1024
        return self.payload


def test_football_data_adapter_limits_resources_to_frozen_provider_proof_corpus() -> None:
    transport = RecordingTransport()
    adapter = FootballDataUkAdapter(transport=transport)

    notes = adapter.notes()
    current = adapter.historical_league_csv(division="E0", season_code="2526")
    overlap = adapter.historical_league_csv(division="E0", season_code="1516")

    assert adapter.provider_code == "football_data_uk"
    assert adapter.capability.enabled
    assert adapter.capability.credential_ref is None
    assert adapter.capability.roles == ("tier_b",)
    assert [resource.path for resource in (notes, current, overlap)] == [
        "notes.txt",
        "mmz4281/2526/E0.csv",
        "mmz4281/1516/E0.csv",
    ]
    assert current.media_type == "text/csv"
    assert notes.media_type == "text/plain"
    assert adapter.fetch(current) == transport.payload
    assert transport.urls == ["https://www.football-data.co.uk/mmz4281/2526/E0.csv"]


@pytest.mark.parametrize(
    ("division", "season_code"),
    [("E1", "2526"), ("E0", "2627"), ("e0", "2526")],
)
def test_football_data_adapter_rejects_resources_outside_frozen_corpus(
    division: str, season_code: str
) -> None:
    adapter = FootballDataUkAdapter()

    with pytest.raises(ProviderConfigurationError, match="frozen Phase 1B corpus"):
        adapter.historical_league_csv(division=division, season_code=season_code)

    with pytest.raises(ProviderConfigurationError, match="unsupported Football-Data"):
        adapter.fetch(SourceResource("mmz4281/2526/E1.csv", "text/csv"))


def test_football_data_csv_contract_requires_results_fields_and_preserves_additions() -> None:
    contract = FootballDataUkHistoricalLeagueCsvV1

    accepted = contract.inspect_columns(
        ("Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR")
    )
    additive = contract.inspect_columns(
        (
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
            "ProviderNewAggregate",
        )
    )
    missing = contract.inspect_columns(("Div", "Date", "HomeTeam"))

    assert accepted.status == "accepted"
    assert additive.status == "accepted"
    assert additive.unknown_additive_fields == ("ProviderNewAggregate",)
    assert missing.status == "quarantine"
    assert missing.missing_required_fields == (
        "AwayTeam",
        "FTHG",
        "FTAG",
        "FTR",
        "HTHG",
        "HTAG",
        "HTR",
    )
