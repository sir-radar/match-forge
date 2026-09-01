from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.forecasting.contracts import MatchResultProbabilitiesV1, PointInTimeScopeV1
from football.forecasting.evaluation import (
    EvaluatedMatchResultV1,
    MatchOutcome,
    MatchResultMetricsV1,
    evaluate_match_results,
)
from football.forecasting.governance import (
    EvaluationCorpusV1,
    EvaluationCoverageV1,
    GovernanceContractError,
    ImmutableEvaluationReportStore,
    ModelPromotionEventV1,
    Sprint2EvaluationReportV1,
)
from football.storage.raw import ImmutableFileConflict
from jsonschema import Draft202012Validator, FormatChecker

DATASET_ID = UUID("10000000-0000-4000-8000-000000000001")
SNAPSHOT_ID = UUID("20000000-0000-4000-8000-000000000001")
ARTIFACT_ID = UUID("30000000-0000-4000-8000-000000000001")
EVALUATION_ID = UUID("40000000-0000-4000-8000-000000000001")
EVENT_ID = UUID("50000000-0000-4000-8000-000000000001")
CUTOFF = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_evaluation_report_is_canonical_immutable_and_retry_safe(tmp_path: Path) -> None:
    store = ImmutableEvaluationReportStore(tmp_path)
    report = _report()

    first = store.publish(report)
    retry = store.publish(report)

    assert first.status == "published"
    assert retry.status == "verified_existing"
    assert retry.report_sha256 == first.report_sha256
    assert first.markdown_relative_path.endswith("Sprint2EvaluationReportV1.md")
    assert (tmp_path / first.markdown_relative_path).is_file()
    payload = json.loads((tmp_path / first.relative_path).read_text(encoding="utf-8"))
    assert payload == report.to_dict()
    assert payload["raw_match_result_metrics"]["sample_count"] == 3
    assert payload["evidence_manifest_path"] == (
        f"run={EVALUATION_ID}/Sprint2EvaluationEvidenceManifestV1.json"
    )
    assert payload["evidence_manifest_sha256"] == "c" * 64
    assert payload["evaluation_football_cutoff_start"] == (
        CUTOFF - timedelta(days=2)
    ).isoformat().replace("+00:00", "Z")
    assert payload["evaluation_football_cutoff_end"] == CUTOFF.isoformat().replace("+00:00", "Z")
    schema = json.loads(
        (PROJECT_ROOT / "schemas/contracts/sprint2-evaluation-report-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    invalid = dict(payload, evidence_manifest_path="../manifest.json")
    assert list(Draft202012Validator(schema).iter_errors(invalid))


def test_evaluation_report_rejects_mutation_and_incoherent_status(tmp_path: Path) -> None:
    store = ImmutableEvaluationReportStore(tmp_path)
    report = _report()
    store.publish(report)
    changed = Sprint2EvaluationReportV1(
        evaluation_run_id=report.evaluation_run_id,
        policy_version=report.policy_version,
        scope=report.scope,
        status="PASS_WITH_WARNINGS",
        completed_at=report.completed_at,
        raw_match_result_metrics=report.raw_match_result_metrics,
        findings=("competition sample is small",),
    )

    with pytest.raises(ImmutableFileConflict, match="immutable file conflict"):
        store.publish(changed)
    with pytest.raises(GovernanceContractError, match="requires findings"):
        Sprint2EvaluationReportV1(
            evaluation_run_id=EVALUATION_ID,
            policy_version="sprint2-gate-v1",
            scope=_scope(),
            status="FAIL",
            completed_at=CUTOFF,
            raw_match_result_metrics=_metrics(),
        )
    with pytest.raises(GovernanceContractError, match="evidence manifest"):
        Sprint2EvaluationReportV1(
            evaluation_run_id=EVALUATION_ID,
            policy_version="sprint2-gate-v1",
            scope=_scope(),
            status="FAIL",
            completed_at=CUTOFF,
            raw_match_result_metrics=_metrics(),
            evidence_manifest_path="run=evidence/manifest.json",
            findings=("review pending",),
        )


def test_failed_preflight_report_requires_no_fabricated_scope_or_metrics(tmp_path: Path) -> None:
    report = Sprint2EvaluationReportV1(
        evaluation_run_id=EVALUATION_ID,
        policy_version="sprint2-gate-v1",
        scope=None,
        status="FAIL",
        completed_at=CUTOFF,
        raw_match_result_metrics=None,
        corpus=_corpus(),
        coverage=EvaluationCoverageV1(),
        stage="corpus-resolution",
        findings=("approved corpus is not ingested",),
    )

    publication = ImmutableEvaluationReportStore(tmp_path).publish(report)
    payload = json.loads((tmp_path / publication.relative_path).read_text(encoding="utf-8"))

    assert payload["scope"] is None
    assert payload["raw_match_result_metrics"] is None
    assert payload["coverage"]["scored_targets"] == 0
    assert "# Sprint 2 evaluation report" in (
        tmp_path / publication.markdown_relative_path
    ).read_text(encoding="utf-8")

    with pytest.raises(GovernanceContractError, match="PASS requires"):
        Sprint2EvaluationReportV1(
            evaluation_run_id=EVALUATION_ID,
            policy_version="sprint2-gate-v1",
            scope=None,
            status="PASS",
            completed_at=CUTOFF,
            raw_match_result_metrics=None,
            corpus=_corpus(),
            coverage=EvaluationCoverageV1(),
            stage="complete",
        )


def test_promotion_event_validates_role_and_time() -> None:
    with pytest.raises(GovernanceContractError, match="role is invalid"):
        ModelPromotionEventV1(
            promotion_event_id=EVENT_ID,
            model_artifact_id=ARTIFACT_ID,
            evaluation_run_id=EVALUATION_ID,
            role="Invalid Role",
            designation="BASELINE_APPROVED",
            recorded_at=CUTOFF,
        )
    with pytest.raises(GovernanceContractError, match="timezone"):
        ModelPromotionEventV1(
            promotion_event_id=EVENT_ID,
            model_artifact_id=ARTIFACT_ID,
            evaluation_run_id=EVALUATION_ID,
            role="match_result/baseline",
            designation="BASELINE_APPROVED",
            recorded_at=datetime(2026, 8, 30),
        )


def _report() -> Sprint2EvaluationReportV1:
    return Sprint2EvaluationReportV1(
        evaluation_run_id=EVALUATION_ID,
        policy_version="sprint2-gate-v1",
        scope=_scope(),
        status="PASS",
        completed_at=CUTOFF,
        raw_match_result_metrics=_metrics(),
        corpus=_corpus(),
        coverage=EvaluationCoverageV1(
            registered_matches=380,
            completed_matches=380,
            scored_targets=300,
            corner_labelled_targets=300,
        ),
        stage="complete",
        evidence_manifest_path=(f"run={EVALUATION_ID}/Sprint2EvaluationEvidenceManifestV1.json"),
        evidence_manifest_sha256="c" * 64,
        evaluation_football_cutoff_start=CUTOFF - timedelta(days=2),
        evaluation_football_cutoff_end=CUTOFF,
    )


def _metrics() -> MatchResultMetricsV1:
    outcomes: tuple[MatchOutcome, ...] = ("HOME", "DRAW", "AWAY")
    probabilities = (
        MatchResultProbabilitiesV1(0.7, 0.2, 0.1),
        MatchResultProbabilitiesV1(0.2, 0.6, 0.2),
        MatchResultProbabilitiesV1(0.1, 0.2, 0.7),
    )
    return evaluate_match_results(
        tuple(
            EvaluatedMatchResultV1(
                kickoff_at=CUTOFF + timedelta(days=index, hours=1),
                prediction_cutoff=CUTOFF + timedelta(days=index),
                outcome_known_at=CUTOFF + timedelta(days=index, hours=3),
                probabilities=probability,
                outcome=outcome,
            )
            for index, (probability, outcome) in enumerate(
                zip(probabilities, outcomes, strict=True)
            )
        )
    )


def _scope() -> PointInTimeScopeV1:
    return PointInTimeScopeV1(
        dataset_version_id=DATASET_ID,
        source_snapshot_id=SNAPSHOT_ID,
        feature_set_version="sprint2-features-v1",
        football_cutoff=CUTOFF,
        knowledge_cutoff=CUTOFF,
        knowledge_mode="bitemporal",
        quality_policy_sha256="a" * 64,
        target_set_sha256="b" * 64,
    )


def _corpus() -> EvaluationCorpusV1:
    return EvaluationCorpusV1(
        provider_code="statsbomb_open_data",
        provider_competition_id=2,
        provider_season_id=27,
        minimum_team_history=10,
        minimum_competition_history=100,
        minimum_scored_targets=250,
    )
