from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.forecast_integrity import PostgresForecastEvaluationHardGateVerifier
from psycopg import Connection


def test_retired_evaluations_are_excluded_but_non_retired_evaluations_remain_in_scope(
    tmp_path: Path,
) -> None:
    verifier = PostgresForecastEvaluationHardGateVerifier(
        cast(Connection[Any], None), tmp_path, tmp_path
    )

    result = verifier._verify_evaluations(
        (
            (
                UUID("10000000-0000-4000-8000-000000000001"),
                "retired-report.json",
                "a" * 64,
                True,
                1,
            ),
            (
                UUID("10000000-0000-4000-8000-000000000002"),
                "production-report.json",
                "b" * 64,
                False,
                1,
            ),
        )
    )

    assert result.registered_count == 2
    assert result.retired_count == 1
    assert result.retained_lineage_row_count == 1
    assert len(result.production_failures) == 1
    assert result.production_failures[0].path == "production-report.json"
    assert len(result.retired_physical_failures) == 1
    assert result.retired_physical_failures[0].path == "retired-report.json"
