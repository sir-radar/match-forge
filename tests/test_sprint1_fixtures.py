from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from tests.support.sprint1_fixtures import (
    SPRINT1_FIXTURE_ROOT,
    FixtureContractError,
    FixtureProvider,
    load_sprint1_fixture,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas/contracts/sprint1-fixture-v1.schema.json"


@pytest.mark.parametrize(
    ("name", "outcome", "resource_count"),
    (
        ("valid", "passed", 4),
        ("quality", "quarantined", 4),
        ("malformed-events", "ingestion_error", 1),
    ),
)
def test_committed_fixture_contracts(name: str, outcome: str, resource_count: int) -> None:
    schema = json.loads(SCHEMA_PATH.read_bytes())
    document = json.loads((SPRINT1_FIXTURE_ROOT / name / "fixture.json").read_bytes())

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    fixture = load_sprint1_fixture(name)

    assert fixture.name == name
    assert fixture.expected.outcome == outcome
    assert len(fixture.resources) == resource_count
    assert fixture.acquired_at.utcoffset() is not None
    assert fixture.snapshot.source_git_sha == document["source_git_sha"]


def test_fixture_provider_returns_only_checksum_verified_bytes() -> None:
    fixture = load_sprint1_fixture("valid")
    provider = FixtureProvider(fixture)

    payloads = [provider.fetch(resource) for resource in fixture.source_resources]

    assert provider.fetches == [resource.path for resource in fixture.source_resources]
    assert [len(payload) for payload in payloads] == [
        resource.size_bytes for resource in fixture.resources
    ]


def test_fixture_loader_rejects_checksum_drift(tmp_path: Path) -> None:
    fixture_root = tmp_path / "sprint1"
    shutil.copytree(SPRINT1_FIXTURE_ROOT / "valid", fixture_root / "valid")
    event_path = fixture_root / "valid/data/events/1001.json"
    event_path.write_bytes(event_path.read_bytes() + b"\n")

    with pytest.raises(FixtureContractError, match="size mismatch"):
        load_sprint1_fixture("valid", fixture_root=fixture_root)


def test_malformed_fixture_preserves_exact_provider_bytes() -> None:
    fixture = load_sprint1_fixture("malformed-events")

    assert fixture.payload(fixture.source_resources[0]) == b"{\n"
