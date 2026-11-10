import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pytest
from football.validation.pitchapi_simulation_reference import (
    SplitMix64,
    base_seed_commitment,
    batch_seed,
    canonical_atoms_bytes,
    canonical_probability,
    event_indexes,
    selected_atom_indexes,
)
from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DRAWS_PER_BATCH = 28_115


def golden() -> dict[str, Any]:
    """Vectors shared with rust/simulation-core/src/tests.rs."""
    path = PROJECT_ROOT / "tests/fixtures/pitchapi-simulation-golden-v1.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def validate(schema_name: str, value: object) -> None:
    schema = json.loads(
        (PROJECT_ROOT / "schemas/contracts" / schema_name).read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(value)


def test_python_reference_golden_vectors() -> None:
    generator = SplitMix64(0)
    assert [generator.next_u64() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]
    base = base_seed_commitment("c" * 64)
    seed = batch_seed(base, "synthetic-match-1", 0)
    assert base.hex() == "c4f0050e1627a07a4e2030beb1b20df55d62549ce4a35e7e2b1ff2d77487560e"
    assert seed.hex() == "a185788a8fcce44299ba16d6e236609aebd759b1cdce490f9ead24fe2fd2fe51"
    assert selected_atom_indexes((0.2, 0.3, 0.5), seed, 8) == (2, 1, 2, 1, 2, 0, 2, 0)
    assert event_indexes(2, 1) == (13, 36, 39, 41, 43, 45, 48, 50, 52, 54, 58)


@pytest.mark.parametrize("protocol", ["v2", "v3", "v4"])
def test_python_reference_reproduces_rust_batch_counts(protocol: str) -> None:
    run = golden()["runs"][protocol]
    document = json.loads(run["input"])
    assert hashlib.sha256(run["input"].encode()).hexdigest() == run["input_sha256"]
    exact = document["atoms"][:-1]
    probabilities = tuple(atom["probability"] for atom in document["atoms"])
    base = base_seed_commitment(
        document["forecast_probability_sha256"],
        protocol_id=run["protocol_id"],
        policy_sha256=run["policy_sha256"],
    )
    counts = [[0, 0, 0, 0] for _ in range(62)]
    for batch in range(4):
        seed = batch_seed(base, document["canonical_match_id"], batch)
        for selected in selected_atom_indexes(probabilities, seed, DRAWS_PER_BATCH):
            atom = exact[selected]
            for event in event_indexes(atom["home_goals"], atom["away_goals"]):
                counts[event][batch] += 1
    assert counts == run["batch_counts"]


def test_python_atom_serialization_matches_rust_bytes_and_hash() -> None:
    fixture = golden()
    atoms = json.loads(fixture["runs"]["v3"]["input"])["atoms"]
    canonical = canonical_atoms_bytes(atoms)
    assert canonical.decode() == fixture["canonical_atoms"]
    assert hashlib.sha256(canonical).hexdigest() == fixture["forecast_probability_sha256"]
    for vector in fixture["number_format_vectors"]:
        assert canonical_probability(float(vector["python"])) == vector["rust"]


@pytest.mark.parametrize("value", [-0.0, -1e-9, 1.0000000000000002, float("nan"), float("inf")])
def test_canonical_probability_rejects_values_outside_the_unit_interval(value: float) -> None:
    with pytest.raises(ValueError, match="probability must be in"):
        canonical_probability(value)


def test_canonical_atoms_reject_untyped_values() -> None:
    atom = {"away_goals": 0, "home_goals": 0, "kind": "EXACT_SCORE", "probability": 1.0}
    with pytest.raises(ValueError, match="must be a float"):
        canonical_atoms_bytes([{**atom, "probability": 1}])
    with pytest.raises(ValueError, match="must be a float"):
        canonical_probability(True)
    with pytest.raises(ValueError, match="integers or null"):
        canonical_atoms_bytes([{**atom, "home_goals": True}])


def test_golden_documents_satisfy_the_published_schemas() -> None:
    runs = golden()["runs"]
    for run in runs.values():
        validate("pitchapi-simulation-input-v1.schema.json", json.loads(run["input"]))
    validate("simulation-validation-artifact-v1.schema.json", json.loads(runs["v3"]["output"]))
    validate(
        "pitchapi-v4-simulation-validation-artifact-v1.schema.json",
        json.loads(runs["v4"]["output"]),
    )
    for name in ("v3", "v4"):
        output = runs[name]["output"].encode()
        assert hashlib.sha256(output).hexdigest() == runs[name]["output_sha256"]
