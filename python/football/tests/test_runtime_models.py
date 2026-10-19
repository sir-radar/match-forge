import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import pytest
from football.forecasting.champion_adapter import TransferableRollingGoalsChampion
from football.forecasting.features import FixtureFeatureSnapshotV1
from football.forecasting.model_contracts import ModelRunResult
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
