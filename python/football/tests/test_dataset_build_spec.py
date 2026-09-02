from datetime import UTC, datetime

import pytest
from football.datasets import DatasetBuildSpecError, DatasetBuildSpecV1


def test_build_spec_is_canonical_and_reproducible() -> None:
    spec = _spec()

    assert spec.to_dict()["contract"] == "DatasetBuildSpecV1"
    assert spec.to_dict()["knowledge_mode"] == "historical"
    assert len(spec.sha256) == 64
    assert spec.sha256 == _spec().sha256


def test_historical_build_requires_knowledge_cutoff() -> None:
    with pytest.raises(DatasetBuildSpecError, match="requires a cutoff"):
        _spec(knowledge_cutoff=None)


def test_build_spec_rejects_duplicate_inputs_and_invalid_git_sha() -> None:
    with pytest.raises(DatasetBuildSpecError, match="must be unique"):
        _spec(source_input_refs=("source-1", "source-1"))
    with pytest.raises(DatasetBuildSpecError, match="Git SHA"):
        _spec(code_git_sha="invalid")


def _spec(**overrides: object) -> DatasetBuildSpecV1:
    values: dict[str, object] = {
        "dataset_contract": "curated_matches",
        "dataset_version": "v1",
        "source_input_refs": ("source-1",),
        "canonical_input_refs": ("canonical-1",),
        "football_cutoff": datetime(2022, 12, 1, tzinfo=UTC),
        "knowledge_cutoff": datetime(2022, 12, 2, tzinfo=UTC),
        "knowledge_mode": "historical",
        "feature_versions": ("features-v1",),
        "quality_policy_version": "quality-v1",
        "resolution_policy_version": "resolution-v1",
        "code_git_sha": "a" * 40,
        "dependency_lock_sha256": "b" * 64,
        "configuration": {"competition": "epl", "season": 2022},
    }
    values.update(overrides)
    return DatasetBuildSpecV1(**values)  # type: ignore[arg-type]
