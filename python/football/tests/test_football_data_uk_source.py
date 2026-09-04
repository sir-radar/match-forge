from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.providers import (
    FootballDataUkSourceResourceError,
    FootballDataUkSourceResourceV1,
)


def test_football_data_source_resource_is_content_addressed_and_retrospective() -> None:
    observed_at = datetime(2026, 9, 4, 12, 45, tzinfo=UTC)
    resource = FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/2526/E0.csv",
        payload=b"Div,Date\nE0,01/01/26\n",
        observed_by_matchforge_at=observed_at,
        http_status=200,
        content_type="text/csv",
        http_etag='"provider-version"',
    )

    assert resource.provider_id == "football_data_uk"
    assert resource.source_host == "www.football-data.co.uk"
    assert resource.provider_competition_code == "E0"
    assert resource.provider_season_code == "2526"
    assert resource.raw_byte_size == len(b"Div,Date\nE0,01/01/26\n")
    assert resource.knowledge_mode == "retrospective"
    assert resource.known_from == observed_at
    assert resource.historical_provider_known_at is None
    assert resource.resource_identity == (
        "football_data_uk/mmz4281/2526/E0.csv/sha256/"
        "7e2683673c55f06c61b7922be35d8ad5a09efd70e07ec160bd7e4034065f0b0c"
    )
    assert resource.to_dict()["provider_schema_version"] is None


def test_football_data_source_resource_rejects_unapproved_paths_and_mismatched_bytes() -> None:
    observed_at = datetime(2026, 9, 4, 12, 45, tzinfo=UTC)

    with pytest.raises(FootballDataUkSourceResourceError, match="frozen Phase 1B corpus"):
        FootballDataUkSourceResourceV1.from_payload(
            resource_type="historical_league_csv",
            source_path="mmz4281/2627/E0.csv",
            payload=b"x",
            observed_by_matchforge_at=observed_at,
            http_status=200,
            content_type="text/csv",
        )
    with pytest.raises(FootballDataUkSourceResourceError, match="raw byte size"):
        FootballDataUkSourceResourceV1(
            resource_type="historical_league_csv",
            source_path="mmz4281/2526/E0.csv",
            observed_by_matchforge_at=observed_at,
            http_status=200,
            content_type="text/csv",
            raw_byte_size=0,
            raw_sha256="7e2683673c55f06c61b7922be35d8ad5a09efd70e07ec160bd7e4034065f0b0c",
        )
