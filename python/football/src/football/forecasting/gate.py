from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection

from football.contracts.source import canonical_json_bytes
from football.forecasting.governance import (
    EvaluationCorpusV1,
    EvaluationCoverageV1,
    EvaluationStatus,
    ImmutableEvaluationReportStore,
    Sprint2EvaluationReportV1,
)
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION

_EVALUATION_NAMESPACE = UUID("4ae2a83b-7efb-4c2c-98bf-70e818c6f6d1")


@dataclass(frozen=True, slots=True)
class Sprint2GateSummary:
    evaluation_run_id: UUID
    status: EvaluationStatus
    stage: str
    json_path: Path
    markdown_path: Path
    findings: tuple[str, ...]


class Sprint2GateService:
    """Run the authoritative Sprint 2 gate until the first blocking stage."""

    def __init__(self, connection: Connection[Any], report_root: Path) -> None:
        self._connection = connection
        self._report_root = report_root.resolve()

    def evaluate(self, corpus: EvaluationCorpusV1 | None = None) -> Sprint2GateSummary:
        requested = corpus or EvaluationCorpusV1()
        completed_at = datetime.now(UTC)
        coverage, stage, findings = self._inspect_corpus(requested)
        report = Sprint2EvaluationReportV1(
            evaluation_run_id=_evaluation_id(completed_at, requested, coverage, stage, findings),
            policy_version="sprint2-baseline-gate-v1",
            corpus=requested,
            coverage=coverage,
            stage=stage,
            scope=None,
            status="FAIL",
            completed_at=completed_at,
            raw_match_result_metrics=None,
            findings=findings,
        )
        publication = ImmutableEvaluationReportStore(self._report_root).publish(report)
        return Sprint2GateSummary(
            evaluation_run_id=report.evaluation_run_id,
            status=report.status,
            stage=report.stage,
            json_path=self._report_root / publication.relative_path,
            markdown_path=self._report_root / publication.markdown_relative_path,
            findings=report.findings,
        )

    def _inspect_corpus(
        self, corpus: EvaluationCorpusV1
    ) -> tuple[EvaluationCoverageV1, str, tuple[str, ...]]:
        with self._connection.cursor() as cursor:
            mappings = cursor.execute(
                """
                SELECT season.id, season.competition_id
                FROM football.season_provider_mappings AS mapping
                JOIN football.providers AS provider ON provider.id = mapping.provider_id
                JOIN football.seasons AS season ON season.id = mapping.season_id
                WHERE provider.code = %s
                  AND mapping.provider_competition_id = %s
                  AND mapping.provider_season_id = %s
                  AND mapping.valid_to IS NULL
                ORDER BY season.id
                """,
                (
                    corpus.provider_code,
                    str(corpus.provider_competition_id),
                    str(corpus.provider_season_id),
                ),
            ).fetchall()
        if not mappings:
            return (
                EvaluationCoverageV1(),
                "corpus-resolution",
                (
                    "approved corpus is not ingested: "
                    f"{corpus.provider_code} competition_id={corpus.provider_competition_id} "
                    f"season_id={corpus.provider_season_id}",
                    "chronological walk-forward evaluation did not run",
                ),
            )
        if len(mappings) != 1:
            return (
                EvaluationCoverageV1(),
                "corpus-resolution",
                (
                    "approved corpus maps to multiple canonical seasons",
                    "chronological walk-forward evaluation did not run",
                ),
            )
        season_id = UUID(str(mappings[0][0]))
        coverage = self._coverage(season_id)
        if coverage.scored_targets < corpus.minimum_scored_targets:
            return (
                coverage,
                "coverage",
                (
                    f"primary evaluation has {coverage.scored_targets} scored targets; "
                    f"minimum is {corpus.minimum_scored_targets}",
                    "chronological walk-forward evaluation did not run",
                ),
            )
        return (
            coverage,
            "walk-forward-execution",
            (
                "approved corpus passed count preflight but no complete retained walk-forward "
                "evaluation exists",
            ),
        )

    def _coverage(self, season_id: UUID) -> EvaluationCoverageV1:
        with self._connection.cursor() as cursor:
            row = cursor.execute(
                """
                SELECT
                    count(DISTINCT match.id),
                    count(DISTINCT match.id) FILTER (
                        WHERE claim.id IS NOT NULL
                    ),
                    count(DISTINCT match.id) FILTER (
                        WHERE claim.id IS NOT NULL
                          AND observation.home_score IS NOT NULL
                          AND observation.away_score IS NOT NULL
                    )
                FROM football.matches AS match
                LEFT JOIN football.match_lifecycle_claims AS claim
                  ON claim.match_id = match.id
                 AND claim.claim_version = %s
                 AND claim.lifecycle = 'completed'
                LEFT JOIN football.match_observations AS observation
                  ON observation.id = claim.match_observation_id
                WHERE match.season_id = %s
                """,
                (LIFECYCLE_CLAIM_VERSION, season_id),
            ).fetchone()
        if row is None:
            return EvaluationCoverageV1()
        return EvaluationCoverageV1(
            registered_matches=int(row[0]),
            completed_matches=int(row[1]),
            scored_targets=int(row[2]),
            corner_labelled_targets=0,
        )


def _evaluation_id(
    completed_at: datetime,
    corpus: EvaluationCorpusV1,
    coverage: EvaluationCoverageV1,
    stage: str,
    findings: tuple[str, ...],
) -> UUID:
    identity = {
        "completed_at": completed_at.isoformat(),
        "corpus": corpus.to_dict(),
        "coverage": coverage.to_dict(),
        "stage": stage,
        "findings": list(findings),
    }
    digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return uuid5(_EVALUATION_NAMESPACE, digest)
