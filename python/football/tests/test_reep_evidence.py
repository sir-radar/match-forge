from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from football.identity.reep import bridge_candidates


def release(tmp_path: Path, rows: list[list[str]], redirects: list[list[str]]) -> tuple[Path, str]:
    files = {}
    for name, header, data in [
        (
            "bridges.csv.gz",
            [
                "reep_id",
                "provider",
                "namespace",
                "external_id",
                "entity_type",
                "independence_bucket",
                "route_scope",
                "rule_id",
                "confidence",
                "attached_at",
            ],
            rows,
        ),
        ("redirects.csv.gz", ["from_id", "to_id"], redirects),
    ]:
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(header)
        writer.writerows(data)
        raw = gzip.compress(out.getvalue().encode())
        (tmp_path / name).write_bytes(raw)
        files[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    raw = json.dumps(
        {"schema": "reep-public-release/v4", "stamp": "2026-10-31.1", "files": files}
    ).encode()
    path = tmp_path / "release.json"
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


def bridge(entity: str, provider: str, namespace: str, native: str) -> list[str]:
    return [
        entity,
        provider,
        namespace,
        native,
        "team",
        "NONE",
        "structural",
        "source-rule",
        "1.0",
        "",
    ]


def test_exact_namespace_redirect_and_provenance(tmp_path: Path) -> None:
    path, checksum = release(
        tmp_path,
        [
            bridge("old", "statsbomb", "team", "26"),
            bridge("new", "sofascore", "team", "33"),
            bridge("wrong", "statsbomb", "player", "26"),
        ],
        [["old", "new"]],
    )
    inventory: list[dict[str, Any]] = [
        {
            "provider": "statsbomb",
            "namespace": "team",
            "external_id": "26",
            "case_key": "team:existing",
        }
    ]
    result = bridge_candidates(path, checksum, inventory)
    assert result["matched_native_ids"] == 1
    assert result["candidate_identities"] == 1
    candidate = result["candidates"][0]
    assert candidate["redirect_chain"] == ["old", "new"]
    assert candidate["inventory"] == inventory[0]
    assert candidate["admission_permission"] is False
    assert candidate["bridges"][0]["confidence"] == "1.0"
    assert {r["external_id"] for r in candidate["bridges"]} == {"26", "33"}
    assert bridge_candidates(path, checksum, inventory) == result


def test_conflicting_native_bridge_is_rejected(tmp_path: Path) -> None:
    path, checksum = release(
        tmp_path,
        [bridge("one", "statsbomb", "team", "26"), bridge("two", "statsbomb", "team", "26")],
        [],
    )
    result = bridge_candidates(
        path, checksum, [{"provider": "statsbomb", "namespace": "team", "external_id": "26"}]
    )
    assert result["candidates"] == []
    assert len(result["conflicts"]) == 1


def test_conflicting_peer_namespace_is_rejected(tmp_path: Path) -> None:
    path, checksum = release(
        tmp_path,
        [
            bridge("one", "statsbomb", "team", "26"),
            bridge("one", "sofascore", "team", "33"),
            bridge("one", "sofascore", "team", "34"),
        ],
        [],
    )
    result = bridge_candidates(
        path, checksum, [{"provider": "statsbomb", "namespace": "team", "external_id": "26"}]
    )
    assert result["candidates"] == []
    assert result["conflicts"]


@pytest.mark.parametrize("redirects", [[["a", "b"], ["b", "a"]], [["a", "b"], ["a", "c"]]])
def test_invalid_redirects_fail_closed(tmp_path: Path, redirects: list[list[str]]) -> None:
    path, checksum = release(tmp_path, [bridge("a", "statsbomb", "team", "26")], redirects)
    with pytest.raises(ValueError, match="redirect"):
        bridge_candidates(path, checksum, [])


def test_file_and_manifest_checksums(tmp_path: Path) -> None:
    path, checksum = release(tmp_path, [], [])
    with pytest.raises(ValueError, match="checksum"):
        bridge_candidates(path, "0" * 64, [])
    (tmp_path / "bridges.csv.gz").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum|length"):
        bridge_candidates(path, checksum, [])


def test_v0_and_incomplete_inventory_are_rejected(tmp_path: Path) -> None:
    path, checksum = release(tmp_path, [], [])
    with pytest.raises(ValueError, match="namespace"):
        bridge_candidates(path, checksum, [{"provider": "statsbomb", "external_id": "26"}])
    path.write_text('{"schema":"v0"}')
    with pytest.raises(ValueError, match="release"):
        bridge_candidates(path, hashlib.sha256(path.read_bytes()).hexdigest(), [])


def test_entity_type_conflict_never_becomes_candidate(tmp_path: Path) -> None:
    row = bridge("one", "espn", "person", "26")
    path, checksum = release(tmp_path, [row], [])
    result = bridge_candidates(
        path,
        checksum,
        [{"provider": "espn", "namespace": "person", "external_id": "26", "entity_type": "player"}],
    )
    assert result["candidates"] == []
    assert result["conflicts"][0]["conflicts"][0]["expected"] == "player"
