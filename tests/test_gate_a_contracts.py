from __future__ import annotations

from experiments.sprint1_roundtrip.core import (
    DATASET_SCHEMA_PATH,
    EVENT_SCHEMA_SPEC_PATH,
    FIXTURE_PATH,
    QUALITY_POLICY_PATH,
    SOURCE_SCHEMA_PATH,
    load_json,
)


def test_fixture_is_pinned_to_full_git_sha() -> None:
    fixture = load_json(FIXTURE_PATH)
    assert len(fixture["source_git_sha"]) == 40
    assert fixture["match_id"] == 3869685
    assert len(fixture["resources"]) == 5
    assert all(len(resource["sha256"]) == 64 for resource in fixture["resources"])


def test_quality_policy_has_four_expected_severities() -> None:
    policy = load_json(QUALITY_POLICY_PATH)
    severities = {rule["severity"] for rule in policy["rules"].values()}
    assert severities == {"FATAL", "QUARANTINE", "WARNING", "INFO"}


def test_contract_schemas_are_versioned() -> None:
    assert load_json(SOURCE_SCHEMA_PATH)["$id"] == "SourceManifestV1"
    assert load_json(DATASET_SCHEMA_PATH)["$id"] == "DatasetManifestV1"
    assert load_json(EVENT_SCHEMA_SPEC_PATH)["name"] == "normalized-events-v1"
