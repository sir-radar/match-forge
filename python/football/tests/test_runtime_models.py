import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
from football.forecasting.features import FixtureFeatureSnapshotV1
from football.forecasting.model_contracts import ForecastInputSnapshot, ModelRunResult
from football.forecasting.model_runner import ModelRegistry, ModelRunner
from football.forecasting.runtime_models import ModelRegistration, load_registered_champion
from test_feature_snapshots import _input

REGISTRATION = Path("config/models/current-champion.json")


def _entry() -> ModelRegistration:
    return ModelRegistration.from_bytes(REGISTRATION.read_bytes())


def test_current_champion_registration_preserves_frozen_lineage() -> None:
    entry = _entry()
    assert entry.artifact_hash == "e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4"
    assert entry.training_cutoff == datetime.fromisoformat("2022-05-14T13:35:00+00:00")
    assert (
        entry.dependency_fingerprint
        == "d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e"
    )
    assert entry.calibrator_refs == ()
    assert entry.lifecycle_state == "CHAMPION"
    assert ModelRegistration.from_bytes(entry.to_bytes()) == entry


def test_registry_schema_and_bootstrap_forecast() -> None:
    from football.forecasting.runtime_models import model_registration_schema
    from jsonschema import Draft202012Validator, FormatChecker

    entry = _entry()
    schema = json.loads(Path("schemas/contracts/model-registration.schema.json").read_text())
    assert schema == model_registration_schema()
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(entry.to_dict())
    artifact = load_registered_champion(entry, Path("."))
    registry = ModelRegistry.from_registrations(
        (entry,),
        (TransferableRollingGoalsChampion(),),
        {artifact.artifact_sha256: artifact},
        enabled=frozenset((entry.model_id,)),
    )
    result = ModelRunner(registry).run(FixtureFeatureSnapshotV1(_input()))
    assert len(result.forecasts) == 1
    assert result.forecasts[0].model_artifact_sha256 == entry.artifact_hash
    assert registry.models[0].registration == entry


@pytest.mark.parametrize("field", ["artifact_hash", "model_id", "version", "feature_contract"])
def test_registration_cannot_announce_another_champion(field: str) -> None:
    value = _entry().to_dict()
    value[field] = "f" * 64 if field == "artifact_hash" else "different"
    with pytest.raises(ValueError, match="champion"):
        ModelRegistration.from_bytes(json.dumps(value).encode())


def test_corrupt_champion_bytes_reject_before_loading(tmp_path: Path) -> None:
    entry = _entry()
    path = tmp_path / entry.artifact_uri
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        load_registered_champion(entry, tmp_path)


def test_eligibility_and_retirement_are_enforced() -> None:
    from uuid import UUID

    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))

    def run(value: ModelRegistration) -> ModelRunResult:
        registry = ModelRegistry.from_registrations(
            (value,),
            (TransferableRollingGoalsChampion(),),
            {artifact.artifact_sha256: artifact},
            enabled=frozenset((entry.model_id,)),
        )
        return ModelRunner(registry).run(FixtureFeatureSnapshotV1(_input()))

    assert (
        run(replace(entry, eligible_competitions=(UUID(int=9),))).availability[0].reason
        == "COMPETITION_NOT_ELIGIBLE"
    )
    assert (
        run(replace(entry, eligible_products=("CORNERS_DISTRIBUTION",))).availability[0].reason
        == "PRODUCT_NOT_ELIGIBLE"
    )
    assert run(replace(entry, lifecycle_state="RETIRED")).availability[0].reason == "DISABLED"


def test_loaded_artifact_and_implementation_must_match_registration() -> None:
    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))
    with pytest.raises(ValueError, match="identity"):
        ModelRegistry.from_registrations(
            (entry,),
            (TransferableRollingGoalsChampion(),),
            {artifact.artifact_sha256: replace(artifact, dataset_sha256="f" * 64)},
            enabled=frozenset((entry.model_id,)),
        )
    registry = ModelRegistry.from_registrations(
        (entry,),
        (TransferableRollingGoalsChampion(),),
        {artifact.artifact_sha256: artifact},
        enabled=frozenset(),
    )
    assert not registry.models[0].enabled


def test_registration_rejects_extra_fields_duplicate_keys_and_invalid_intervals() -> None:
    entry = _entry()
    value = entry.to_dict()
    value["promoted"] = True
    with pytest.raises(ValueError):
        ModelRegistration.from_bytes(json.dumps(value).encode())
    with pytest.raises(ValueError):
        ModelRegistration.from_bytes(
            entry.to_bytes().replace(b'"model_id":', b'"model_id":"duplicate","model_id":')
        )
    with pytest.raises(ValueError):
        replace(entry, training_cutoff=entry.training_start.replace(year=2020))


def test_experiment_identity_includes_exact_runtime_registration(tmp_path: Path) -> None:
    from football.forecasting.experiments import run_experiment
    from football.storage.raw import ImmutableFileStore
    from test_experiments import _protocol

    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))
    results = []
    for registration in (entry, replace(entry, eligible_products=())):
        registry = ModelRegistry.from_registrations(
            (registration,),
            (TransferableRollingGoalsChampion(),),
            {artifact.artifact_sha256: artifact},
            enabled=frozenset((entry.model_id,)),
        )
        results.append(
            run_experiment(
                protocol=_protocol(),
                registry=registry,
                features=(FixtureFeatureSnapshotV1(_input()),),
                files=ImmutableFileStore(tmp_path),
                started_at=_input().knowledge_cutoff,
                code_git_sha="b" * 40,
                dependency_lock_sha256="c" * 64,
            )
        )
    assert results[0].run_id != results[1].run_id
    assert results[0].status == "SUCCEEDED" and results[1].status == "FAILED"


@pytest.mark.parametrize("runtime_metadata", [False, True])
@pytest.mark.parametrize("relation", ["after", "same_kickoff"])
def test_registered_artifact_trained_after_prediction_is_unavailable(
    runtime_metadata: bool,
    relation: str,
) -> None:
    from datetime import timedelta

    from football.forecasting.snapshot import build_forecast_snapshot

    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))
    original = _input()
    shift = original.football_cutoff - entry.training_cutoff
    if relation == "after":
        shift += timedelta(days=1)
    history = tuple(
        replace(row, kickoff_at=row.kickoff_at - shift, known_at=row.known_at - shift)
        for row in original.qualified_history
    )
    snapshot = build_forecast_snapshot(
        fixture_id=original.fixture_id,
        competition_id=original.competition_id,
        competition_context=original.competition_context,
        season_label="synthetic-earlier-season",
        kickoff_at=original.kickoff_at - shift,
        home_team_id=original.home_team_id,
        away_team_id=original.away_team_id,
        football_cutoff=original.football_cutoff - shift,
        knowledge_cutoff=original.knowledge_cutoff - shift,
        knowledge_mode=original.knowledge_mode,
        history=history,
    )
    registry = ModelRegistry.from_registrations(
        (entry,),
        (TransferableRollingGoalsChampion(),),
        {artifact.artifact_sha256: artifact},
        enabled=frozenset((entry.model_id,)),
    )
    if not runtime_metadata:
        from football.forecasting.model_runner import RegisteredModel

        registry = ModelRegistry(
            (RegisteredModel(TransferableRollingGoalsChampion(), artifact, True, 10),)
        )
    result = ModelRunner(registry).run(snapshot)
    assert result.forecasts == ()
    assert result.availability[0].reason == "ARTIFACT_TRAINING_NOT_BEFORE_FOOTBALL_CUTOFF"


def _early_knowledge_snapshot(knowledge_cutoff: datetime) -> ForecastInputSnapshot:
    from datetime import timedelta

    from football.forecasting.snapshot import build_forecast_snapshot

    original = _input()
    shift = max(row.known_at for row in original.qualified_history) - (
        knowledge_cutoff - timedelta(days=1)
    )
    history = tuple(
        replace(row, kickoff_at=row.kickoff_at - shift, known_at=row.known_at - shift)
        for row in original.qualified_history
    )
    return build_forecast_snapshot(
        fixture_id=original.fixture_id,
        competition_id=original.competition_id,
        competition_context=original.competition_context,
        season_label=original.season_label,
        kickoff_at=original.kickoff_at,
        home_team_id=original.home_team_id,
        away_team_id=original.away_team_id,
        football_cutoff=original.football_cutoff,
        knowledge_cutoff=knowledge_cutoff,
        knowledge_mode=original.knowledge_mode,
        history=history,
    )


@pytest.mark.parametrize("runtime_metadata", [False, True])
@pytest.mark.parametrize("relation", ["after", "same_kickoff"])
def test_artifact_training_must_precede_independent_knowledge_cutoff(
    runtime_metadata: bool, relation: str
) -> None:
    from datetime import timedelta

    from football.forecasting.model_runner import RegisteredModel

    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))
    known = entry.training_cutoff - (timedelta(days=1) if relation == "after" else timedelta(0))
    snapshot = _early_knowledge_snapshot(known)
    if runtime_metadata:
        registry = ModelRegistry.from_registrations(
            (entry,),
            (TransferableRollingGoalsChampion(),),
            {artifact.artifact_sha256: artifact},
            enabled=frozenset((entry.model_id,)),
        )
    else:
        registry = ModelRegistry(
            (RegisteredModel(TransferableRollingGoalsChampion(), artifact, True, 10),)
        )
    result = ModelRunner(registry).run(snapshot)
    assert result.forecasts == ()
    assert result.availability[0].reason == "ARTIFACT_TRAINING_NOT_BEFORE_KNOWLEDGE_CUTOFF"
