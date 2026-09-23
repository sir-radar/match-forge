from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.run_pitchapi_full_audit import combine_season_reports, validate_pilot_evidence
from scripts.run_pitchapi_validation_pilot import PilotStop


def _pilot_evidence() -> dict[str, Any]:
    value = json.loads(
        Path("docs/evidence/pitchapi-live-audit-replacement-pilot-2026-09-23.json").read_text(
            encoding="utf-8"
        )
    )
    return cast(dict[str, Any], value)


def test_recorded_pilot_evidence_is_accepted() -> None:
    seasons = validate_pilot_evidence(_pilot_evidence())

    assert set(seasons) == {"bundesliga", "ligue1"}
    assert seasons["bundesliga"]["observed_matches"] == 10
    assert seasons["ligue1"]["shots"] == 270


def test_changed_manifest_or_selection_evidence_stops_continuation() -> None:
    evidence = deepcopy(_pilot_evidence())
    evidence["manifests"]["bundesliga"]["selection_sha256"] = "0" * 64

    with pytest.raises(PilotStop, match="PILOT_EVIDENCE_SELECTION_HASH_MISMATCH"):
        validate_pilot_evidence(evidence)


def test_combines_pilot_and_unsampled_counts_without_inventing_fields() -> None:
    pilot = {
        "observed_matches": 10,
        "successful_shot_resources": 10,
        "empty_shot_resources": 1,
        "missing_shot_resources": 0,
        "malformed_shot_resources": 0,
        "shots": 200,
        "penalties": 2,
        "regulation_shots": 200,
        "invalid_xg": 0,
        "duplicate_shot_ids": 0,
        "unknown_periods": 0,
        "unknown_situations": 0,
        "missing_fields": 0,
        "request_failures": 0,
    }
    remainder = {
        "observed_matches": 296,
        "successful_shot_resources": 296,
        "empty_shot_resources": 2,
        "missing_shot_resources": 0,
        "malformed_shot_resources": 0,
        "shots": 6000,
        "penalties": 50,
        "regulation_shots": 6000,
        "invalid_xg": 0,
        "duplicate_shot_ids": 0,
        "unknown_periods": 0,
        "unknown_situations": 0,
        "missing_fields": 0,
        "request_failures": 0,
    }

    combined = combine_season_reports("bundesliga", 306, pilot, remainder)

    assert combined["expected_matches"] == 306
    assert combined["observed_matches"] == 306
    assert combined["successful_shot_resources"] == 306
    assert combined["empty_shot_resources"] == 3
    assert combined["shots"] == 6200
    assert combined["penalties"] == 52


def test_rejects_non_integer_aggregate_evidence() -> None:
    pilot = validate_pilot_evidence(_pilot_evidence())["bundesliga"]
    remainder = dict(pilot)
    remainder["shots"] = "277"

    with pytest.raises(PilotStop, match="MALFORMED_AGGREGATE_EVIDENCE"):
        combine_season_reports("bundesliga", 306, pilot, remainder)
