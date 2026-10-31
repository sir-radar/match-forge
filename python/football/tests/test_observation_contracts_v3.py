from __future__ import annotations

import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from football.contracts.observation_schema import observation_schema, observation_schema_sha256
from football.contracts.observations import ObservationError, observation_from_bytes
from football.contracts.observations_v2 import EntityReferenceV2
from football.contracts.observations_v3 import (
    ObservationVersionsV3,
    PeriodScoreObservationV3,
    PlayerStatisticObservationV3,
    RefereeObservationV3,
    ShotObservationV3,
    TeamRatingObservationV3,
    TeamStatisticObservationV3,
)
from test_observation_contracts import fixture


def common() -> dict[str, Any]:
    old = fixture()
    return {
        "provenance": replace(
            old.provenance, provider_native_id=None, source_record_key="json:/reported"
        ),
        "time": old.time,
        "versions": ObservationVersionsV3(
            adapter_version="contract-test", normalizer_version="rich-resource-test"
        ),
    }


def examples() -> list[Any]:
    fixture_ref, team_ref = EntityReferenceV2("42"), EntityReferenceV2("1")
    return [
        TeamStatisticObservationV3(
            **common(),
            fixture=fixture_ref,
            team=team_ref,
            period="FULL_MATCH",
            offsides=0,
            passes=100,
            accurate_passes=90,
        ),
        PlayerStatisticObservationV3(
            **common(),
            fixture=fixture_ref,
            team=team_ref,
            player=EntityReferenceV2("2"),
            shots=2,
            shots_on_target=1,
        ),
        ShotObservationV3(
            **common(),
            fixture=fixture_ref,
            team=team_ref,
            body_part="RIGHT_FOOT",
            expected_goals_on_target=0.7,
            home_goals_before_shot=0,
            away_goals_before_shot=0,
        ),
        PeriodScoreObservationV3(
            **common(),
            fixture=fixture_ref,
            period="FIRST_HALF",
            score_basis="REGULATION_90",
            home_goals=0,
            away_goals=1,
            period_complete=True,
        ),
        RefereeObservationV3(
            **common(),
            fixture=fixture_ref,
            referee=EntityReferenceV2(None, source_record_key="csv:record/1/Referee"),
            name="Reported referee",
        ),
        TeamRatingObservationV3(
            **common(),
            team=team_ref,
            rating_date=date(2026, 10, 1),
            rating=1500.5,
            rating_system="source-reported-elo",
        ),
    ]


def test_rich_contracts_round_trip_without_inventing_missing_values_or_semantics() -> None:
    for item in examples():
        decoded = observation_from_bytes(item.to_bytes())
        assert decoded == item and decoded.to_bytes() == item.to_bytes()
        assert decoded.provenance == item.provenance
        assert decoded.time == item.time
        assert isinstance(decoded.versions, ObservationVersionsV3)
        assert decoded.versions.semantic_version is None
    assert examples()[0].corners is None
    assert examples()[0].offsides == 0
    rating = observation_from_bytes(examples()[-1].to_bytes())
    assert isinstance(rating, TeamRatingObservationV3)
    assert isinstance(rating.rating_date, date)


def test_old_schema_identities_are_unchanged_and_v3_matches_checked_in_schema() -> None:
    assert observation_schema_sha256("1") == (
        "5028f7b235aded2d7e87b08f25b0b44e4d6d242a720a61ed723bdec940beac14"
    )
    assert observation_schema_sha256("2") == (
        "f1490653fd46652dd3823309536adeb1baff51f523562d8f9627f24786eecfbc"
    )
    assert observation_schema_sha256("3") == (
        "eeb6e65f4ad68eaa6bbac0043776312d16c3cea853308611d63da3b90dfab4b5"
    )
    path = Path("schemas/contracts/resource-observations-v3.schema.json")
    assert json.loads(path.read_bytes()) == observation_schema("3")


@pytest.mark.parametrize("value", [-1, True, 1.5, float("inf")])
def test_rich_count_fields_reject_invalid_values(value: object) -> None:
    with pytest.raises(ObservationError):
        replace(examples()[0], offsides=value)


def test_compatible_counts_and_shot_context_reject_inconsistent_data() -> None:
    with pytest.raises(ObservationError, match="shots_on_target"):
        replace(examples()[0], total_shots=1, shots_on_target=2)
    with pytest.raises(ObservationError, match="accurate_passes"):
        replace(examples()[0], accurate_passes=101)
    with pytest.raises(ObservationError, match="shots_on_target"):
        replace(examples()[1], shots_on_target=3)
    with pytest.raises(ObservationError):
        replace(examples()[2], expected_goals_on_target=1.1)
    with pytest.raises(ObservationError, match="both"):
        replace(examples()[2], away_goals_before_shot=None)


def test_period_basis_and_referee_identity_are_explicit() -> None:
    with pytest.raises(ObservationError):
        replace(examples()[3], score_basis="EXTRA_TIME")
    with pytest.raises(ObservationError):
        replace(examples()[4], name=None)
    assert examples()[4].referee.provider_native_id is None
    assert examples()[4].referee.canonical_id is None
    with pytest.raises(ObservationError):
        replace(examples()[-1], rating=float("nan"))
    with pytest.raises(ObservationError, match="rating_system"):
        replace(examples()[-1], rating_system=" ")


@pytest.mark.parametrize("metric", ["shots_off_target", "blocked_shots"])
def test_shot_subsets_cannot_exceed_the_reported_total(metric: str) -> None:
    with pytest.raises(ObservationError, match=metric):
        replace(examples()[0], **{metric: 2, "total_shots": 1})


def test_v3_rejects_wrong_wire_version_and_backdated_knowledge() -> None:
    item = examples()[0]
    payload = json.loads(item.to_bytes())
    payload["versions"]["observation_contract_version"] = "2"
    with pytest.raises(ObservationError):
        observation_from_bytes(json.dumps(payload).encode())
    with pytest.raises(ObservationError, match="known_at"):
        replace(item, time=replace(item.time, known_at=item.time.known_at.replace(year=2025)))


def test_unknown_semantics_and_referee_labels_cannot_be_fabricated_as_observed_values() -> None:
    with pytest.raises(ObservationError):
        TeamStatisticObservationV3(
            **common(),
            fixture=EntityReferenceV2("42"),
            team=EntityReferenceV2("1"),
            period="FULL_MATCH",
        )
    with pytest.raises(ObservationError, match="semantic_version"):
        replace(examples()[0], versions=replace(examples()[0].versions, semantic_version=" "))
    with pytest.raises(ObservationError, match="referee name"):
        replace(examples()[4], name=" ")
    identified = replace(examples()[4], name=None, referee=EntityReferenceV2("reported-id"))
    assert identified.name is None and identified.referee.canonical_id is None
    payload = json.loads(examples()[-1].to_bytes())
    payload["rating_date"] = "2026-02-30"
    with pytest.raises(ObservationError):
        observation_from_bytes(json.dumps(payload).encode())
