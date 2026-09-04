from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest
from football.normalization import (
    FootballDataUkNormalizationError,
    normalize_football_data_uk_record,
)
from football.providers import FootballDataUkCsvRecordV1, FootballDataUkSourceResourceV1


def test_normalization_preserves_aggregate_provider_statistics_without_events() -> None:
    receipt = _receipt()
    record = FootballDataUkCsvRecordV1(
        csv_record_index=7,
        values={
            "Div": "E0",
            "Date": "03/01/26",
            "Time": "15:00",
            "HomeTeam": "Alpha",
            "AwayTeam": "Beta",
            "FTHG": "2",
            "FTAG": "1",
            "FTR": "H",
            "HTHG": "1",
            "HTAG": "1",
            "HTR": "D",
            "HC": "8",
            "AC": "4",
            "HS": "12",
            "AS": "9",
            "HBP": "20",
            "ABP": "10",
            "ProviderNewAggregate": "unreviewed",
        },
    )

    normalized = normalize_football_data_uk_record(receipt, record)

    assert normalized.provider_match_ref.endswith("/record/7")
    assert normalized.provider_match_date == date(2026, 1, 3)
    assert normalized.provider_local_kickoff_time == time(15, 0)
    assert normalized.kickoff_at is None
    assert normalized.timezone is None
    assert normalized.full_time_home_goals == 2
    assert normalized.full_time_away_goals == 1
    assert normalized.full_time_result == "HOME_WIN"
    assert normalized.provider_aggregate_statistics == {
        "HC": 8,
        "AC": 4,
        "HS": 12,
        "AS": 9,
        "HBP": 20,
        "ABP": 10,
    }
    assert normalized.raw_values["ProviderNewAggregate"] == "unreviewed"


def test_normalization_rejects_inconsistent_result_or_invalid_aggregate_count() -> None:
    values = _base_values()
    values["FTR"] = "A"
    with pytest.raises(FootballDataUkNormalizationError, match="inconsistent"):
        normalize_football_data_uk_record(_receipt(), FootballDataUkCsvRecordV1(1, values))

    values = _base_values()
    values["HC"] = "eight"
    with pytest.raises(FootballDataUkNormalizationError, match="non-negative integer"):
        normalize_football_data_uk_record(_receipt(), FootballDataUkCsvRecordV1(1, values))


def test_normalization_accepts_four_digit_provider_dates() -> None:
    values = _base_values()
    values["Date"] = "03/01/2016"

    normalized = normalize_football_data_uk_record(_receipt(), FootballDataUkCsvRecordV1(1, values))

    assert normalized.provider_match_date == date(2016, 1, 3)


def _receipt() -> FootballDataUkSourceResourceV1:
    return FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/2526/E0.csv",
        payload=b"immutable source",
        observed_by_matchforge_at=datetime(2026, 9, 4, 13, 30, tzinfo=UTC),
        http_status=200,
        content_type="text/csv",
    )


def _base_values() -> dict[str, str]:
    return {
        "Div": "E0",
        "Date": "03/01/26",
        "HomeTeam": "Alpha",
        "AwayTeam": "Beta",
        "FTHG": "2",
        "FTAG": "1",
        "FTR": "H",
        "HTHG": "1",
        "HTAG": "1",
        "HTR": "D",
    }
