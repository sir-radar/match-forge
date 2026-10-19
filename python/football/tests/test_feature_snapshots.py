from dataclasses import replace
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from football.forecasting.model_contracts import CompetitionContext, ForecastInputSnapshot
from football.forecasting.snapshot import build_forecast_snapshot
from test_multi_model_forecasting import AWAY, COMPETITION, HOME, KICKOFF, _training_history

TARGET = UUID(int=1_000_000)


def _input() -> ForecastInputSnapshot:
    return build_forecast_snapshot(
        fixture_id=TARGET,
        competition_id=COMPETITION,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        history=_training_history(),
        source_references=("retained-test-dataset",),
    )


def test_target_identity_is_excluded_even_with_an_earlier_kickoff_revision() -> None:
    history = _training_history()
    target_revision = replace(
        history[0], fixture_id=TARGET, kickoff_at=history[0].kickoff_at - timedelta(minutes=1)
    )
    snapshot = build_forecast_snapshot(
        fixture_id=TARGET,
        competition_id=COMPETITION,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        football_cutoff=KICKOFF,
        knowledge_cutoff=KICKOFF,
        knowledge_mode="bitemporal",
        history=(*history, target_revision),
    )
    assert TARGET not in {row.fixture_id for row in snapshot.qualified_history}
    assert snapshot.qualified_history == history


def test_snapshot_keeps_unsupported_resources_missing_and_preserves_legacy_inputs() -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    original = _input()
    snapshot = FixtureFeatureSnapshotV1(original)
    value = snapshot.to_dict()
    assert value["contract"] == "FixtureFeatureSnapshotV1"
    assert value["football_cutoff"] == value["knowledge_cutoff"]
    assert snapshot.model_input.to_dict() == original.to_dict()
    assert value["model_input"] == original.to_dict()
    assert snapshot.model_input.sha256 == original.sha256
    assert value["quality"] is None
    for family in (
        "league_strength",
        "home_advantage",
        "travel",
        "manager_context",
        "lineup_context",
        "availability_context",
        "tactical_context",
        "corners_context",
        "cards_context",
        "player_context",
    ):
        assert value[family] is None
        assert family in value["missingness"]
    assert value["provenance"]["source_references"] == ["retained-test-dataset"]
    assert set(value["fixture"]) == {
        "fixture_id",
        "competition_id",
        "competition_context",
        "season_label",
        "kickoff_at",
        "home_team_id",
        "away_team_id",
    }


@pytest.mark.parametrize("invalid", ["target", "future", "late_known", "duplicate"])
def test_snapshot_rejects_unqualified_history(invalid: str) -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    original = _input()
    row = original.qualified_history[0]
    cases: dict[str, dict[str, Any]] = {
        "target": {"fixture_id": TARGET},
        "future": {"kickoff_at": KICKOFF},
        "late_known": {"known_at": KICKOFF + timedelta(seconds=1)},
        "duplicate": {},
    }
    altered = replace(row, **cases[invalid])
    with pytest.raises(ValueError):
        FixtureFeatureSnapshotV1(
            replace(original, qualified_history=(*original.qualified_history, altered))
        )


def test_snapshot_copies_mutable_context_and_exported_values() -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    context: dict[str, object] = {"home_days_since_last_match": 3.0}
    original = replace(
        _input(),
        rest_context=context,
        context_provenance=(
            {"source_reference": "retained-rest", "known_at": KICKOFF.isoformat()},
        ),
    )
    snapshot = FixtureFeatureSnapshotV1(original, quality=("SOURCE_QUALITY_REVIEWED",))
    digest = snapshot.sha256
    context["home_days_since_last_match"] = 100.0
    projection = snapshot.model_input
    assert projection.rest_context == {"home_days_since_last_match": 3.0}
    assert projection.rest_context is not None
    projection.rest_context["home_days_since_last_match"] = 200.0
    payload = snapshot.to_dict()
    payload["fixture"]["home_score"] = 9
    assert snapshot.sha256 == digest
    assert "home_score" not in snapshot.to_dict()["fixture"]
    assert snapshot.model_input.rest_context == {"home_days_since_last_match": 3.0}


def test_feature_snapshot_and_legacy_model_inputs_produce_identical_champion_forecasts() -> None:
    from football.forecasting.champion_adapter import (
        TransferableRollingGoalsChampion,
        load_champion_artifact,
    )
    from football.forecasting.features import FixtureFeatureSnapshotV1
    from football.forecasting.model_runner import ModelRegistry, ModelRunner, RegisteredModel
    from football.product.domain import MODEL_ARTIFACT_PATH

    original = _input()
    runner = ModelRunner(
        ModelRegistry(
            (
                RegisteredModel(
                    TransferableRollingGoalsChampion(),
                    load_champion_artifact(MODEL_ARTIFACT_PATH, original.qualified_history),
                    True,
                    minimum_team_history=10,
                ),
            )
        )
    )
    old = runner.run(original).forecasts[0]
    new = runner.run(FixtureFeatureSnapshotV1(original)).forecasts[0]
    assert old.expected_home_goals == new.expected_home_goals
    assert old.expected_away_goals == new.expected_away_goals
    assert old.score_matrix == new.score_matrix
    assert old.input_snapshot_sha256 == new.input_snapshot_sha256 == original.sha256


def test_feature_export_validates_and_target_outcomes_have_no_fixture_fields() -> None:
    import json
    from pathlib import Path

    from football.forecasting.features import FixtureFeatureSnapshotV1
    from jsonschema import Draft202012Validator, FormatChecker

    schema = json.loads(
        Path("schemas/contracts/fixture-feature-snapshot-v1.schema.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    payload = FixtureFeatureSnapshotV1(_input()).to_dict()
    validator.validate(payload)
    payload["fixture"]["home_score"] = 2
    assert list(validator.iter_errors(payload))


@pytest.mark.parametrize("invalid", ["unproven", "late", "target_outcome"])
def test_external_context_requires_eligible_provenance_and_no_target_outcomes(invalid: str) -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    base = _input()
    context: dict[str, object] = {"coach_tenure_days": 10.0}
    provenance: tuple[dict[str, object], ...] = (
        {
            "source_reference": "retained-coach-observation",
            "known_at": KICKOFF.isoformat(),
        },
    )
    if invalid == "unproven":
        provenance = ()
    elif invalid == "late":
        provenance = (
            {
                "source_reference": "retained-coach-observation",
                "known_at": (KICKOFF + timedelta(seconds=1)).isoformat(),
            },
        )
    else:
        context = {"home_score": 3.0}
    with pytest.raises(ValueError):
        FixtureFeatureSnapshotV1(
            replace(base, coach_context=context, context_provenance=provenance)
        )


def test_training_replay_and_production_share_exact_rolling_features(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football.forecasting.pitchapi_v3 import (
        HistoryObservationV1,
        MatchHistoryFeaturesV1,
        RollingHistoryV1,
        TransferableGoalModelV1,
        build_training_rows,
    )
    from football.product.domain import MODEL_ARTIFACT_PATH, FinishedMatch, forecast_from_history

    observations = tuple(
        HistoryObservationV1(
            match_id=UUID(int=100 + index),
            kickoff_at=KICKOFF - timedelta(days=20 - index),
            home_team_id=HOME,
            away_team_id=AWAY,
            home_goals=index % 4,
            away_goals=index % 3,
            home_npxg=1.0 + index / 10,
            away_npxg=0.5 + index / 10,
        )
        for index in range(12)
    )
    replay = RollingHistoryV1()
    for row in observations:
        replay.update_batch((row,))
    expected = replay.features(HOME, AWAY, cutoff=KICKOFF)
    target = replace(observations[-1], match_id=TARGET, kickoff_at=KICKOFF, home_goals=999)
    training = build_training_rows((*observations, target), scope_key="test")
    assert training[-1].features == expected
    captured: list[MatchHistoryFeaturesV1] = []
    original = TransferableGoalModelV1.forecast_features

    def record(self: TransferableGoalModelV1, features: MatchHistoryFeaturesV1) -> Any:
        captured.append(features)
        return original(self, features)

    monkeypatch.setattr(TransferableGoalModelV1, "forecast_features", record)
    forecast = forecast_from_history(
        artifact_path=MODEL_ARTIFACT_PATH,
        target_kickoff=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        history=tuple(
            FinishedMatch(
                row.match_id,
                row.kickoff_at,
                row.home_team_id,
                row.away_team_id,
                row.home_goals,
                row.away_goals,
                row.home_npxg,
                row.away_npxg,
            )
            for row in observations
        ),
    )
    assert forecast is not None and captured == [expected]


def test_low_level_publication_rejects_target_results_before_model_computation() -> None:
    import json
    from typing import cast

    from football.forecasting.pitchapi_v3 import TransferableParametersV1
    from football.product.api_football import ApiFootballClient
    from football.product.domain import MODEL_ARTIFACT_PATH, FinishedMatch
    from football.product.sync import ProductSync

    params = TransferableParametersV1(**json.loads(MODEL_ARTIFACT_PATH.read_bytes())["parameters"])
    product = ProductSync(
        cast(Any, object()),
        ApiFootballClient("offline"),
        MODEL_ARTIFACT_PATH.parent,
        MODEL_ARTIFACT_PATH,
    )
    target_result = FinishedMatch(TARGET, KICKOFF - timedelta(days=1), HOME, AWAY, 9, 0)
    with pytest.raises(ValueError, match="target fixture"):
        product._publish_forecast(
            TARGET,
            HOME,
            AWAY,
            KICKOFF,
            KICKOFF - timedelta(hours=1),
            [target_result],
            "a" * 64,
            params,
        )


def test_qualified_context_is_retained_without_activating_predictive_features() -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    base = _input()
    contextual = replace(
        base,
        coach_context={"coach_tenure_days": 10.0},
        context_provenance=(
            {
                "source_reference": "retained-coach-observation",
                "known_at": KICKOFF.isoformat(),
            },
        ),
    )
    snapshot = FixtureFeatureSnapshotV1(contextual)
    assert snapshot.to_dict()["manager_context"] == {"coach_tenure_days": 10.0}
    assert snapshot.model_input.sha256 == base.sha256
    assert snapshot.sha256 != FixtureFeatureSnapshotV1(base).sha256


def test_context_cannot_hide_a_late_fact_behind_earlier_provenance() -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    original = _input()
    with pytest.raises(ValueError, match="knowledge time"):
        FixtureFeatureSnapshotV1(
            replace(
                original,
                coach_context={"known_at": (KICKOFF + timedelta(seconds=1)).isoformat()},
                context_provenance=(
                    {"source_reference": "retained", "known_at": KICKOFF.isoformat()},
                ),
            )
        )


def test_unsupported_feature_contract_cannot_be_mislabeled() -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    with pytest.raises(ValueError, match="contract version"):
        FixtureFeatureSnapshotV1(_input(), feature_contract_version="unrecognized")


@pytest.mark.parametrize(
    ("football_days", "knowledge_days", "eligible"),
    [(20, 5, True), (20, 0.5, False), (5, 2, False)],
)
def test_feature_football_and_knowledge_cutoffs_remain_independent(
    football_days: float,
    knowledge_days: float,
    eligible: bool,
) -> None:
    from football.forecasting.features import FixtureFeatureSnapshotV1

    original = _input()
    observation = replace(
        original.qualified_history[0],
        fixture_id=UUID(int=2_000_000),
        kickoff_at=KICKOFF - timedelta(days=football_days),
        known_at=KICKOFF - timedelta(days=knowledge_days),
    )
    source = build_forecast_snapshot(
        fixture_id=TARGET,
        competition_id=COMPETITION,
        competition_context=CompetitionContext.LEAGUE,
        season_label="2026",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        football_cutoff=KICKOFF - timedelta(days=10),
        knowledge_cutoff=KICKOFF - timedelta(days=1),
        knowledge_mode="bitemporal",
        history=(*original.qualified_history, observation),
    )
    assert (
        observation.fixture_id in {row.fixture_id for row in source.qualified_history}
    ) is eligible
    payload = FixtureFeatureSnapshotV1(source).to_dict()
    assert payload["football_cutoff"] != payload["knowledge_cutoff"]
