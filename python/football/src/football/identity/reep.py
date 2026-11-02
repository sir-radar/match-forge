"""Exact Reep v1 bridge evidence for operator review; never identity admission."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import polars as pl

from football.contracts.source import canonical_json_bytes
from football.storage.raw import ImmutableFileStore


def _verified_release(path: Path, checksum: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("Reep release checksum mismatch")
    release: dict[str, Any] = json.loads(raw)
    if release.get("schema") != "reep-public-release/v4" or not release.get("stamp"):
        raise ValueError("unsupported Reep release; dated v1 distribution required")
    for name in ("bridges.csv.gz", "redirects.csv.gz"):
        expected = release["files"][name]
        file = path.parent / name
        if file.stat().st_size != expected["bytes"]:
            raise ValueError(f"Reep {name} length mismatch")
        with file.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected["sha256"]:
                raise ValueError(f"Reep {name} checksum mismatch")
    return release


def _rows(path: Path, required: set[str]) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if not required <= set(reader.fieldnames or ()):
            raise ValueError(f"Reep {path.name} missing required columns")
        for row in reader:
            if None in row or any(row.get(field) in (None, "") for field in required):
                raise ValueError(f"Reep {path.name} malformed row")
            yield row


def _redirect_chain(identifier: str, redirects: Mapping[str, str]) -> list[str]:
    chain = [identifier]
    seen = {identifier}
    while identifier in redirects:
        identifier = redirects[identifier]
        if identifier in seen:
            raise ValueError("Reep redirect cycle")
        seen.add(identifier)
        chain.append(identifier)
    return chain


def _redirects(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in _rows(path, {"from_id", "to_id"}):
        source, target = row["from_id"], row["to_id"]
        if source in result and result[source] != target:
            raise ValueError("conflicting Reep redirects")
        result[source] = target
    for identifier in result:
        _redirect_chain(identifier, result)
    return result


def _native(row: Mapping[str, str]) -> tuple[str, str, str]:
    fields = ("provider", "namespace", "external_id")
    if any(not isinstance(row.get(key), str) or not row[key] for key in fields):
        raise ValueError("exact provider, namespace and external_id are required")
    return row["provider"], row["namespace"], row["external_id"]


def _peer_conflicts(rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    namespaces: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        namespaces[row["provider"], row["namespace"]].add(row["external_id"])
    return [
        {"provider": provider, "namespace": namespace, "external_ids": sorted(ids)}
        for (provider, namespace), ids in sorted(namespaces.items())
        if len(ids) > 1
    ]


def _bridge_rows(table: pl.LazyFrame) -> Iterator[dict[str, str]]:
    for row in table.collect(engine="streaming").iter_rows(named=True):
        required = ("reep_id", "provider", "namespace", "external_id", "entity_type")
        if any(not isinstance(row.get(key), str) or not row[key] for key in required):
            raise ValueError("Reep bridge missing identity fields")
        yield cast(dict[str, str], row)


def bridge_candidates(
    release_path: Path, release_sha256: str, inventory: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Join explicit namespace/native IDs; preserve source rows and reject conflicts.

    Two streaming passes avoid loading the full register. The supplied
    inventory must translate MatchForge provider codes explicitly, including
    StatsBomb Open Data to Reep's statsbomb namespace. No names are compared.
    """
    release = _verified_release(release_path, release_sha256)
    redirects = _redirects(release_path.parent / "redirects.csv.gz")
    keys = {_native(row) for row in inventory}
    required = {"reep_id", "provider", "namespace", "external_id", "entity_type"}
    matched: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    table = pl.scan_csv(
        release_path.parent / "bridges.csv.gz",
        infer_schema=False,
        empty_string_is_null=False,
    )
    if not required <= set(table.collect_schema().names()):
        raise ValueError("Reep bridges missing required columns")
    if keys:
        lookup = pl.DataFrame(
            sorted(keys), schema=["provider", "namespace", "external_id"], orient="row"
        )
        for row in _bridge_rows(table.join(lookup.lazy(), on=lookup.columns, how="semi")):
            matched[_native(row)].append(row)
    selected = {
        _redirect_chain(row["reep_id"], redirects)[-1] for rows in matched.values() for row in rows
    }
    peers: dict[str, list[dict[str, str]]] = defaultdict(list)
    resolved = {key: _redirect_chain(key, redirects)[-1] for key in redirects}
    if selected:
        selection = (
            table.with_columns(
                pl.col("reep_id")
                .replace_strict(resolved, default=pl.col("reep_id"))
                .alias("_resolved")
            )
            .filter(pl.col("_resolved").is_in(sorted(selected)))
            .drop("_resolved")
        )
        for row in _bridge_rows(selection):
            identifier = _redirect_chain(row["reep_id"], redirects)[-1]
            peers[identifier].append(row)
    candidates, conflicts = _candidates(inventory, matched, peers, redirects)
    return {
        "release": release["stamp"],
        "release_sha256": release_sha256,
        "files": {name: release["files"][name] for name in ("bridges.csv.gz", "redirects.csv.gz")},
        "inventory_native_ids": len(keys),
        "matched_native_ids": len(matched),
        "candidate_identities": len({row["reep_id"] for row in candidates}),
        "redirects": dict(sorted(redirects.items())),
        "candidates": candidates,
        "conflicts": conflicts,
        "identities_admitted": 0,
        "admission_permission": False,
        "review_owner": "Resolution Center; existing identity admission and origin proof rules",
        "data_classification": "EXPERIMENTAL_ONLY",
    }


def _candidates(
    inventory: Sequence[dict[str, Any]],
    matched: Mapping[tuple[str, str, str], list[dict[str, str]]],
    peers: Mapping[str, list[dict[str, str]]],
    redirects: Mapping[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for item in inventory:
        rows = sorted(matched.get(_native(item), []), key=lambda row: tuple(sorted(row.items())))
        if not rows:
            continue
        identifiers = {_redirect_chain(row["reep_id"], redirects)[-1] for row in rows}
        if len(identifiers) != 1:
            conflicts.append({"inventory": item, "conflicting_reep_ids": sorted(identifiers)})
            continue
        identifier = next(iter(identifiers))
        bridges = sorted(peers[identifier], key=lambda row: tuple(sorted(row.items())))
        problems = _peer_conflicts(bridges)
        types = {row["entity_type"] for row in bridges}
        if len(types) != 1 or (item.get("entity_type") and types != {item["entity_type"]}):
            problems.append({"entity_types": sorted(types), "expected": item.get("entity_type")})
        if problems:
            conflicts.append({"inventory": item, "reep_id": identifier, "conflicts": problems})
            continue
        candidates.append(
            {
                "inventory": item,
                "reep_id": identifier,
                "redirect_chain": _redirect_chain(rows[0]["reep_id"], redirects),
                "source_rows": rows,
                "bridges": bridges,
                "admission_permission": False,
            }
        )
    return candidates, conflicts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--release-sha256", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = bridge_candidates(
        args.release, args.release_sha256, json.loads(args.inventory.read_text())
    )
    raw = canonical_json_bytes(result)
    saved = ImmutableFileStore(args.artifact_root).publish(
        "identity-evidence/reep/" + hashlib.sha256(raw).hexdigest() + ".json", raw
    )
    print(
        json.dumps(
            {
                "path": str(saved.path),
                "sha256": saved.sha256,
                "matched_native_ids": result["matched_native_ids"],
                "candidate_identities": result["candidate_identities"],
                "conflicts": len(result["conflicts"]),
                "identities_admitted": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
