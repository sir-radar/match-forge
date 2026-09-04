from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from football.ingestion.fixture_persistence import F3FixtureSourceV1
from football.normalization import normalize_football_data_uk_record
from football.providers.football_data_uk_csv import parse_football_data_uk_csv

_FIXTURE_ROOT = Path(__file__).resolve().parents[3] / "tests/fixtures/football_data_uk/phase1b"


def test_committed_f3_fixture_has_immutable_contract_source_identity() -> None:
    payload = (_FIXTURE_ROOT / "f3_ambiguous_identity_v1.csv").read_bytes()
    manifest_payload = (_FIXTURE_ROOT / "f3_ambiguous_identity_v1.json").read_bytes()
    source = F3FixtureSourceV1.from_payload(
        payload=payload,
        acquired_at=datetime(2026, 9, 5, 12, tzinfo=UTC),
        manifest_path="fixtures/football_data_uk/phase1b/f3_ambiguous_identity_v1.json",
        manifest_payload=manifest_payload,
    )
    manifest = json.loads(manifest_payload)

    assert source.provider_id == "football_data_uk"
    assert source.source_kind == "CONTRACT_FIXTURE"
    assert source.fixture_id == manifest["fixture_id"]
    assert source.fixture_locator == manifest["fixture_locator"]
    assert source.raw_byte_size == manifest["raw_byte_size"]
    assert source.raw_sha256 == manifest["raw_sha256"]
    assert source.fixture_contract_version == manifest["fixture_contract_version"]
    parsed = parse_football_data_uk_csv(source, payload)
    normalized = normalize_football_data_uk_record(source, parsed.records[0])
    assert normalized.provider_home_team_name == "F3 Ambiguous Team"
    assert normalized.full_time_home_goals == 1
