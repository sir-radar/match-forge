from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.integrity import IntegrityFileVerification, _verify_file

_ForecastRow = tuple[UUID, str, str, bool, int, int]
_EvaluationRow = tuple[UUID, str, str, bool, int]


@dataclass(frozen=True, slots=True)
class ForecastEvaluationHardGateIntegrityV1:
    registered_forecast_count: int
    retired_test_only_forecast_count: int
    production_eligible_forecast_count: int
    retained_artifact_link_count: int
    retained_lineage_row_count: int
    evaluation_run_count: int
    registered_evaluation_run_count: int
    retired_test_only_evaluation_count: int
    production_eligible_evaluation_count: int
    retained_evaluation_lineage_row_count: int
    production_failures: tuple[IntegrityFileVerification, ...]
    retired_physical_failures: tuple[IntegrityFileVerification, ...]
    retired_evaluation_physical_failures: tuple[IntegrityFileVerification, ...]

    @property
    def status(self) -> str:
        return "PASS" if not self.production_failures else "FAIL"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": "ForecastEvaluationHardGateIntegrityV1",
            "registered_forecast_count": self.registered_forecast_count,
            "retired_test_only_forecast_count": self.retired_test_only_forecast_count,
            "production_eligible_forecast_count": self.production_eligible_forecast_count,
            "retained_artifact_link_count": self.retained_artifact_link_count,
            "retained_lineage_row_count": self.retained_lineage_row_count,
            "evaluation_run_count": self.evaluation_run_count,
            "registered_evaluation_run_count": self.registered_evaluation_run_count,
            "retired_test_only_evaluation_count": self.retired_test_only_evaluation_count,
            "production_eligible_evaluation_count": self.production_eligible_evaluation_count,
            "retained_evaluation_lineage_row_count": self.retained_evaluation_lineage_row_count,
            "status": self.status,
            "production_failures": [item.to_dict() for item in self.production_failures],
            "retired_physical_failures": [
                item.to_dict() for item in self.retired_physical_failures
            ],
            "retired_evaluation_physical_failures": [
                item.to_dict() for item in self.retired_evaluation_physical_failures
            ],
        }


@dataclass(frozen=True, slots=True)
class _VerificationPopulation:
    registered_count: int
    retired_count: int
    retained_artifact_link_count: int
    retained_lineage_row_count: int
    production_failures: tuple[IntegrityFileVerification, ...]
    retired_physical_failures: tuple[IntegrityFileVerification, ...]


class PostgresForecastEvaluationHardGateVerifier:
    """Checks production hard-gate files while retaining retired test-only lineage."""

    def __init__(self, connection: Connection[Any], data_root: Path, report_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()
        self._report_root = report_root.resolve()

    def verify(self) -> ForecastEvaluationHardGateIntegrityV1:
        forecasts, evaluations = self._load_populations()
        forecast_result = self._verify_forecasts(forecasts)
        evaluation_result = self._verify_evaluations(evaluations)
        return ForecastEvaluationHardGateIntegrityV1(
            registered_forecast_count=forecast_result.registered_count,
            retired_test_only_forecast_count=forecast_result.retired_count,
            production_eligible_forecast_count=(
                forecast_result.registered_count - forecast_result.retired_count
            ),
            retained_artifact_link_count=forecast_result.retained_artifact_link_count,
            retained_lineage_row_count=forecast_result.retained_lineage_row_count,
            evaluation_run_count=evaluation_result.registered_count,
            registered_evaluation_run_count=evaluation_result.registered_count,
            retired_test_only_evaluation_count=evaluation_result.retired_count,
            production_eligible_evaluation_count=(
                evaluation_result.registered_count - evaluation_result.retired_count
            ),
            retained_evaluation_lineage_row_count=evaluation_result.retained_lineage_row_count,
            production_failures=(
                forecast_result.production_failures + evaluation_result.production_failures
            ),
            retired_physical_failures=forecast_result.retired_physical_failures,
            retired_evaluation_physical_failures=evaluation_result.retired_physical_failures,
        )

    def _load_populations(
        self,
    ) -> tuple[tuple[_ForecastRow, ...], tuple[_EvaluationRow, ...]]:
        with self._connection.cursor() as cursor:
            forecasts = tuple(
                cursor.execute(
                    """
                    SELECT forecast.id, forecast.payload_path, forecast.payload_sha256,
                           EXISTS (
                               SELECT 1 FROM football.artifact_retirement_events AS retirement
                               WHERE retirement.object_kind = 'FORECAST'
                                 AND retirement.object_id = forecast.id
                                 AND retirement.retirement_scope =
                                     'TEST_ONLY_HARD_GATE_EXCLUSION'
                                 AND retirement.reason = 'SYNTHETIC_TEST_LINEAGE'
                           ),
                           (SELECT count(*) FROM football.forecast_artifacts AS artifact
                            WHERE artifact.forecast_id = forecast.id),
                           (SELECT count(*) FROM football.dependency_edges AS edge
                            WHERE edge.downstream_kind = 'FORECAST'
                              AND edge.downstream_id = forecast.id)
                    FROM football.baseline_forecasts AS forecast
                    ORDER BY forecast.id
                    """
                )
            )
            evaluations = tuple(
                cursor.execute(
                    """
                    SELECT evaluation.id, evaluation.report_path, evaluation.report_sha256,
                           EXISTS (
                               SELECT 1 FROM football.artifact_retirement_events AS retirement
                               WHERE retirement.object_kind = 'EVALUATION'
                                 AND retirement.object_id = evaluation.id
                                 AND retirement.retirement_scope =
                                     'TEST_ONLY_HARD_GATE_EXCLUSION'
                                 AND retirement.reason = 'SYNTHETIC_TEST_LINEAGE'
                           ),
                           (SELECT count(*) FROM football.dependency_edges AS edge
                            WHERE edge.downstream_kind = 'EVALUATION'
                              AND edge.downstream_id = evaluation.id)
                    FROM football.sprint2_evaluation_runs AS evaluation
                    ORDER BY evaluation.id
                    """
                )
            )
        return cast(tuple[_ForecastRow, ...], forecasts), cast(
            tuple[_EvaluationRow, ...], evaluations
        )

    def _verify_forecasts(self, forecasts: tuple[_ForecastRow, ...]) -> _VerificationPopulation:
        production_failures: list[IntegrityFileVerification] = []
        retired_physical_failures: list[IntegrityFileVerification] = []
        retired_count = 0
        retained_artifact_links = 0
        retained_lineage_rows = 0
        for forecast_id, path, checksum, retired, artifact_count, lineage_count in forecasts:
            referential_failure = _referential_failure(forecast_id, artifact_count, lineage_count)
            if retired:
                retired_count += 1
                retained_artifact_links += artifact_count
                retained_lineage_rows += lineage_count
                if referential_failure is not None:
                    production_failures.append(referential_failure)
                    continue
                check = _verify_file(self._data_root, str(path), str(checksum))
                if check.status != "PASS":
                    retired_physical_failures.append(check)
                continue
            if referential_failure is not None:
                production_failures.append(referential_failure)
                continue
            check = _verify_file(self._data_root, str(path), str(checksum))
            if check.status != "PASS":
                production_failures.append(check)
        return _VerificationPopulation(
            registered_count=len(forecasts),
            retired_count=retired_count,
            retained_artifact_link_count=retained_artifact_links,
            retained_lineage_row_count=retained_lineage_rows,
            production_failures=tuple(production_failures),
            retired_physical_failures=tuple(retired_physical_failures),
        )

    def _verify_evaluations(
        self, evaluations: tuple[_EvaluationRow, ...]
    ) -> _VerificationPopulation:
        production_failures: list[IntegrityFileVerification] = []
        retired_physical_failures: list[IntegrityFileVerification] = []
        retired_count = 0
        retained_lineage_rows = 0
        for evaluation_id, path, checksum, retired, lineage_count in evaluations:
            referential_failure = _evaluation_referential_failure(evaluation_id, lineage_count)
            if retired:
                retired_count += 1
                retained_lineage_rows += lineage_count
                if referential_failure is not None:
                    production_failures.append(referential_failure)
                    continue
                check = _verify_file(self._report_root, str(path), str(checksum))
                if check.status != "PASS":
                    retired_physical_failures.append(check)
                continue
            if referential_failure is not None:
                production_failures.append(referential_failure)
                continue
            check = _verify_file(self._report_root, str(path), str(checksum))
            if check.status != "PASS":
                production_failures.append(check)
        return _VerificationPopulation(
            registered_count=len(evaluations),
            retired_count=retired_count,
            retained_artifact_link_count=0,
            retained_lineage_row_count=retained_lineage_rows,
            production_failures=tuple(production_failures),
            retired_physical_failures=tuple(retired_physical_failures),
        )


def _referential_failure(
    forecast_id: UUID, artifact_count: int, lineage_count: int
) -> IntegrityFileVerification | None:
    if artifact_count < 1 or lineage_count < artifact_count:
        return IntegrityFileVerification(
            path=f"forecast={forecast_id}",
            expected_sha256=None,
            actual_sha256=None,
            status="INVALID_REGISTRATION",
            failure_reason="forecast artifact links and dependency lineage conflict",
        )
    return None


def _evaluation_referential_failure(
    evaluation_id: UUID, lineage_count: int
) -> IntegrityFileVerification | None:
    if lineage_count < 1:
        return IntegrityFileVerification(
            path=f"evaluation={evaluation_id}",
            expected_sha256=None,
            actual_sha256=None,
            status="INVALID_REGISTRATION",
            failure_reason="evaluation dependency lineage is missing",
        )
    return None
