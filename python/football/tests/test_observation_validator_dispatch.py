from __future__ import annotations

from copy import deepcopy

import pytest
from football.contracts.observation_codec import _validate_payload
from football.contracts.observation_schema import observation_schema
from football.contracts.observations import ObservationError
from jsonschema import Draft202012Validator, FormatChecker
from test_observation_contracts import RESOURCE_EXAMPLES, resource_payload


def _accepted(payload: dict[str, object]) -> bool:
    try:
        _validate_payload(payload)
    except ObservationError:
        return False
    return True


def _mutations(payload: dict[str, object], version: str) -> list[dict[str, object]]:
    mutations = []
    invalid_values: tuple[object, ...] = (None, "wrong-type", False, [])
    for key in payload:
        missing = deepcopy(payload)
        del missing[key]
        mutations.append(missing)
        for invalid in invalid_values:
            changed = deepcopy(payload)
            changed[key] = invalid
            mutations.append(changed)
    mutations.append({**deepcopy(payload), "unexpected": "extra field"})
    for tag in ("UnregisteredObservation", f"TeamObservationV{version}"):
        mutations.append({**deepcopy(payload), "contract": tag})
    for field in ("observed_at", "acquired_at", "known_at"):
        changed = deepcopy(payload)
        time = changed["time"]
        assert isinstance(time, dict)
        time[field] = "2026-10-16"
        mutations.append(changed)
    changed = deepcopy(payload)
    versions = changed["versions"]
    assert isinstance(versions, dict)
    versions["observation_contract_version"] = "2" if version == "1" else "1"
    mutations.append(changed)
    return mutations


@pytest.mark.parametrize("version", ["1", "2"])
@pytest.mark.parametrize("contract", RESOURCE_EXAMPLES)
def test_declared_type_validation_matches_the_complete_published_union(
    version: str, contract: str
) -> None:
    payload = deepcopy(resource_payload(contract))
    payload["contract"] = contract.replace("V1", f"V{version}")
    versions = payload["versions"]
    assert isinstance(versions, dict)
    versions["observation_contract_version"] = version
    schema = observation_schema(version)
    original = deepcopy(schema)
    full = Draft202012Validator(schema, format_checker=FormatChecker())
    assert full.is_valid(payload) and _accepted(payload)
    for mutation in _mutations(payload, version):
        assert _accepted(mutation) == full.is_valid(mutation), mutation
    assert schema == original
