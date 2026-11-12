import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.source_manifest_bindings import (
    APPROVED_EVIDENCE,
    SourceManifestBindingError,
    approved_bindings,
    evidence_bindings,
)


def test_approved_evidence_binds_47_football_data_uk_snapshots() -> None:
    bindings = approved_bindings()
    assert len(bindings) == 47
    evidence = json.loads((ROOT / APPROVED_EVIDENCE[0]).read_text())
    assert evidence["path_digest_snapshots_by_provider"] == {
        "football_data_uk": 47,
        "openfootball": 1,
    }
    assert Counter(item["classification"] for item in evidence["findings"]) == {
        "RAW_FILE_PATH_DIGEST_RESOURCE_BOUND": 45,
        "RAW_FILE_PATH_DIGEST_SIBLING_BOUND": 2,
    }
    for item in bindings:
        assert item.sha256 == hashlib.sha256(item.path.encode()).hexdigest()
        assert Path(item.path).stem == item.resource_sha256
        assert item.path.startswith("football_data_uk/")
    # The OpenFootball never-written catalog is a different correction kind.
    assert "7389bfe6-2d25-5b4c-b51e-e8f22e159c6d" not in {b.source_snapshot_id for b in bindings}


def _evidence(**changes: object) -> bytes:
    path = "football_data_uk/2010-2011/" + "c" * 64 + ".zip"
    resource = {"id": "r", "sha256": "c" * 64, "size_bytes": 3}
    finding = {
        "classification": "RAW_FILE_PATH_DIGEST_RESOURCE_BOUND",
        "table": "source_snapshots",
        "keys": {"id": "one"},
        "path": path,
        "registered_sha256": hashlib.sha256(path.encode()).hexdigest(),
        "bound_resource": resource,
        "file": {"present": True, "sha256": "c" * 64, "size_bytes": 3},
    }
    value = {
        "registrations": 1,
        "registrations_modified": 0,
        "fabricated_values": 0,
        "findings": [finding | changes],
    }
    return json.dumps(value).encode()


def _load(raw: bytes) -> object:
    return evidence_bindings(raw, "evidence.json", hashlib.sha256(raw).hexdigest())


def test_valid_synthetic_evidence_yields_one_binding() -> None:
    [binding] = _load(_evidence())  # type: ignore[misc]
    assert binding.resource_size_bytes == 3


@pytest.mark.parametrize(
    "changes",
    (
        {"classification": "UNVERIFIED"},
        {"registered_sha256": "a" * 64},
        {"bound_resource": None},
        {"file": {"present": False, "error": "FileNotFoundError"}},
        {"file": {"present": True, "sha256": "c" * 64, "size_bytes": 4}},
        {"table": "source_resources"},
    ),
)
def test_unverified_findings_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(SourceManifestBindingError, match="no verified raw-file binding"):
        _load(_evidence(**changes))


def test_evidence_must_match_approval_and_be_read_only() -> None:
    reference, digest = APPROVED_EVIDENCE
    with pytest.raises(SourceManifestBindingError, match="checksum"):
        evidence_bindings(b"{}", reference, digest)
    raw = json.loads(_evidence())
    raw["registrations_modified"] = 1
    with pytest.raises(SourceManifestBindingError, match="read-only"):
        _load(json.dumps(raw).encode())
    raw = json.loads(_evidence())
    raw["findings"].append(raw["findings"][0])
    raw["registrations"] = 2
    with pytest.raises(SourceManifestBindingError, match="repeats"):
        _load(json.dumps(raw).encode())
