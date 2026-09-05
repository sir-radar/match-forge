from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection

from football.integrity import IntegrityFileVerification, _verify_file


@dataclass(frozen=True, slots=True)
class ForecastEvaluationHardGateIntegrityV1:
    registered_forecast_count: int
    retired_test_only_forecast_count: int
    production_eligible_forecast_count: int
    retained_artifact_link_count: int
    retained_lineage_row_count: int
    evaluation_run_count: int
    production_failures: tuple[IntegrityFileVerification, ...]
    retired_physical_failures: tuple[IntegrityFileVerification, ...]

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
            "status": self.status,
            "production_failures": [item.to_dict() for item in self.production_failures],
            "retired_physical_failures": [
                item.to_dict() for item in self.retired_physical_failures
            ],
        }


class PostgresForecastEvaluationHardGateVerifier:
    """Checks production hard-gate files while retaining retired test-only lineage."""

    def __init__(self, connection: Connection[Any], data_root: Path, report_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()
        self._report_root = report_root.resolve()

    def verify(self) -> ForecastEvaluationHardGateIntegrityV1:
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
                    SELECT id, report_path, report_sha256
                    FROM football.sprint2_evaluation_runs
                    ORDER BY id
                    """
                )
            )
        production_failures: list[IntegrityFileVerification] = []
        retired_physical_failures: list[IntegrityFileVerification] = []
        retired_count = 0
        retained_artifact_links = 0
        retained_lineage_rows = 0
        for forecast_id, path, checksum, retired, artifact_count, lineage_count in forecasts:
            referential_failure = _referential_failure(
                UUID(str(forecast_id)), int(artifact_count), int(lineage_count)
            )
            if retired:
                retired_count += 1
                retained_artifact_links += int(artifact_count)
                retained_lineage_rows += int(lineage_count)
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
        for _evaluation_id, path, checksum in evaluations:
            check = _verify_file(self._report_root, str(path), str(checksum))
            if check.status != "PASS":
                production_failures.append(check)
        return ForecastEvaluationHardGateIntegrityV1(
            registered_forecast_count=len(forecasts),
            retired_test_only_forecast_count=retired_count,
            production_eligible_forecast_count=len(forecasts) - retired_count,
            retained_artifact_link_count=retained_artifact_links,
            retained_lineage_row_count=retained_lineage_rows,
            evaluation_run_count=len(evaluations),
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
