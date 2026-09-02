from datetime import UTC, datetime

import pytest
from football.datasets import DatasetBuildSpecError, DatasetRebuildRequestV1


def test_rebuild_request_binds_build_identity_and_source_correction() -> None:
    request = _request()

    assert request.to_dict()["contract"] == "DatasetRebuildRequestV1"
    assert request.to_dict()["reason"] == "SOURCE_CORRECTION"
    assert len(request.sha256) == 64


def test_rebuild_request_rejects_invalid_build_checksum_and_attempt() -> None:
    with pytest.raises(DatasetBuildSpecError, match="must be a SHA-256"):
        _request(build_spec_sha256="invalid")
    with pytest.raises(DatasetBuildSpecError, match="attempt"):
        _request(attempt=0)


def test_rebuild_request_status_is_versioned_and_validated() -> None:
    with pytest.raises(DatasetBuildSpecError, match="status"):
        _request(status="UNKNOWN")


def _request(**overrides: object) -> DatasetRebuildRequestV1:
    values: dict[str, object] = {
        "request_id": "rebuild-1",
        "dataset_ref": "dataset-1",
        "build_spec_sha256": "a" * 64,
        "requested_at": datetime(2026, 9, 2, 12, 0, tzinfo=UTC),
        "reason": "SOURCE_CORRECTION",
        "status": "REQUESTED",
        "source_change_set_ref": "change-set-1",
    }
    values.update(overrides)
    return DatasetRebuildRequestV1(**values)  # type: ignore[arg-type]
