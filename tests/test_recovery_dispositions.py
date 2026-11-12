import hashlib
import json
from collections import Counter

import pytest

from scripts.recovery_dispositions import (
    APPROVED_EVIDENCE,
    RecoveryDispositionError,
    approved_dispositions,
    evidence_dispositions,
)
from scripts.recovery_scope import exclude_disposed, unavailable_hash, validate_gaps


def test_approved_evidence_yields_160_retirements_and_one_path_digest_correction() -> None:
    retirements, corrections = approved_dispositions()
    assert len(retirements) == 160
    assert Counter(item.table for item in retirements) == {
        "source_snapshots": 33,
        "source_resources": 33,
        "model_artifacts": 26,
        "model_artifact_files": 26,
        "dataset_versions": 22,
        "baseline_forecasts": 13,
        "sprint2_evaluation_runs": 4,
        "dataset_files": 3,
    }
    assert {item.evidence_reference for item in retirements} == {r for r, _ in APPROVED_EVIDENCE}
    [correction] = corrections
    assert correction.source_snapshot_id == "7389bfe6-2d25-5b4c-b51e-e8f22e159c6d"
    assert correction.sha256 == hashlib.sha256(correction.path.encode()).hexdigest()
    reference, digest = APPROVED_EVIDENCE[0]
    with pytest.raises(RecoveryDispositionError, match="checksum"):
        evidence_dispositions(b"{}", reference, digest)


def _evidence(**changes: object) -> bytes:
    finding = {
        "table": "source_snapshots",
        "keys": {"id": "one"},
        "path": "manifests/one.json",
        "registered_sha256": "a" * 64,
        "classification": "SYNTHETIC_TEST_REGISTRATION_PLACEHOLDER_CHECKSUM",
    }
    value = {
        "gaps": 1,
        "full_recovery": False,
        "registrations_modified": 0,
        "fabricated_values": 0,
        "findings": [finding | changes],
    }
    return json.dumps(value).encode()


@pytest.mark.parametrize(
    ("changes", "message"),
    (
        ({"classification": "ORIGINAL_STILL_UNAVAILABLE"}, "no approved disposition"),
        ({"registered_sha256": None}, "lacks a registered checksum"),
        (
            {"classification": "MANIFEST_NEVER_WRITTEN_PATH_DIGEST", "table": "dataset_versions"},
            "no approved disposition",
        ),
    ),
)
def test_evidence_without_an_approved_disposition_fails_closed(
    changes: dict[str, object], message: str
) -> None:
    raw = _evidence(**changes)
    with pytest.raises(RecoveryDispositionError, match=message):
        evidence_dispositions(raw, "evidence.json", hashlib.sha256(raw).hexdigest())


def _owner(identity: str, digest: str, table: str = "source_snapshots") -> dict[str, object]:
    return {"table": table, "keys": {"id": identity}, "registered_sha256": digest}


def test_only_fully_disposed_gaps_with_matching_checksums_leave_scope() -> None:
    recorded = {
        ("source_snapshots", "retired"): ("SYNTHETIC_TEST_LINEAGE", "a" * 64),
        ("source_resources", "retired"): ("SYNTHETIC_TEST_LINEAGE", "c" * 64),
    }
    disposed = {"path": "a", "registrations": (_owner("retired", "a" * 64),)}
    unresolved = {"registration": _owner("retired", "c" * 64, "source_resources")}
    shared = {"path": "b", "registrations": (_owner("retired", "a" * 64), _owner("other", "a"))}
    changed = {"path": "c", "registrations": (_owner("retired", "b" * 64),)}
    repository = {"root": "repository", "path": "d", "registrations": ()}
    unavailable, excluded = exclude_disposed(
        [disposed, unresolved, shared, changed, repository], recorded
    )
    assert unavailable == [shared, changed, repository]
    assert [item["dispositions"] for item in excluded] == [["SYNTHETIC_TEST_LINEAGE"]] * 2


def test_plan_binds_excluded_dependencies() -> None:
    excluded = [{"path": "a", "registrations": [{"id": "one"}]}]
    plan = {
        "scope": "RECOVERABLE_ONLY",
        "unavailable": [],
        "unavailable_sha256": unavailable_hash([]),
        "excluded": excluded,
        "excluded_sha256": unavailable_hash(excluded),
    }
    validate_gaps(plan)
    validate_gaps({key: plan[key] for key in ("scope", "unavailable", "unavailable_sha256")})
    plan["excluded"] = []
    with pytest.raises(ValueError, match="bindings"):
        validate_gaps(plan)
