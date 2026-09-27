from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.pitchapi_v3 import (
    MatchHistoryFeaturesV1,
    TeamHistoryFeaturesV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
    TransferableParametersV1,
)
from football.forecasting.pitchapi_v3_executor import (
    ForecastBatchV1,
    PitchApiV3ExecutionConfigV1,
    PitchApiV3ExecutionError,
    PitchApiV3Executor,
    PitchApiV4ExecutionConfigV1,
    PitchApiV4Executor,
    PreparedTargetV1,
    RevealedOutcomeV1,
    SimulationReceiptV1,
    V4SimulationReceiptV1,
)

_HASH = "a" * 64


class _SyntheticCorpus:
    def __init__(
        self, count: int = 712, protocol_id: str = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3"
    ) -> None:
        self.count = count
        self.protocol_id = protocol_id
        self.revealed = False

    def preflight(self) -> dict[str, object]:
        return {
            "alias_reconciliation_sha256": _HASH,
            "corpus_sha256": _HASH,
            "firewall_sha256": _HASH,
            "protocol_id": self.protocol_id,
            "snapshot_sha256": _HASH,
            "target_count": self.count,
        }

    def batches(self):  # type: ignore[no-untyped-def]
        domains = [
            *("bundesliga_2022_23" for _ in range(216)),
            *("bundesliga_2023_24" for _ in range(216)),
            *("ligue1_2022_23" for _ in range(280)),
        ][: self.count]
        targets = tuple(
            PreparedTargetV1(
                context=TransferableForecastContextV1(
                    match_id=UUID(int=index + 1),
                    scope_key=domain,
                    kickoff_at=datetime(2026, 1, 1, tzinfo=UTC),
                    home_team_id=UUID(int=10_000 + index * 2),
                    away_team_id=UUID(int=10_001 + index * 2),
                ),
                domain=domain,
                kickoff_batch=index,
                features=MatchHistoryFeaturesV1(
                    TeamHistoryFeaturesV1(10, 1.4, 1.2, 1.3),
                    TeamHistoryFeaturesV1(10, 1.1, 1.5, 1.0),
                ),
            )
            for index, domain in enumerate(domains)
        )
        yield ForecastBatchV1("batch", targets)

    def reveal_batch(self, batch_id: str) -> tuple[RevealedOutcomeV1, ...]:
        assert batch_id == "batch"
        self.revealed = True
        return tuple(
            RevealedOutcomeV1(str(UUID(int=index + 1)), index % 3, (index + 1) % 2)
            for index in range(self.count)
        )

    def heterogeneity(self) -> dict[str, object]:
        return {"classification": "SYNTHETIC_IMPLEMENTATION_DIAGNOSTIC"}


class _Simulator:
    def validate(self, *, target, model_role, model_artifact_sha256, distribution):  # type: ignore[no-untyped-def]
        digest = str(target.context.match_id).replace("-", "")[:32].ljust(64, "0")
        return SimulationReceiptV1(
            target_id=str(target.context.match_id),
            model_role=model_role,
            seed_identity=digest,
            simulation_count=112_460,
            input_sha256=digest,
            output_sha256=digest,
            rust_build_sha256=_HASH,
            status="PASS",
        )


class _V4Simulator:
    def validate(self, *, target, model_role, model_artifact_sha256, distribution):  # type: ignore[no-untyped-def]
        digest = str(target.context.match_id).replace("-", "")[:32].ljust(64, "0")
        return V4SimulationReceiptV1(
            target_id=str(target.context.match_id),
            model_role=model_role,
            seed_identity=digest,
            simulation_count=112_460,
            input_sha256=digest,
            output_sha256=digest,
            rust_build_sha256=_HASH,
            status="PASS_WITH_WARNINGS",
            total_variation=0.006,
            total_variation_limit=0.012794580429261083,
            warnings=("diagnostic warning",),
        )


def _executor(corpus: _SyntheticCorpus) -> PitchApiV3Executor:
    parameters = TransferableParametersV1(0.2, 0.0, 0.4, 0.3, 0.0, 1.3, 1.2)
    config = PitchApiV3ExecutionConfigV1(
        protocol_id="PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3",
        policy_sha256=_HASH,
        preregistration_sha256=_HASH,
        snapshot_sha256=_HASH,
        corpus_sha256=_HASH,
        firewall_sha256=_HASH,
        alias_reconciliation_sha256=_HASH,
        reference_artifact_sha256=_HASH,
        challenger_artifact_sha256=_HASH,
        rust_policy_sha256=_HASH,
        rust_build_sha256=_HASH,
        executor_source_commit="b" * 40,
        execution_configuration_sha256=_HASH,
    )
    return PitchApiV3Executor(
        config=config,
        reference_model=TransferableGoalModelV1(parameters),
        challenger_model=TransferableGoalModelV1(parameters),
        simulator=_Simulator(),
        corpus=corpus,
    )


def test_executor_publishes_atomically_for_712_target_shape(tmp_path: Path) -> None:
    corpus = _SyntheticCorpus()

    result = _executor(corpus).execute(
        run_id="synthetic",
        execution_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        output_root=tmp_path,
    )

    assert corpus.revealed
    assert result.directory.is_dir()
    assert not (tmp_path / ".staging" / "synthetic").exists()
    assert (result.directory / "COMPLETION.json").is_file()


def test_executor_fails_before_outcomes_on_preflight_mismatch(tmp_path: Path) -> None:
    corpus = _SyntheticCorpus(count=711)

    with pytest.raises(PitchApiV3ExecutionError, match="preflight identity mismatch"):
        _executor(corpus).execute(
            run_id="bad", execution_timestamp=datetime(2026, 1, 1, tzinfo=UTC), output_root=tmp_path
        )

    assert not corpus.revealed
    assert not (tmp_path / "bad").exists()
    assert (tmp_path / ".failures" / "bad.json").is_file()


def test_v4_executor_accepts_diagnostic_warnings_and_records_tv(tmp_path: Path) -> None:
    corpus = _SyntheticCorpus(protocol_id="PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4")
    parameters = TransferableParametersV1(0.2, 0.0, 0.4, 0.3, 0.0, 1.3, 1.2)
    config = PitchApiV4ExecutionConfigV1(
        protocol_id="PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4",
        policy_sha256=_HASH,
        preregistration_sha256=_HASH,
        snapshot_sha256=_HASH,
        corpus_sha256=_HASH,
        firewall_sha256=_HASH,
        alias_reconciliation_sha256=_HASH,
        reference_artifact_sha256=_HASH,
        challenger_artifact_sha256=_HASH,
        rust_policy_sha256=_HASH,
        rust_build_sha256=_HASH,
        executor_source_commit="b" * 40,
        execution_configuration_sha256=_HASH,
    )
    executor = PitchApiV4Executor(
        config=config,
        reference_model=TransferableGoalModelV1(parameters),
        challenger_model=TransferableGoalModelV1(parameters),
        simulator=_V4Simulator(),
        corpus=corpus,
    )

    result = executor.execute(
        run_id="synthetic-v4",
        execution_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        output_root=tmp_path,
    )

    manifest = (result.directory / "simulation-manifest.json").read_text(encoding="utf-8")
    evidence = (result.directory / "evaluation-evidence.json").read_text(encoding="utf-8")
    assert '"contract":"PitchApiV4SimulationManifestV1"' in manifest
    assert '"total_variation":0.006' in manifest
    assert '"contract":"PitchApiDomainStratifiedEvaluationV4EvidenceV1"' in evidence
