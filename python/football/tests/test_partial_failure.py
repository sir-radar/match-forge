from __future__ import annotations

import pytest
from football.ingestion import (
    PartialFailureError,
    PartialFailureReportV1,
    ResourceProcessingResultV1,
)


def test_partial_failure_report_isolates_resource_outcomes() -> None:
    report = PartialFailureReportV1(
        (
            ResourceProcessingResultV1("resource:ok", "SUCCEEDED"),
            ResourceProcessingResultV1("resource:retry", "RETRYABLE", "TIMEOUT"),
            ResourceProcessingResultV1("resource:quarantine", "QUARANTINED", "SCHEMA_INVALID"),
        )
    )

    assert report.status == "PARTIAL"
    assert report.resources[0].status == "SUCCEEDED"


def test_partial_failure_report_is_failed_when_every_resource_fails() -> None:
    report = PartialFailureReportV1(
        (ResourceProcessingResultV1("resource:failed", "FAILED", "PUBLISH_ERROR"),)
    )
    assert report.status == "FAILED"


def test_partial_failure_rejects_missing_error_or_duplicate_identity() -> None:
    with pytest.raises(PartialFailureError, match="requires an error"):
        ResourceProcessingResultV1("resource:failed", "FAILED")
    with pytest.raises(PartialFailureError, match="identities must be unique"):
        PartialFailureReportV1(
            (
                ResourceProcessingResultV1("resource:one", "SUCCEEDED"),
                ResourceProcessingResultV1("resource:one", "SUCCEEDED"),
            )
        )
