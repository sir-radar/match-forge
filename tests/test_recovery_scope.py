import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import recovery_scope
from scripts.recovery_files import FileReference
from scripts.recovery_scope import inspect_references, load_plan, unavailable_hash


def test_exact_retained_copy_and_missing_registration_are_distinct(tmp_path: Path) -> None:
    payload = b"original evidence"
    (tmp_path / "retained").write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    owner = {"table": "model_artifacts", "keys": {"id": "registered-id"}}
    ref = FileReference("data", "missing", digest, len(payload), (owner,))
    roots = {"data": tmp_path / "data", "repository": tmp_path}
    found = inspect_references([ref], roots, {digest: "retained"})
    assert found["references"] == [replace(ref, source_path="retained")]
    assert found["logical_bytes"] == len(payload)
    assert not found["unavailable"]
    (tmp_path / "retained").write_bytes(b"different bytes")
    missing = inspect_references([ref], roots, {digest: "retained"})
    assert not missing["references"]
    assert missing["unavailable"][0]["registrations"] == (owner,)


def test_gap_binding_ignores_environment_errors_but_preserves_exact_ids() -> None:
    item = {"path": "missing", "sha256": "a" * 64, "registration": {"id": "one"}}
    assert unavailable_hash([item]) == unavailable_hash([{**item, "reason": "new machine"}])
    assert unavailable_hash([item]) != unavailable_hash([{**item, "registration": {"id": "two"}}])


def test_plan_rejects_changed_gaps_and_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recovery_scope, "ROOT", tmp_path)
    plan = {
        "scope": "RECOVERABLE_ONLY",
        "unavailable": [],
        "unavailable_sha256": unavailable_hash([]),
        "locations": {"a" * 64: "retained/file"},
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    assert load_plan(path) == plan
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(ValueError, match="symlink"):
        load_plan(link)
    plan["unavailable"].append({"path": "new missing dependency"})
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="bindings"):
        load_plan(path)
