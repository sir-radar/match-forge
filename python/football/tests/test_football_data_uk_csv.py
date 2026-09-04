from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.providers import (
    FootballDataUkCsvValidationError,
    FootballDataUkSourceResourceV1,
    parse_football_data_uk_csv,
)


def test_csv_parser_produces_ordered_header_fingerprint_and_resource_local_coverage() -> None:
    payload = (
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HC,AC,NewAggregate\n"
        b"E0,01/01/26,A,B,1,0,H,1,0,H,5,2,x\n"
        b"E0,02/01/26,C,D,0,0,D,0,0,D,,,\n"
    )
    result = parse_football_data_uk_csv(_receipt(payload), payload)

    assert result.schema.status == "accepted"
    assert result.schema.unknown_additive_fields == ("NewAggregate",)
    assert result.coverage.row_count == 2
    assert result.coverage.header == (
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
        "HC",
        "AC",
        "NewAggregate",
    )
    assert result.coverage.header_sha256 == (
        "f417558ec2db993966ed80765c3b39f563f13f447aeffcd2254a990cce16e806"
    )
    assert result.coverage.field_coverage("HC").non_null_count == 1
    assert result.coverage.field_coverage("HC").null_count == 1
    assert result.coverage.field_coverage("HC").coverage_ratio == 0.5
    assert result.records[0].csv_record_index == 1
    assert result.records[1].values["HomeTeam"] == "C"


def test_csv_parser_reports_schema_quarantine_and_rejects_non_rectangular_rows() -> None:
    missing_required = b"Div,Date,HomeTeam\nE0,01/01/26,A\n"
    quarantined = parse_football_data_uk_csv(_receipt(missing_required), missing_required)

    assert quarantined.schema.status == "quarantine"
    assert quarantined.records == ()

    malformed = (
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR\nE0,01/01/26,A,B,1,0,H,1,0\n"
    )
    with pytest.raises(FootballDataUkCsvValidationError, match="does not match header"):
        parse_football_data_uk_csv(_receipt(malformed), malformed)


def _receipt(payload: bytes) -> FootballDataUkSourceResourceV1:
    return FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/2526/E0.csv",
        payload=payload,
        observed_by_matchforge_at=datetime(2026, 9, 4, 13, 15, tzinfo=UTC),
        http_status=200,
        content_type="text/csv",
    )
