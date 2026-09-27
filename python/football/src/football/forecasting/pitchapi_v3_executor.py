"""Fail-closed orchestration for the frozen PitchAPI V3 evaluation."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3 import (
    PROTOCOL_ID,
    MatchHistoryFeaturesV1,
    TransferableForecastContextV1,
    TransferableGoalModelV1,
)
from football.forecasting.pitchapi_v3_evaluation import (
    EXPECTED_TARGETS,
    DomainMetricSeriesV1,
    ExactScoreDistributionV1,
    aggregate_domain_series,
    binary_auc,
    calibration_fit,
    descriptive_target_metrics,
    exact_distribution,
    paired_domain_bootstrap,
    reliability_diagram,
    score_target,
)

V4_PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4"
V5_PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V5"


class PitchApiV3ExecutionError(RuntimeError):
    """V3 execution stopped without publishing successful evidence."""


@dataclass(frozen=True, slots=True)
class PreparedTargetV1:
    context: TransferableForecastContextV1
    domain: str
    kickoff_batch: int
    features: MatchHistoryFeaturesV1


@dataclass(frozen=True, slots=True)
class ForecastBatchV1:
    batch_id: str
    targets: tuple[PreparedTargetV1, ...]


@dataclass(frozen=True, slots=True)
class RevealedOutcomeV1:
    match_id: str
    home_goals: int
    away_goals: int


@dataclass(frozen=True, slots=True)
class SimulationReceiptV1:
    target_id: str
    model_role: str
    seed_identity: str
    simulation_count: int
    input_sha256: str
    output_sha256: str
    rust_build_sha256: str
    status: str


@dataclass(frozen=True, slots=True)
class V4SimulationReceiptV1(SimulationReceiptV1):
    total_variation: float | None = None
    total_variation_limit: float | None = None
    warnings: tuple[str, ...] = ()


class EvaluationCorpusPort(Protocol):
    def preflight(self) -> Mapping[str, object]: ...

    def batches(self) -> Iterator[ForecastBatchV1]: ...

    def reveal_batch(self, batch_id: str) -> tuple[RevealedOutcomeV1, ...]: ...

    def heterogeneity(self) -> Mapping[str, object]: ...


class SimulationPort(Protocol):
    def validate(
        self,
        *,
        target: PreparedTargetV1,
        model_role: str,
        model_artifact_sha256: str,
        distribution: ExactScoreDistributionV1,
    ) -> SimulationReceiptV1: ...


@dataclass(frozen=True, slots=True)
class PitchApiV3ExecutionConfigV1:
    protocol_id: str
    policy_sha256: str
    preregistration_sha256: str
    snapshot_sha256: str
    corpus_sha256: str
    firewall_sha256: str
    alias_reconciliation_sha256: str
    reference_artifact_sha256: str
    challenger_artifact_sha256: str
    rust_policy_sha256: str
    rust_build_sha256: str
    executor_source_commit: str
    execution_configuration_sha256: str
    target_count: int = 712

    def __post_init__(self) -> None:
        if self.protocol_id != PROTOCOL_ID or self.target_count != 712:
            raise PitchApiV3ExecutionError("execution configuration identity is invalid")
        for name, value in asdict(self).items():
            if name.endswith("sha256") and (not isinstance(value, str) or not _is_hash(value)):
                raise PitchApiV3ExecutionError(f"{name} is not a SHA-256 identity")


@dataclass(frozen=True, slots=True)
class PitchApiV4ExecutionConfigV1(PitchApiV3ExecutionConfigV1):
    forecast_validation_count: int = 1_424

    def __post_init__(self) -> None:
        if (
            self.protocol_id != V4_PROTOCOL_ID
            or self.target_count != 712
            or self.forecast_validation_count != 1_424
        ):
            raise PitchApiV3ExecutionError("V4 execution configuration identity is invalid")
        for name, value in asdict(self).items():
            if name.endswith("sha256") and (not isinstance(value, str) or not _is_hash(value)):
                raise PitchApiV3ExecutionError(f"{name} is not a SHA-256 identity")


@dataclass(frozen=True, slots=True)
class PitchApiV5ExecutionConfigV1(PitchApiV3ExecutionConfigV1):
    forecast_validation_count: int = 1_424

    def __post_init__(self) -> None:
        if (
            self.protocol_id != V5_PROTOCOL_ID
            or self.target_count != 712
            or self.forecast_validation_count != 1_424
        ):
            raise PitchApiV3ExecutionError("V5 execution configuration identity is invalid")
        for name, value in asdict(self).items():
            if name.endswith("sha256") and (not isinstance(value, str) or not _is_hash(value)):
                raise PitchApiV3ExecutionError(f"{name} is not a SHA-256 identity")


@dataclass(frozen=True, slots=True)
class PublishedEvaluationV1:
    directory: Path
    machine_sha256: str
    human_sha256: str
    simulation_manifest_sha256: str
    execution_receipt_sha256: str | None = None


class PitchApiV3Executor:
    def __init__(
        self,
        *,
        config: PitchApiV3ExecutionConfigV1,
        reference_model: TransferableGoalModelV1,
        challenger_model: TransferableGoalModelV1,
        simulator: SimulationPort,
        corpus: EvaluationCorpusPort,
        accepted_simulation_statuses: frozenset[str] = frozenset({"PASS"}),
    ) -> None:
        self._config = config
        self._reference = reference_model
        self._challenger = challenger_model
        self._simulator = simulator
        self._corpus = corpus
        self._accepted_simulation_statuses = accepted_simulation_statuses

    def execute(
        self, *, run_id: str, execution_timestamp: datetime, output_root: Path
    ) -> PublishedEvaluationV1:
        if not run_id or execution_timestamp.tzinfo is None:
            raise PitchApiV3ExecutionError("run identity and aware timestamp are required")
        staging = output_root / ".staging" / run_id
        final = output_root / run_id
        failure = output_root / ".failures" / f"{run_id}.json"
        if staging.exists() or final.exists() or failure.exists():
            raise PitchApiV3ExecutionError(
                "run identity already exists; interrupted and failed runs require owner review"
            )
        staging.mkdir(parents=True)
        try:
            return self._execute_into(
                run_id=run_id,
                execution_timestamp=execution_timestamp,
                staging=staging,
                final=final,
            )
        except Exception as error:
            failure.parent.mkdir(parents=True, exist_ok=True)
            _write_json(
                failure,
                {
                    "contract": (
                        f"PitchApi{_protocol_version(self._config.protocol_id)}ExecutionFailureV1"
                    ),
                    "error": str(error),
                    "protocol_id": self._config.protocol_id,
                    "run_id": run_id,
                    "status": "FAIL_CLOSED_OWNER_REVIEW_REQUIRED",
                },
            )
            raise PitchApiV3ExecutionError(str(error)) from error

    def _execute_into(
        self,
        *,
        run_id: str,
        execution_timestamp: datetime,
        staging: Path,
        final: Path,
    ) -> PublishedEvaluationV1:
        preflight = dict(self._corpus.preflight())
        self._validate_preflight(preflight)
        target_records: list[dict[str, object]] = []
        simulation_receipts: list[SimulationReceiptV1] = []
        seen: set[str] = set()
        for batch in self._corpus.batches():
            forecasts: dict[str, tuple[ExactScoreDistributionV1, ExactScoreDistributionV1]] = {}
            for target in sorted(batch.targets, key=lambda item: str(item.context.match_id)):
                target_id = str(target.context.match_id)
                if target.domain not in EXPECTED_TARGETS or target_id in seen:
                    raise PitchApiV3ExecutionError("target domain or identity is invalid")
                reference = exact_distribution(self._reference.forecast_features(target.features))
                challenger = exact_distribution(self._challenger.forecast_features(target.features))
                forecasts[target_id] = reference, challenger
                for role, artifact, distribution in (
                    (
                        "REFERENCE",
                        self._config.reference_artifact_sha256,
                        reference,
                    ),
                    (
                        "CHALLENGER",
                        self._config.challenger_artifact_sha256,
                        challenger,
                    ),
                ):
                    receipt = self._simulator.validate(
                        target=target,
                        model_role=role,
                        model_artifact_sha256=artifact,
                        distribution=distribution,
                    )
                    if receipt.status not in self._accepted_simulation_statuses:
                        raise PitchApiV3ExecutionError("mandatory Rust simulation did not pass")
                    simulation_receipts.append(receipt)
                seen.add(target_id)
            outcomes = {item.match_id: item for item in self._corpus.reveal_batch(batch.batch_id)}
            if set(outcomes) != set(forecasts):
                raise PitchApiV3ExecutionError("revealed outcomes do not match sealed batch")
            for target in batch.targets:
                target_id = str(target.context.match_id)
                outcome = outcomes[target_id]
                reference, challenger = forecasts[target_id]
                target_records.append(
                    {
                        "challenger": score_target(
                            challenger,
                            home_goals=outcome.home_goals,
                            away_goals=outcome.away_goals,
                        ).to_dict(),
                        "domain": target.domain,
                        "descriptive_challenger": descriptive_target_metrics(
                            challenger,
                            home_goals=outcome.home_goals,
                            away_goals=outcome.away_goals,
                        ),
                        "descriptive_reference": descriptive_target_metrics(
                            reference,
                            home_goals=outcome.home_goals,
                            away_goals=outcome.away_goals,
                        ),
                        "kickoff_batch": target.kickoff_batch,
                        "reference": score_target(
                            reference,
                            home_goals=outcome.home_goals,
                            away_goals=outcome.away_goals,
                        ).to_dict(),
                        "target_id": target_id,
                        "one_x_two": {
                            "challenger": _outcome_probabilities(challenger),
                            "reference": _outcome_probabilities(reference),
                            "observed": _outcome_class(outcome.home_goals, outcome.away_goals),
                        },
                    }
                )
        if len(seen) != 712:
            raise PitchApiV3ExecutionError(f"expected 712 targets, got {len(seen)}")
        expected_receipts = 712 * 2
        if len(simulation_receipts) != expected_receipts:
            raise PitchApiV3ExecutionError("simulation receipt count is incomplete")
        report = _evaluation_report(target_records)
        v4_or_later = self._config.protocol_id in (V4_PROTOCOL_ID, V5_PROTOCOL_ID)
        version = _protocol_version(self._config.protocol_id)
        simulation_parity = _simulation_parity(simulation_receipts, v4=v4_or_later)
        simulation_manifest = {
            "contract": f"PitchApi{version}SimulationManifestV1",
            "receipts": [asdict(item) for item in simulation_receipts],
            "rust_build_sha256": self._config.rust_build_sha256,
            "simulation_count_per_forecast": 112_460,
            "summary": simulation_parity,
        }
        simulation_manifest_sha256 = _write_json(
            staging / "simulation-manifest.json", simulation_manifest
        )
        machine = {
            "aggregate_metrics": report["aggregate_metrics"],
            "alias_reconciliation_sha256": self._config.alias_reconciliation_sha256,
            "challenger_artifact_sha256": self._config.challenger_artifact_sha256,
            "challenger_satisfied_frozen_success_criteria": (
                report["result_classification"] == "PROMOTE_CANDIDATE" if v4_or_later else None
            ),
            "contract": f"PitchApiDomainStratifiedEvaluation{version}EvidenceV1",
            "corpus_sha256": self._config.corpus_sha256,
            "domain_metrics": report["domain_metrics"],
            "execution_configuration_sha256": self._config.execution_configuration_sha256,
            "execution_timestamp": execution_timestamp.isoformat(),
            "executor_source_commit": self._config.executor_source_commit,
            "firewall_sha256": self._config.firewall_sha256,
            "heterogeneity": dict(self._corpus.heterogeneity()),
            "preregistration_sha256": self._config.preregistration_sha256,
            "protocol_id": self._config.protocol_id,
            "reference_artifact_sha256": self._config.reference_artifact_sha256,
            "frozen_criteria_classification": report["result_classification"],
            "result_classification": (
                _v4_classification(str(report["result_classification"]))
                if v4_or_later
                else report["result_classification"]
            ),
            "run_id": run_id,
            "rust_build_sha256": self._config.rust_build_sha256,
            "rust_policy_sha256": self._config.rust_policy_sha256,
            "simulation_manifest_sha256": simulation_manifest_sha256,
            "simulation_parity": simulation_parity,
            "snapshot_sha256": self._config.snapshot_sha256,
            "target_count": len(seen),
            "target_results": target_records,
            "warnings_failures": report["warnings_failures"],
        }
        machine_sha256 = _write_json(staging / "evaluation-evidence.json", machine)
        human = _human_report(machine, machine_sha256, self._config.protocol_id)
        human_path = staging / "evaluation-evidence.md"
        human_path.write_text(human, encoding="utf-8")
        human_sha256 = hashlib.sha256(human_path.read_bytes()).hexdigest()
        execution_receipt_sha256 = _write_execution_receipt(
            staging=staging,
            config=self._config,
            run_id=run_id,
            target_count=len(seen),
            forecast_validation_count=len(simulation_receipts),
            machine_sha256=machine_sha256,
            human_sha256=human_sha256,
            simulation_manifest_sha256=simulation_manifest_sha256,
        )
        completion = {
            "execution_receipt_sha256": execution_receipt_sha256,
            "human_sha256": human_sha256,
            "machine_sha256": machine_sha256,
            "simulation_manifest_sha256": simulation_manifest_sha256,
            "status": "COMPLETE",
        }
        _write_json(staging / "COMPLETION.json", completion)
        _verify_staging(staging, completion)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, final)
        return PublishedEvaluationV1(
            directory=final,
            machine_sha256=machine_sha256,
            human_sha256=human_sha256,
            simulation_manifest_sha256=simulation_manifest_sha256,
            execution_receipt_sha256=execution_receipt_sha256,
        )

    def _validate_preflight(self, actual: Mapping[str, object]) -> None:
        expected = {
            "alias_reconciliation_sha256": self._config.alias_reconciliation_sha256,
            "corpus_sha256": self._config.corpus_sha256,
            "firewall_sha256": self._config.firewall_sha256,
            "protocol_id": self._config.protocol_id,
            "snapshot_sha256": self._config.snapshot_sha256,
            "target_count": 712,
        }
        if any(actual.get(key) != value for key, value in expected.items()):
            raise PitchApiV3ExecutionError("corpus preflight identity mismatch")


def _evaluation_report(records: list[dict[str, object]]) -> dict[str, object]:
    metrics = (
        "joint_score_log_loss",
        "one_x_two_log_loss",
        "one_x_two_brier",
        "one_x_two_rps",
        "total_goal_crps",
    )
    domains: dict[str, object] = {}
    aggregate: dict[str, object] = {}
    for metric in metrics:
        series = _domain_series(records, metric)
        bootstrap = paired_domain_bootstrap(series)
        summary = aggregate_domain_series(series)
        aggregate[metric] = {
            "macro_delta": summary.macro_delta,
            "macro_interval_95": list(bootstrap.macro_interval),
            "weighted_delta": summary.weighted_delta,
            "weighted_interval_95": list(bootstrap.weighted_interval),
        }
        for domain in EXPECTED_TARGETS:
            domain_report = domains.setdefault(domain, {"metrics": {}})
            assert isinstance(domain_report, dict)
            metric_reports = domain_report["metrics"]
            assert isinstance(metric_reports, dict)
            metric_reports[metric] = {
                "challenger": sum(series[domain].challenger) / EXPECTED_TARGETS[domain],
                "delta": series[domain].point_delta,
                "delta_interval_95": list(bootstrap.domain_intervals[domain]),
                "reference": sum(series[domain].reference) / EXPECTED_TARGETS[domain],
            }
    for domain in EXPECTED_TARGETS:
        domain_records = [row for row in records if row["domain"] == domain]
        domains[domain]["calibration"] = _calibration_report(domain_records)  # type: ignore[index]
        domains[domain]["descriptive"] = _descriptive_report(domain_records)  # type: ignore[index]
        domains[domain]["target_count"] = len(domain_records)  # type: ignore[index]
    classification, findings = _classify(aggregate, domains)
    return {
        "aggregate_metrics": aggregate,
        "domain_metrics": domains,
        "result_classification": classification,
        "warnings_failures": findings,
    }


def _domain_series(
    records: list[dict[str, object]], metric: str
) -> dict[str, DomainMetricSeriesV1]:
    output: dict[str, DomainMetricSeriesV1] = {}
    for domain in EXPECTED_TARGETS:
        rows = sorted(
            (row for row in records if row["domain"] == domain),
            key=lambda row: (cast(int, row["kickoff_batch"]), str(row["target_id"])),
        )
        output[domain] = DomainMetricSeriesV1(
            reference=tuple(float(row["reference"][metric]) for row in rows),  # type: ignore[index]
            challenger=tuple(float(row["challenger"][metric]) for row in rows),  # type: ignore[index]
            kickoff_batches=tuple(cast(int, row["kickoff_batch"]) for row in rows),
        )
    return output


def _calibration_report(records: list[dict[str, object]]) -> dict[str, object]:
    report: dict[str, object] = {}
    for role in ("reference", "challenger"):
        role_report: dict[str, object] = {}
        for index, outcome_name in enumerate(("away", "draw", "home")):
            probabilities = tuple(float(row["one_x_two"][role][index]) for row in records)  # type: ignore[index]
            outcomes = tuple(int(row["one_x_two"]["observed"] == index) for row in records)  # type: ignore[index]
            fit = calibration_fit(probabilities, outcomes)
            role_report[outcome_name] = {
                "fit": asdict(fit),
                "reliability": reliability_diagram(probabilities, outcomes),
            }
        report[role] = role_report
    return report


def _descriptive_report(records: list[dict[str, object]]) -> dict[str, object]:
    report: dict[str, object] = {}
    for role in ("reference", "challenger"):
        binary_report: dict[str, object] = {}
        source_key = f"descriptive_{role}"
        for market in (
            "btts",
            "over_0.5",
            "under_0.5",
            "over_1.5",
            "under_1.5",
            "over_2.5",
            "under_2.5",
            "over_3.5",
            "under_3.5",
            "over_4.5",
            "under_4.5",
        ):
            values = [row[source_key]["binary_markets"][market] for row in records]  # type: ignore[index]
            probabilities = tuple(float(value["probability"]) for value in values)
            outcomes = tuple(int(value["outcome"]) for value in values)
            binary_report[market] = {
                "auc": binary_auc(probabilities, outcomes),
                "brier": sum(float(value["brier"]) for value in values) / len(values),
                "log_loss": sum(float(value["log_loss"]) for value in values) / len(values),
            }
        interval_report: dict[str, object] = {}
        for level in ("50", "90"):
            values = [row[source_key]["prediction_intervals"][level] for row in records]  # type: ignore[index]
            interval_report[level] = {
                "coverage": sum(int(value["covered"]) for value in values) / len(values),
                "mean_width": sum(int(value["width"]) for value in values) / len(values),
            }
        report[role] = {
            "binary_markets": binary_report,
            "prediction_intervals": interval_report,
        }
    return report


def _classify(
    aggregate: Mapping[str, object], domains: Mapping[str, object]
) -> tuple[str, list[str]]:
    findings: list[str] = []
    primary = aggregate["joint_score_log_loss"]
    assert isinstance(primary, dict)
    if primary["macro_delta"] > -0.01 or primary["macro_interval_95"][1] >= 0.0:
        findings.append("MACRO_PRIMARY_NOT_MET")
    limits = {
        "one_x_two_log_loss": 0.02,
        "one_x_two_brier": 0.01,
        "one_x_two_rps": 0.01,
        "total_goal_crps": 0.02,
    }
    for metric, limit in limits.items():
        value = aggregate[metric]
        assert isinstance(value, dict)
        if value["macro_interval_95"][1] > limit:
            findings.append(f"MACRO_GUARDRAIL_FAILED:{metric}")
    for domain, value in domains.items():
        assert isinstance(value, dict)
        interval = value["metrics"]["joint_score_log_loss"]["delta_interval_95"]
        if interval[1] > 0.05:
            findings.append(f"DOMAIN_LOG_LOSS_GUARDRAIL_FAILED:{domain}")
        findings.extend(_calibration_findings(domain, value))
    if any("FAILED" in finding for finding in findings):
        return "REJECT", findings
    if "MACRO_PRIMARY_NOT_MET" in findings:
        return "RETAIN_CHAMPION", findings
    return "PROMOTE_CANDIDATE", findings


def _calibration_findings(domain: str, value: Mapping[str, object]) -> list[str]:
    findings: list[str] = []
    calibration = value["calibration"]
    assert isinstance(calibration, dict)
    for outcome in ("away", "draw", "home"):
        reference = calibration["reference"][outcome]["fit"]
        challenger = calibration["challenger"][outcome]["fit"]
        if abs(challenger["intercept"]) - abs(reference["intercept"]) > 0.05:
            findings.append(f"CALIBRATION_INTERCEPT_FAILED:{domain}:{outcome}")
        if abs(challenger["slope"] - 1.0) - abs(reference["slope"] - 1.0) > 0.1:
            findings.append(f"CALIBRATION_SLOPE_FAILED:{domain}:{outcome}")
    return findings


def _outcome_probabilities(distribution: ExactScoreDistributionV1) -> tuple[float, ...]:
    away = sum(value for home, goals, value in distribution.atoms if home < goals)
    draw = sum(value for home, goals, value in distribution.atoms if home == goals)
    home = sum(value for goals, away_goals, value in distribution.atoms if goals > away_goals)
    return away, draw, home


def _outcome_class(home_goals: int, away_goals: int) -> int:
    return 2 if home_goals > away_goals else 1 if home_goals == away_goals else 0


def _write_json(path: Path, payload: Mapping[str, object]) -> str:
    content = canonical_json_bytes(dict(payload)) + b"\n"
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _verify_staging(staging: Path, completion: Mapping[str, object]) -> None:
    expected = {
        "evaluation-evidence.json": completion["machine_sha256"],
        "evaluation-evidence.md": completion["human_sha256"],
        "simulation-manifest.json": completion["simulation_manifest_sha256"],
    }
    if completion.get("execution_receipt_sha256") is not None:
        expected["execution-receipt.json"] = completion["execution_receipt_sha256"]
    for name, digest in expected.items():
        if hashlib.sha256((staging / name).read_bytes()).hexdigest() != digest:
            raise PitchApiV3ExecutionError(f"staging artifact hash mismatch: {name}")
    parsed = json.loads((staging / "evaluation-evidence.json").read_text(encoding="utf-8"))
    if parsed["target_count"] != 712:
        raise PitchApiV3ExecutionError("staging evidence is incomplete")


def _human_report(machine: Mapping[str, object], machine_sha256: str, protocol_id: str) -> str:
    version = _protocol_version(protocol_id)
    return (
        f"# PitchAPI domain-stratified evaluation {version}\n\n"
        f"Protocol: `{protocol_id}`\n\n"
        f"Result: `{machine['result_classification']}`\n\n"
        f"Targets: `{machine['target_count']}`\n\n"
        f"Machine evidence SHA-256: `{machine_sha256}`\n\n"
        "Domain and aggregate results are recorded without pooling source distributions.\n"
    )


class PitchApiV4Executor(PitchApiV3Executor):
    def __init__(
        self,
        *,
        config: PitchApiV4ExecutionConfigV1,
        reference_model: TransferableGoalModelV1,
        challenger_model: TransferableGoalModelV1,
        simulator: SimulationPort,
        corpus: EvaluationCorpusPort,
    ) -> None:
        super().__init__(
            config=config,
            reference_model=reference_model,
            challenger_model=challenger_model,
            simulator=simulator,
            corpus=corpus,
            accepted_simulation_statuses=frozenset({"PASS", "PASS_WITH_WARNINGS"}),
        )


class PitchApiV5Executor(PitchApiV3Executor):
    def __init__(
        self,
        *,
        config: PitchApiV5ExecutionConfigV1,
        reference_model: TransferableGoalModelV1,
        challenger_model: TransferableGoalModelV1,
        simulator: SimulationPort,
        corpus: EvaluationCorpusPort,
    ) -> None:
        super().__init__(
            config=config,
            reference_model=reference_model,
            challenger_model=challenger_model,
            simulator=simulator,
            corpus=corpus,
            accepted_simulation_statuses=frozenset({"PASS", "PASS_WITH_WARNINGS"}),
        )


def _is_hash(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _protocol_version(protocol_id: str) -> str:
    if protocol_id == V5_PROTOCOL_ID:
        return "V5"
    if protocol_id == V4_PROTOCOL_ID:
        return "V4"
    if protocol_id == PROTOCOL_ID:
        return "V3"
    raise PitchApiV3ExecutionError("unknown evaluation protocol identity")


def _v4_classification(classification: str) -> str:
    return {
        "PROMOTE_CANDIDATE": "CHALLENGER_SUPPORTED",
        "RETAIN_CHAMPION": "REFERENCE_RETAINED",
        "REJECT": "REFERENCE_RETAINED",
    }[classification]


def _simulation_parity(receipts: list[SimulationReceiptV1], *, v4: bool) -> dict[str, object]:
    status_counts = {
        status: sum(receipt.status == status for receipt in receipts)
        for status in sorted({receipt.status for receipt in receipts})
    }
    v4_receipts = [receipt for receipt in receipts if isinstance(receipt, V4SimulationReceiptV1)]
    tv_values = [
        receipt.total_variation for receipt in v4_receipts if receipt.total_variation is not None
    ]
    return {
        "forecast_validation_count": len(receipts),
        "maximum_observed_total_variation": max(tv_values) if tv_values else None,
        "status": "PASS_WITH_WARNINGS" if status_counts.get("PASS_WITH_WARNINGS", 0) else "PASS",
        "status_counts": status_counts,
        "total_variation_limit": 0.012794580429261083 if v4 else None,
        "warning_count": sum(len(receipt.warnings) for receipt in v4_receipts),
    }


def _write_execution_receipt(
    *,
    staging: Path,
    config: PitchApiV3ExecutionConfigV1,
    run_id: str,
    target_count: int,
    forecast_validation_count: int,
    machine_sha256: str,
    human_sha256: str,
    simulation_manifest_sha256: str,
) -> str | None:
    if config.protocol_id not in (V4_PROTOCOL_ID, V5_PROTOCOL_ID):
        return None
    version = _protocol_version(config.protocol_id)
    return _write_json(
        staging / "execution-receipt.json",
        {
            "contract": f"PitchApiDomainStratifiedEvaluation{version}ExecutionReceiptV1",
            "execution_configuration_sha256": config.execution_configuration_sha256,
            "forecast_validation_count": forecast_validation_count,
            "human_sha256": human_sha256,
            "machine_sha256": machine_sha256,
            "protocol_id": config.protocol_id,
            "run_id": run_id,
            "simulation_manifest_sha256": simulation_manifest_sha256,
            "status": "COMPLETE",
            "target_count": target_count,
        },
    )
