"""Exercise the Python side of the Rust simulation bridge against a stand-in executable."""

import hashlib
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from football.forecasting import pitchapi_v3_runtime as runtime
from football.forecasting.pitchapi_v3_evaluation import ExactScoreDistributionV1
from football.forecasting.pitchapi_v3_executor import PreparedTargetV1, V4SimulationReceiptV1
from football.validation.pitchapi_simulation_reference import canonical_atoms_bytes
from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATCH_ID = UUID("00000000-0000-4000-8000-000000000001")
POLICY_SHA256 = "c" * 64
MODEL_SHA256 = "b" * 64

_STAND_IN = """#!{python}
import hashlib, importlib.util, json, os, sys

# Load the stdlib-only reference module directly; importing the package is slow.
spec = importlib.util.spec_from_file_location("reference", {reference!r})
reference = importlib.util.module_from_spec(spec)
sys.modules["reference"] = reference
spec.loader.exec_module(reference)
canonical_atoms_bytes = reference.canonical_atoms_bytes

arguments = sys.argv[1:]
if arguments[0] == "--canonicalize-atoms":
    with open(arguments[1], "rb") as handle:
        sys.stdout.buffer.write(canonical_atoms_bytes(json.load(handle)))
elif arguments[0] == "--canonicalize":
    with open(arguments[1], "rb") as handle:
        sys.stdout.buffer.write(handle.read())
else:
    with open(arguments[0], "rb") as handle:
        payload = handle.read()
    if hashlib.sha256(payload).hexdigest() != arguments[1]:
        sys.exit("INPUT_HASH_MISMATCH: input bytes do not match expected SHA-256")
    mode = os.environ.get("STAND_IN_MODE", "")
    if mode == "hang":
        import time

        time.sleep(30)
    if mode == "fail":
        sys.exit("PARITY_FAILURE: stand-in refusal")
    with open(os.environ["STAND_IN_CAPTURE"], "wb") as handle:
        handle.write(payload)
    with open(os.environ["STAND_IN_OUTPUT"], "rb") as handle:
        output = handle.read()
    sys.stdout.buffer.write(output + (arguments[2].encode() if mode == "diverge" else b""))
"""


def golden() -> dict[str, Any]:
    path = PROJECT_ROOT / "tests/fixtures/pitchapi-simulation-golden-v1.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@pytest.fixture
def stand_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    binary = tmp_path / "simulation-stand-in"
    reference = "python/football/src/football/validation/pitchapi_simulation_reference.py"
    binary.write_text(
        _STAND_IN.format(python=sys.executable, reference=str(PROJECT_ROOT / reference)),
        encoding="utf-8",
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("STAND_IN_CAPTURE", str(tmp_path / "captured-input.json"))
    monkeypatch.setenv("STAND_IN_OUTPUT", str(tmp_path / "output.json"))
    monkeypatch.delenv("STAND_IN_MODE", raising=False)
    return binary


def build_sha256(binary: Path) -> str:
    return hashlib.sha256(binary.read_bytes()).hexdigest()


def target() -> PreparedTargetV1:
    return cast(PreparedTargetV1, SimpleNamespace(context=SimpleNamespace(match_id=MATCH_ID)))


def distribution() -> ExactScoreDistributionV1:
    atoms = json.loads(golden()["runs"]["v3"]["input"])["atoms"]
    return ExactScoreDistributionV1(
        atoms=tuple(
            (atom["home_goals"], atom["away_goals"], atom["probability"]) for atom in atoms[:-1]
        ),
        unresolved_tail=atoms[-1]["probability"],
    )


def write_output(tmp_path: Path, protocol: str, **overrides: object) -> None:
    output = json.loads(golden()["runs"][protocol]["output"])
    (tmp_path / "output.json").write_text(json.dumps({**output, **overrides}), encoding="utf-8")


def captured_input(tmp_path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = (tmp_path / "captured-input.json").read_bytes()
    return raw, cast(dict[str, Any], json.loads(raw))


def assert_input_contract(raw: bytes, document: dict[str, Any], protocol: str) -> None:
    schema = json.loads(
        (PROJECT_ROOT / "schemas/contracts/pitchapi-simulation-input-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(document)
    expected = json.loads(golden()["runs"][protocol]["input"])
    assert raw == json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    assert document["atoms"] == expected["atoms"]
    assert (
        document["forecast_probability_sha256"]
        == hashlib.sha256(canonical_atoms_bytes(document["atoms"])).hexdigest()
        == golden()["forecast_probability_sha256"]
    )
    assert [item["event_id"] for item in document["analytic_probabilities"]] == [
        item["event_id"] for item in expected["analytic_probabilities"]
    ]
    for actual, reduced in zip(
        document["analytic_probabilities"], expected["analytic_probabilities"], strict=True
    ):
        # simulation-core recomputes these from the atoms and allows 1e-12.
        assert abs(actual["probability"] - reduced["probability"]) <= 1e-12


def test_v3_adapter_writes_the_contract_and_returns_a_receipt(
    stand_in: Path, tmp_path: Path
) -> None:
    write_output(tmp_path, "v3")
    adapter = runtime.RustSimulationV3(
        binary=stand_in, policy_sha256=POLICY_SHA256, build_sha256=build_sha256(stand_in)
    )
    receipt = adapter.validate(
        target=target(),
        model_role="CHAMPION",
        model_artifact_sha256=MODEL_SHA256,
        distribution=distribution(),
    )

    raw, document = captured_input(tmp_path)
    assert_input_contract(raw, document, "v3")
    assert document["protocol_id"] == golden()["runs"]["v3"]["protocol_id"]
    assert document["forecast_id"] == f"{MATCH_ID}:champion"
    assert receipt.input_sha256 == hashlib.sha256(raw).hexdigest()
    assert (
        receipt.output_sha256 == hashlib.sha256((tmp_path / "output.json").read_bytes()).hexdigest()
    )
    assert receipt.rust_build_sha256 == build_sha256(stand_in)
    assert (receipt.status, receipt.simulation_count) == ("PASS", runtime.SIMULATION_COUNT)


def test_v4_adapter_writes_the_contract_and_carries_warnings(
    stand_in: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "V3_CANONICALIZER_SHA256", build_sha256(stand_in))
    write_output(
        tmp_path,
        "v4",
        status="PASS_WITH_WARNINGS",
        warnings=["score:0-0 exceeds event warning limit"],
    )
    adapter = runtime.RustSimulationV4(
        binary=stand_in,
        canonicalizer_binary=stand_in,
        policy_sha256=POLICY_SHA256,
        build_sha256=build_sha256(stand_in),
    )
    receipt = adapter.validate(
        target=target(),
        model_role="CHALLENGER",
        model_artifact_sha256=MODEL_SHA256,
        distribution=distribution(),
    )

    raw, document = captured_input(tmp_path)
    assert_input_contract(raw, document, "v4")
    assert document["protocol_id"] == runtime.V4_PROTOCOL_ID
    assert isinstance(receipt, V4SimulationReceiptV1)
    assert receipt.status == "PASS_WITH_WARNINGS"
    assert receipt.warnings == ("score:0-0 exceeds event warning limit",)
    assert receipt.total_variation is not None
    assert receipt.total_variation_limit is not None
    assert receipt.total_variation <= receipt.total_variation_limit


def test_adapters_refuse_an_executable_with_the_wrong_identity(stand_in: Path) -> None:
    with pytest.raises(runtime.PitchApiV3RuntimeError, match="executable identity mismatch"):
        runtime.RustSimulationV3(
            binary=stand_in, policy_sha256=POLICY_SHA256, build_sha256="0" * 64
        )
    with pytest.raises(runtime.PitchApiV3RuntimeError, match="V4 Rust executable identity"):
        runtime.RustSimulationV4(
            binary=stand_in,
            canonicalizer_binary=stand_in,
            policy_sha256=POLICY_SHA256,
            build_sha256="0" * 64,
        )
    with pytest.raises(runtime.PitchApiV3RuntimeError, match="canonicalizer identity mismatch"):
        runtime.RustSimulationV4(
            binary=stand_in,
            canonicalizer_binary=stand_in,
            policy_sha256=POLICY_SHA256,
            build_sha256=build_sha256(stand_in),
        )


@pytest.mark.parametrize(
    ("mode", "overrides", "message"),
    [
        ("fail", {}, "Rust simulation failed: PARITY_FAILURE"),
        ("diverge", {}, "serial/parallel replay mismatch"),
        ("", {"status": "FAIL"}, "not PASS"),
        ("", {"simulation_count": 1}, "not PASS"),
    ],
)
def test_v3_adapter_fails_closed(
    stand_in: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    overrides: dict[str, object],
    message: str,
) -> None:
    monkeypatch.setenv("STAND_IN_MODE", mode)
    write_output(tmp_path, "v3", **overrides)
    adapter = runtime.RustSimulationV3(
        binary=stand_in, policy_sha256=POLICY_SHA256, build_sha256=build_sha256(stand_in)
    )
    with pytest.raises(runtime.PitchApiV3RuntimeError, match=message):
        adapter.validate(
            target=target(),
            model_role="CHAMPION",
            model_artifact_sha256=MODEL_SHA256,
            distribution=distribution(),
        )


@pytest.mark.parametrize(
    ("mode", "overrides", "message"),
    [
        ("fail", {}, "V4 Rust simulation failed: PARITY_FAILURE"),
        ("diverge", {}, "serial/parallel replay mismatch"),
        ("", {"status": "FAIL"}, "did not pass"),
        ("", {"simulation_count": 1}, "simulation count mismatch"),
    ],
)
def test_v4_adapter_fails_closed(
    stand_in: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    overrides: dict[str, object],
    message: str,
) -> None:
    monkeypatch.setattr(runtime, "V3_CANONICALIZER_SHA256", build_sha256(stand_in))
    monkeypatch.setenv("STAND_IN_MODE", mode)
    write_output(tmp_path, "v4", **overrides)
    adapter = runtime.RustSimulationV4(
        binary=stand_in,
        canonicalizer_binary=stand_in,
        policy_sha256=POLICY_SHA256,
        build_sha256=build_sha256(stand_in),
    )
    with pytest.raises(runtime.PitchApiV3RuntimeError, match=message):
        adapter.validate(
            target=target(),
            model_role="CHALLENGER",
            model_artifact_sha256=MODEL_SHA256,
            distribution=distribution(),
        )


def test_adapter_stops_waiting_for_a_hung_executable(
    stand_in: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime, "_RUST_TIMEOUT_SECONDS", 0.5)
    monkeypatch.setenv("STAND_IN_MODE", "hang")
    write_output(tmp_path, "v3")
    adapter = runtime.RustSimulationV3(
        binary=stand_in, policy_sha256=POLICY_SHA256, build_sha256=build_sha256(stand_in)
    )
    with pytest.raises(
        runtime.PitchApiV3RuntimeError, match="Rust simulation failed: no result within 0.5 seconds"
    ):
        adapter.validate(
            target=target(),
            model_role="CHAMPION",
            model_artifact_sha256=MODEL_SHA256,
            distribution=distribution(),
        )
