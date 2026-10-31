from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from football.providers.data_audit import summarize_statistics


def test_audit_counts_revisions_and_unique_fixtures_without_equating_zero_and_missing() -> None:
    row = {
        "provider": "fotmob",
        "competition_id": "competition",
        "season_id": "2026/2027",
        "fixture_id": "fixture",
        "kickoff_at": datetime(2026, 10, 1, tzinfo=UTC),
        "payload": {
            "Periods": {
                "All": {"stats": [{"stats": [{"key": "unmapped_metric", "stats": [0, None]}]}]}
            }
        },
    }
    report = summarize_statistics([row, row])
    field = report["fields"][0]
    assert field["resource_rows"] == 2
    assert field["fixtures"] == 1
    assert field["home_known"] == field["home_zero"] == 2
    assert field["away_known"] == field["away_zero"] == 0
    assert field["normalized_field"] is None
    assert field["modeled"] is None


def test_audit_separates_provider_season_and_period_and_retains_unknown_statistic() -> None:
    def row(provider: str, season: str, period: str) -> dict[str, Any]:
        item = {"key": "passes", "home": 0, "away": 12}
        return {
            "provider": provider,
            "competition_id": None,
            "season_id": season,
            "fixture_id": None,
            "kickoff_at": None,
            "payload": {"periods": [{"period": period, "groups": [{"items": [item]}]}]},
        }

    report = summarize_statistics(
        [row("pitchapi", "2025", "FirstHalf"), row("pitchapi", "2026", "SecondHalf")]
    )
    assert len(report["fields"]) == 2
    assert {field["period"] for field in report["fields"]} == {"FIRST_HALF", "SECOND_HALF"}
    assert all(field["fixtures"] == 0 for field in report["fields"])
    assert all(field["earliest_fixture"] is None for field in report["fields"])
    unknown = summarize_statistics([row("new_provider", "2026", "All")])
    assert unknown == {"fields": [], "unparsed_resource_rows": {"new_provider": 1}}


@pytest.mark.parametrize("invalid", ["NaN", float("nan"), float("inf"), True])
def test_audit_does_not_count_invalid_numbers_as_observed_or_invent_qualification(
    invalid: object,
) -> None:
    row = {
        "provider": "pitchapi",
        "competition_id": None,
        "season_id": None,
        "fixture_id": "fixture",
        "kickoff_at": None,
        "payload": {
            "periods": [
                {
                    "period": "All",
                    "groups": [{"items": [{"key": "corners", "home": invalid, "away": None}]}],
                }
            ]
        },
    }
    field = summarize_statistics([row])["fields"][0]
    assert field["home_known"] == field["away_known"] == 0
    assert field["normalized_field"] == "corners"
    assert field["identity_qualified"] is None
    assert field["semantically_qualified"] is None
    assert field["pit_eligible"] is None


def test_repeated_native_measurements_do_not_inflate_resource_coverage() -> None:
    item = {"key": "corners", "home": 0, "away": 2}
    row = {
        "provider": "pitchapi",
        "competition_id": None,
        "season_id": None,
        "fixture_id": "fixture",
        "kickoff_at": None,
        "payload": {"periods": [{"period": "All", "groups": [{"items": [item, item]}]}]},
    }
    field = summarize_statistics([row])["fields"][0]
    assert field["resource_rows"] == field["fixtures"] == 1
    assert field["measurement_rows"] == 2
    assert field["repeated_measurements"] == 1
