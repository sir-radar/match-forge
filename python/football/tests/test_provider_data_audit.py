from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from football.providers.data_audit import summarize_observations, summarize_statistics


def test_retained_fields_measure_missing_zero_and_time_without_inventing_qualification() -> None:
    from test_observation_contracts_v3 import examples

    observation = examples()[0]
    report = summarize_observations([observation])
    by_path = {field["field"]: field for field in report}
    assert by_path["/offsides"]["zero"] == by_path["/offsides"]["known"] == 1
    assert by_path["/corners"]["missing"] == 1
    assert by_path["/corners"]["zero"] == by_path["/corners"]["known"] == 0
    assert by_path["/passes"]["source_resources"] == 1
    for field in report:
        assert field["known"] + field["missing"] == field["measurements"]
        assert field["semantic_version_known"] == 0
        assert field["identity_qualified"] is None
        assert field["pit_eligible"] is None
        assert field["expected_units"] is None


def test_retained_audit_keeps_sources_periods_versions_and_missing_times_separate() -> None:
    from dataclasses import replace

    from test_observation_contracts_v3 import examples

    first = examples()[0]
    first = replace(first, time=replace(first.time, event_time=None))
    second = replace(first, provenance=replace(first.provenance, provider="soccerway"))
    third = replace(first, period="FIRST_HALF")
    report = summarize_observations([first, second, third])
    offsides = [field for field in report if field["field"] == "/offsides"]
    assert len(offsides) == 3
    assert {field["provider"] for field in offsides} == {first.provenance.provider, "soccerway"}
    assert all(field["event_time_known"] == 0 for field in report)
    assert summarize_observations([]) == []


def test_retained_boolean_false_is_observed_and_never_a_numeric_zero() -> None:
    from dataclasses import replace

    from test_observation_contracts_v3 import examples

    report = summarize_observations([replace(examples()[3], period_complete=False)])
    field = next(field for field in report if field["field"] == "/period_complete")
    assert field["known"] == 1 and field["missing"] == field["zero"] == 0


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
