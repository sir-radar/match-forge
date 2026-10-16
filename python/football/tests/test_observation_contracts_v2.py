from __future__ import annotations

import json
from dataclasses import replace

import pytest
from football.contracts.observation_schema import observation_schema_sha256
from football.contracts.observations import ObservationError, observation_from_bytes
from football.contracts.observations_v2 import (
    EntityReferenceV2,
    FixtureObservationV2,
    ObservationVersionsV2,
)
from test_observation_contracts import RESOURCE_EXAMPLES, fixture, resource_payload


def test_v1_schema_and_bytes_remain_compatible() -> None:
    assert (
        observation_schema_sha256()
        == "5028f7b235aded2d7e87b08f25b0b44e4d6d242a720a61ed723bdec940beac14"
    )
    item = fixture()
    assert observation_from_bytes(item.to_bytes()).to_bytes() == item.to_bytes()


def test_file_provider_references_do_not_invent_native_or_canonical_ids() -> None:
    old = fixture()
    item = FixtureObservationV2(
        provenance=replace(
            old.provenance,
            provider="openfootball",
            provider_native_id=None,
            source_record_key="json:/matches/0",
        ),
        time=old.time,
        versions=ObservationVersionsV2(
            adapter_version="openfootball-test", normalizer_version="fixture-test"
        ),
        fixture=EntityReferenceV2(None, source_record_key="json:/matches/0"),
        competition=EntityReferenceV2(None, source_record_key="json:/name"),
        home_team=EntityReferenceV2(None, source_record_key="json:/matches/0/team1"),
        away_team=EntityReferenceV2(None, source_record_key="json:/matches/0/team2"),
        kickoff_at=old.kickoff_at,
        status="SCHEDULED",
        kickoff_precision="EXACT",
    )
    assert observation_from_bytes(item.to_bytes()) == item
    assert item.home_team.provider_native_id is None and item.home_team.canonical_id is None
    assert item.home_team != item.away_team
    payload = json.loads(item.to_bytes())
    assert payload["versions"]["observation_contract_version"] == "2"
    with pytest.raises(ObservationError):
        replace(item, away_team=item.home_team)
    with pytest.raises(ObservationError):
        EntityReferenceV2(None)


@pytest.mark.parametrize("contract", RESOURCE_EXAMPLES)
def test_all_v2_contracts_round_trip_and_reject_wrong_version(contract: str) -> None:

    payload = resource_payload(contract)
    payload["contract"] = contract.replace("V1", "V2")
    versions = payload["versions"]
    assert isinstance(versions, dict)
    versions["observation_contract_version"] = "2"
    encoded = json.dumps(payload).encode()
    item = observation_from_bytes(encoded)
    assert observation_from_bytes(item.to_bytes()) == item
    versions["observation_contract_version"] = "1"
    with pytest.raises(ObservationError):
        observation_from_bytes(json.dumps(payload).encode())


def test_v2_schema_file_matches_and_contract_determines_default_version() -> None:
    from pathlib import Path

    from football.contracts.observation_schema import observation_schema

    assert json.loads(
        Path("schemas/contracts/resource-observations-v2.schema.json").read_bytes()
    ) == observation_schema("2")
    payload = resource_payload("FixtureObservationV1")
    payload["contract"] = "FixtureObservationV2"
    versions = payload["versions"]
    assert isinstance(versions, dict)
    del versions["observation_contract_version"]
    assert (
        observation_from_bytes(json.dumps(payload).encode()).versions.observation_contract_version
        == "2"
    )
