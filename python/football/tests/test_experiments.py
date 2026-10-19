from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.contracts.decisions import DecisionRecordV1
from football.forecasting.champion_adapter import (
    TransferableRollingGoalsChampion,
    load_champion_artifact,
)
from football.forecasting.experiments import (
    ExperimentArtifact,
    ExperimentProtocolV1,
    ExperimentRun,
    record_experiment_decision,
    run_experiment,
)
from football.forecasting.features import FixtureFeatureSnapshotV1
from football.forecasting.model_runner import ModelRegistry, RegisteredModel
from football.product.domain import MODEL_ARTIFACT_PATH
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore
from test_feature_snapshots import _input


def _protocol() -> ExperimentProtocolV1:
    policy = ExperimentArtifact("retained/policy.json", "a" * 64)
    return ExperimentProtocolV1(
        protocol_id="synthetic-development-control",
        hypothesis="The frozen champion reproduces its approved inputs.",
        development_corpus=(_input().fixture_id,),
        validation_corpus=(UUID(int=2_000_000),),
        evaluation_corpus=(UUID(int=3_000_000),),
        forbidden_target_manifest=(UUID(int=4_000_000),),
        feature_contract="fixture-features-v1",
        candidate_models=(TransferableRollingGoalsChampion.model_id,),
        fit_policy=policy,
        calibration_policy=policy,
        evaluation_policy=policy,
        promotion_policy=policy,
        authorization_refs=(policy,),
    )


def _registry() -> ModelRegistry:
    return ModelRegistry(
        (
            RegisteredModel(
                TransferableRollingGoalsChampion(),
                load_champion_artifact(MODEL_ARTIFACT_PATH, _input().qualified_history),
                True,
                10,
            ),
        )
    )


def _run(
    root: Path,
    *,
    protocol: ExperimentProtocolV1 | None = None,
    registry: ModelRegistry | None = None,
    features: tuple[FixtureFeatureSnapshotV1, ...] | None = None,
    started_at: datetime | None = None,
    code_git_sha: str = "b" * 40,
    dependency_lock_sha256: str = "c" * 64,
) -> ExperimentRun:
    return run_experiment(
        protocol=protocol or _protocol(),
        registry=registry or _registry(),
        features=features if features is not None else (FixtureFeatureSnapshotV1(_input()),),
        files=ImmutableFileStore(root),
        started_at=started_at or _input().knowledge_cutoff,
        code_git_sha=code_git_sha,
        dependency_lock_sha256=dependency_lock_sha256,
    )


def test_experiment_contract_round_trip_and_frozen_schema() -> None:
    import json

    from football.forecasting.experiments import experiment_protocol_schema
    from jsonschema import Draft202012Validator, FormatChecker

    protocol = _protocol()
    assert ExperimentProtocolV1.from_bytes(protocol.to_bytes()) == protocol
    schema = json.loads(Path("schemas/contracts/experiment-protocol-v1.schema.json").read_text())
    assert schema == experiment_protocol_schema()
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(protocol.to_dict())
    with pytest.raises(ValueError):
        ExperimentProtocolV1.from_bytes(
            protocol.to_bytes().replace(b'"contract":', b'"extra":0,"contract":')
        )


def test_experiment_retry_preserves_run_and_all_artifact_bytes(tmp_path: Path) -> None:
    first = _run(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    second = _run(tmp_path)
    assert first == second
    assert first.status == "SUCCEEDED"
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    assert first.protocol_sha256 == _protocol().sha256
    assert first.result_artifact.sha256 == first.result_sha256


def test_development_corpus_cannot_overlap_sealed_or_other_partitions() -> None:
    p = _protocol()
    for changed in (
        {"validation_corpus": p.development_corpus},
        {"evaluation_corpus": p.development_corpus},
        {"forbidden_target_manifest": p.development_corpus},
    ):
        payload = p.to_dict()
        payload.update({name: [str(value) for value in values] for name, values in changed.items()})
        import json

        with pytest.raises(ValueError, match="overlap"):
            ExperimentProtocolV1.from_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize("target", [UUID(int=2_000_000), UUID(int=3_000_000), UUID(int=4_000_000)])
def test_non_development_target_rejected_before_models_or_files(
    tmp_path: Path, target: UUID
) -> None:
    feature = FixtureFeatureSnapshotV1(replace(_input(), fixture_id=target))
    with pytest.raises(ValueError, match="development"):
        _run(tmp_path, features=(feature,))
    assert not list(tmp_path.rglob("*.json"))


def test_protected_history_rejected_before_model_callback(tmp_path: Path) -> None:
    source = _input()
    protocol = replace(
        _protocol(), forbidden_target_manifest=(source.qualified_history[0].fixture_id,)
    )
    with pytest.raises(ValueError, match="protected history"):
        _run(tmp_path, protocol=protocol)
    assert not list(tmp_path.rglob("*.json"))


def test_protocol_cannot_expand_candidates_or_accept_disabled_models(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="candidate"):
        _run(tmp_path, protocol=replace(_protocol(), candidate_models=("unapproved-model",)))
    with pytest.raises(ValueError, match="enabled"):
        _run(tmp_path, registry=ModelRegistry((replace(_registry().models[0], enabled=False),)))


def test_missing_fit_is_an_explicit_failed_run(tmp_path: Path) -> None:
    result = _run(
        tmp_path, registry=ModelRegistry((replace(_registry().models[0], artifact=None),))
    )
    assert result.status == "FAILED"
    assert b"NO_ELIGIBLE_FITTED_ARTIFACT" in (tmp_path / result.result_artifact.uri).read_bytes()


def test_changed_dependency_or_feature_changes_run_identity(tmp_path: Path) -> None:
    first = _run(tmp_path)
    second = _run(tmp_path, dependency_lock_sha256="d" * 64)
    assert first.run_id != second.run_id
    feature = FixtureFeatureSnapshotV1(_input(), quality=("REVIEWED",))
    third = _run(tmp_path, features=(feature,))
    assert first.run_id != third.run_id


def test_corrupted_output_cannot_be_silently_reused(tmp_path: Path) -> None:
    result = _run(tmp_path)
    (tmp_path / result.result_artifact.uri).write_bytes(b"corruption")
    with pytest.raises(ImmutableFileConflict):
        _run(tmp_path)


def test_decision_binds_exact_run_and_does_not_promote(tmp_path: Path) -> None:
    run = _run(tmp_path)
    decision = DecisionRecordV1(
        decision_type="experiment",
        subject_type="experiment_run",
        subject_id=str(run.run_id),
        decided_at=_input().knowledge_cutoff + timedelta(seconds=1),
        disposition="RETAIN_CONTROL",
        reason="Synthetic development evidence only.",
        evidence={"result_sha256": run.result_sha256},
    )
    result = record_experiment_decision(run, decision, ImmutableFileStore(tmp_path))
    assert result.decision == decision
    assert result.artifact.sha256 == decision.sha256
    assert result == record_experiment_decision(run, decision, ImmutableFileStore(tmp_path))
    with pytest.raises(ValueError, match="run"):
        record_experiment_decision(
            run, replace(decision, subject_id=str(UUID(int=9))), ImmutableFileStore(tmp_path)
        )
    with pytest.raises(ValueError, match="result"):
        record_experiment_decision(
            run, replace(decision, evidence={}), ImmutableFileStore(tmp_path)
        )


def test_run_identity_validation_precedes_publication(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _run(tmp_path, code_git_sha="bad")
    with pytest.raises(ValueError):
        _run(tmp_path, dependency_lock_sha256="bad")
    with pytest.raises(ValueError):
        _run(tmp_path, started_at=_input().knowledge_cutoff.replace(tzinfo=None))
    assert not list(tmp_path.rglob("*.json"))


def test_eligibility_settings_are_part_of_run_identity(tmp_path: Path) -> None:
    first = _run(tmp_path)
    changed = ModelRegistry((replace(_registry().models[0], minimum_team_history=99),))
    second = _run(tmp_path, registry=changed)
    assert first.run_id != second.run_id
    assert second.status == "FAILED"


def test_duplicate_ids_unknown_contract_and_empty_candidates_reject(tmp_path: Path) -> None:
    p = _protocol()
    with pytest.raises(ValueError):
        replace(p, development_corpus=p.development_corpus * 2)
    with pytest.raises(ValueError):
        replace(p, candidate_models=())
    with pytest.raises(ValueError, match="contract"):
        _run(tmp_path, protocol=replace(p, feature_contract="unknown"))
    with pytest.raises(ValueError, match="development"):
        _run(tmp_path, features=())
    assert not list(tmp_path.rglob("*.json"))


def test_result_identity_mismatch_cannot_be_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.forecasting.model_contracts import ModelRunResult
    from football.forecasting.model_runner import ModelRunner

    original = ModelRunner.run

    def wrong(self: ModelRunner, fixture: FixtureFeatureSnapshotV1) -> ModelRunResult:
        result = original(self, fixture)
        return replace(result, forecasts=(replace(result.forecasts[0], fixture_id=UUID(int=9)),))

    monkeypatch.setattr(ModelRunner, "run", wrong)
    with pytest.raises(ValueError, match="identity"):
        _run(tmp_path)
    assert not list(tmp_path.rglob("run.json"))


def test_decision_rejects_changed_published_run(tmp_path: Path) -> None:
    run = _run(tmp_path)
    decision = DecisionRecordV1(
        decision_type="experiment",
        subject_type="experiment_run",
        subject_id=str(run.run_id),
        decided_at=_input().knowledge_cutoff,
        disposition="RETAIN_CONTROL",
        reason="Synthetic.",
        evidence={"result_sha256": run.result_sha256},
    )
    with pytest.raises(ValueError, match="published"):
        record_experiment_decision(
            replace(run, status="FAILED"), decision, ImmutableFileStore(tmp_path)
        )


def test_protocol_rejects_duplicate_json_fields() -> None:
    raw = _protocol().to_bytes().replace(b'"contract":', b'"protocol_id":"duplicate","contract":')
    with pytest.raises(ValueError, match="duplicate"):
        ExperimentProtocolV1.from_bytes(raw)


def test_artifact_and_execution_clocks_are_checked_before_publication(tmp_path: Path) -> None:
    registered = _registry().models[0]
    assert registered.artifact is not None
    with pytest.raises(ValueError, match="artifact identity"):
        _run(
            tmp_path,
            registry=ModelRegistry(
                (replace(registered, artifact=replace(registered.artifact, model_id="other")),)
            ),
        )
    with pytest.raises(ValueError, match="training"):
        _run(
            tmp_path,
            registry=ModelRegistry(
                (
                    replace(
                        registered,
                        artifact=replace(
                            registered.artifact,
                            training_cutoff=_input().football_cutoff + timedelta(seconds=1),
                        ),
                    ),
                )
            ),
        )
    with pytest.raises(ValueError, match="knowledge"):
        _run(tmp_path, started_at=_input().knowledge_cutoff - timedelta(seconds=1))
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize(
    "invalid", ["missing_availability", "missing_forecast", "duplicate_forecast"]
)
def test_incomplete_model_result_cannot_claim_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    from football.forecasting.model_contracts import ModelRunResult
    from football.forecasting.model_runner import ModelRunner

    original = ModelRunner.run

    def wrong(self: ModelRunner, fixture: FixtureFeatureSnapshotV1) -> ModelRunResult:
        result = original(self, fixture)
        if invalid == "missing_availability":
            return replace(result, availability=())
        return replace(
            result, forecasts=() if invalid == "missing_forecast" else result.forecasts * 2
        )

    monkeypatch.setattr(ModelRunner, "run", wrong)
    with pytest.raises(ValueError):
        _run(tmp_path)
    assert not list(tmp_path.rglob("run.json"))


def test_same_kickoff_fitted_artifact_is_rejected_before_publication(tmp_path: Path) -> None:
    registered = _registry().models[0]
    assert registered.artifact is not None
    invalid = replace(
        registered, artifact=replace(registered.artifact, training_cutoff=_input().football_cutoff)
    )
    with pytest.raises(ValueError, match="training"):
        _run(tmp_path, registry=ModelRegistry((invalid,)))
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("relation", ["after", "same_kickoff"])
def test_fitted_artifact_respects_independent_knowledge_cutoff(
    tmp_path: Path, relation: str
) -> None:
    from football.forecasting.runtime_models import load_registered_champion
    from test_runtime_models import _early_knowledge_snapshot, _entry

    entry = _entry()
    artifact = load_registered_champion(entry, Path("."))
    known = entry.training_cutoff - (timedelta(days=1) if relation == "after" else timedelta(0))
    snapshot = _early_knowledge_snapshot(known)
    registry = ModelRegistry(
        (RegisteredModel(TransferableRollingGoalsChampion(), artifact, True, 10),)
    )
    with pytest.raises(ValueError, match="training"):
        _run(tmp_path, registry=registry, features=(FixtureFeatureSnapshotV1(snapshot),))
    assert not list(tmp_path.rglob("*.json"))
