from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.normalization import (
    FootballDataUkNormalizedMatchV1,
    normalize_football_data_uk_record,
)
from football.providers import FootballDataUkCsvRecordV1, FootballDataUkSourceResourceV1
from football.providers.football_data_uk_overlap import (
    FootballDataUkOverlapSelectionError,
    select_football_data_uk_overlap_prefix,
)


def test_overlap_prefix_uses_source_order_and_selects_shortest_complete_prefix() -> None:
    selection = select_football_data_uk_overlap_prefix(
        (
            _match(3, "03/01/16", "E", "F", hc="", ac=""),
            _match(1, "01/01/16", "A", "B", hc="", ac=""),
            _match(2, "02/01/16", "C", "D", hc="4", ac="3"),
        ),
        corners_declared=True,
        trusted_record_indexes=frozenset((2,)),
    )

    assert selection.selection_rule_version == "FootballDataUkOverlapPrefixSelectionV1"
    assert selection.provider_team_labels == frozenset(("A", "B", "C", "D", "E", "F"))
    assert [record.csv_record_index for record in selection.ordered_records] == [1, 2, 3]
    assert [record.csv_record_index for record in selection.selected_records] == [1, 2, 3]


def test_overlap_prefix_fails_when_no_trusted_match_exists() -> None:
    with pytest.raises(FootballDataUkOverlapSelectionError, match="trusted match"):
        select_football_data_uk_overlap_prefix(
            (_match(1, "01/01/16", "A", "B", hc="1", ac="1"),),
            corners_declared=True,
            trusted_record_indexes=frozenset(),
        )


def _match(
    index: int,
    match_date: str,
    home: str,
    away: str,
    *,
    hc: str,
    ac: str,
) -> FootballDataUkNormalizedMatchV1:
    values = {
        "Div": "E0",
        "Date": match_date,
        "HomeTeam": home,
        "AwayTeam": away,
        "FTHG": "1",
        "FTAG": "0",
        "FTR": "H",
        "HTHG": "0",
        "HTAG": "0",
        "HTR": "D",
        "HC": hc,
        "AC": ac,
    }
    receipt = FootballDataUkSourceResourceV1.from_payload(
        resource_type="historical_league_csv",
        source_path="mmz4281/1516/E0.csv",
        payload=f"resource-{index}".encode(),
        observed_by_matchforge_at=datetime(2026, 9, 4, 14, 0, tzinfo=UTC),
        http_status=200,
        content_type="text/csv",
    )
    return normalize_football_data_uk_record(receipt, FootballDataUkCsvRecordV1(index, values))
