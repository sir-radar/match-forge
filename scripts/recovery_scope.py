"""Registered recovery inventory with exact retained-byte locations and explicit gaps."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

from scripts.capture_architecture_v2_baseline import ROOT, file_sha256
from scripts.recovery_dispositions import disposition_records, recorded_dispositions
from scripts.recovery_files import FileReference, registered_files, regular_file


def _verified_file(ref: FileReference, roots: Mapping[str, Path]) -> FileReference:
    path = regular_file(
        roots["repository"] if ref.source_path is not None else roots[ref.root],
        ref.source_path if ref.source_path is not None else ref.path,
    )
    before = path.stat()
    if ref.size is not None and before.st_size != ref.size:
        raise ValueError("registered size mismatch")
    digest = file_sha256(path)
    if ref.sha256 is not None and digest != ref.sha256:
        raise ValueError("registered checksum mismatch")
    after = path.stat()
    if (before.st_ino, before.st_mtime_ns, before.st_size) != (
        after.st_ino,
        after.st_mtime_ns,
        after.st_size,
    ):
        raise ValueError("source changed during inventory")
    return replace(ref, sha256=digest, size=before.st_size)


def _located_file(
    ref: FileReference, roots: Mapping[str, Path], locations: Mapping[str, str]
) -> FileReference:
    candidates = [ref]
    if ref.sha256 is not None and ref.sha256 in locations:
        candidates.append(replace(ref, source_path=locations[ref.sha256]))
    failure: Exception = ValueError("no original location")
    for candidate in candidates:
        try:
            return _verified_file(candidate, roots)
        except (OSError, ValueError) as error:
            failure = error
    raise failure


def inspect_references(
    refs: list[FileReference], roots: Mapping[str, Path], locations: Mapping[str, str]
) -> dict[str, Any]:
    available = []
    unavailable = []
    for ref in refs:
        try:
            available.append(_located_file(ref, roots, locations))
        except (OSError, ValueError) as error:
            unavailable.append({**asdict(ref), "error": type(error).__name__, "reason": str(error)})
    return {
        "references": available,
        "unavailable": unavailable,
        "logical_bytes": sum(ref.size or 0 for ref in available),
    }


def inventory(
    connection: Connection[Any],
    data_root: Path,
    repository_root: Path,
    locations: Mapping[str, str],
) -> dict[str, Any]:
    unresolved: list[dict[str, Any]] = []
    refs = registered_files(
        connection, data_root, unresolved=unresolved, repository_root=repository_root
    )
    result = inspect_references(refs, {"data": data_root, "repository": repository_root}, locations)
    result["unavailable"], result["excluded"] = exclude_disposed(
        [*result["unavailable"], *unresolved], recorded_dispositions(connection)
    )
    result["registered_references"] = len(refs) + len(unresolved)
    result["unavailable_sha256"] = unavailable_hash(result["unavailable"])
    result["excluded_sha256"] = unavailable_hash(result["excluded"])
    result["governed_sha256"] = governed_hash(result["excluded"], disposition_records(connection))
    return result


def _disposition(
    owner: Mapping[str, Any] | None, recorded: Mapping[tuple[str, str], tuple[str, str]]
) -> str | None:
    if not owner or not isinstance(owner.get("keys"), dict) or "id" not in owner["keys"]:
        return None
    found = recorded.get((str(owner["table"]), str(owner["keys"]["id"])))
    if found is None or found[1] != owner.get("registered_sha256"):
        return None
    return found[0]


def exclude_disposed(
    issues: list[dict[str, Any]], recorded: Mapping[tuple[str, str], tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Move an unavailable dependency out of scope only when every registration owning it
    has a recorded disposition bound to the same registered checksum."""
    unavailable: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in issues:
        owners = list(item.get("registrations") or [item.get("registration")])
        dispositions = [_disposition(owner, recorded) for owner in owners]
        if all(dispositions):
            excluded.append({**item, "dispositions": dispositions})
        else:
            unavailable.append(item)
    return unavailable, excluded


def _dependency_binding(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "root": item.get("root", "data"),
        "path": item.get("path"),
        "sha256": item.get("sha256"),
        "size": item.get("size"),
        "registrations": item.get("registrations", [item.get("registration")]),
    }


def _digest(bindings: list[Any]) -> str:
    encoded = sorted(json.dumps(item, sort_keys=True, separators=(",", ":")) for item in bindings)
    return hashlib.sha256(json.dumps(encoded, separators=(",", ":")).encode()).hexdigest()


def unavailable_hash(issues: list[dict[str, Any]]) -> str:
    return _digest([_dependency_binding(item) for item in issues])


def governed_hash(
    excluded: list[dict[str, Any]], records: Mapping[tuple[str, str], Mapping[str, str]]
) -> str:
    """Bind each excluded dependency to the exact approved disposition of every owner.

    Fails when any owner lacks a recorded disposition bound to its registered checksum,
    so a shared path is only governed when all of its registrations are.
    """
    bindings = []
    for item in excluded:
        approvals = []
        for owner in item.get("registrations") or [item.get("registration")]:
            keys = owner.get("keys") if isinstance(owner, Mapping) else None
            if not isinstance(keys, Mapping) or "id" not in keys:
                raise ValueError("an excluded dependency lacks an approved disposition per owner")
            key = (str(owner["table"]), str(keys["id"]))
            record = records.get(key)
            if record is None or record["registered_sha256"] != owner.get("registered_sha256"):
                raise ValueError("an excluded dependency lacks an approved disposition per owner")
            approvals.append({"table": key[0], "id": key[1], **record})
        approvals.sort(key=lambda value: (value["table"], value["id"]))
        bindings.append({"dependency": _dependency_binding(item), "approvals": approvals})
    return _digest(bindings)


def require_inventory_database(connection: Connection[Any], plan: dict[str, Any]) -> None:
    state = connection.execute(
        "SELECT current_database(),oid::text FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    if state is None or tuple(state) != (plan["database"], plan["database_oid"]):
        raise ValueError("recovery inventory belongs to a different database")


def selected_inventory(
    connection: Connection[Any], data_root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    require_inventory_database(connection, plan)
    result = inventory(connection, data_root, ROOT, plan["locations"])
    if result["unavailable_sha256"] != plan["unavailable_sha256"] or result[
        "excluded_sha256"
    ] != plan.get("excluded_sha256", EMPTY_SHA256):
        raise ValueError("unavailable dependencies changed; inspect a fresh recovery inventory")
    return result


EMPTY_SHA256 = unavailable_hash([])


GOVERNED_SCOPE = "GOVERNED_SCOPE"
SHA256_HEX = frozenset("0123456789abcdef")


def validate_gaps(value: dict[str, Any], scope: str = "RECOVERABLE_ONLY") -> None:
    if (
        value["scope"] != scope
        or unavailable_hash(value["unavailable"]) != value["unavailable_sha256"]
        or unavailable_hash(value.get("excluded", [])) != value.get("excluded_sha256", EMPTY_SHA256)
    ):
        raise ValueError("recovery plan scope or unavailable bindings are invalid")


def validate_governed(value: dict[str, Any]) -> None:
    """A governed scope has no unexplained gap and binds every exclusion to its approvals."""
    digest = value.get("governed_sha256")
    validate_gaps(value, value["scope"])
    if value["scope"] not in ("RECOVERABLE_ONLY", GOVERNED_SCOPE):
        raise ValueError("governed scope requires a reviewed recovery inventory")
    if value["unavailable"] or not value.get("excluded"):
        raise ValueError("governed scope requires zero unavailable and at least one exclusion")
    if not isinstance(digest, str) or len(digest) != 64 or not set(digest) <= SHA256_HEX:
        raise ValueError("governed scope requires the reviewed disposition binding")
    for item in value["excluded"]:
        owners = item.get("registrations") or [item.get("registration")]
        dispositions = item.get("dispositions") or []
        if len(dispositions) != len(owners) or not all(dispositions):
            raise ValueError("every owner of an excluded dependency needs a disposition")


def selected_governed_inventory(
    connection: Connection[Any], data_root: Path, plan: dict[str, Any]
) -> dict[str, Any]:
    """The reviewed inventory, rechecked: no new gap and identical approved exclusions."""
    validate_governed(plan)
    result = selected_inventory(connection, data_root, plan)
    if result["unavailable"] or result["governed_sha256"] != plan["governed_sha256"]:
        raise ValueError("governed exclusions or approvals changed; review a fresh inventory")
    return result


def load_plan(path: Path) -> dict[str, Any]:
    relative = path.absolute().relative_to(ROOT).as_posix()
    value: dict[str, Any] = json.loads(regular_file(ROOT, relative).read_text())
    validate_gaps(value)
    for digest, source in value["locations"].items():
        FileReference("repository", source, digest)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("FOOTBALL_DATA_ROOT", str(ROOT / ".local/football-data"))),
    )
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    locations = json.loads(args.locations.read_text())
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        options="-c default_transaction_read_only=on -c statement_timeout=60000",
    ) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        state = connection.execute(
            "SELECT transaction_timestamp(),current_database(),oid::text "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        assert state is not None
        result = inventory(connection, args.data_root, ROOT, locations)
        connection.rollback()
    plan = {
        "scope": "RECOVERABLE_ONLY",
        "observed_at": state[0].isoformat(),
        "database": state[1],
        "database_oid": state[2],
        "locations": locations,
        "unavailable": result["unavailable"],
        "unavailable_sha256": result["unavailable_sha256"],
        "excluded": result["excluded"],
        "excluded_sha256": result["excluded_sha256"],
        "governed_sha256": result["governed_sha256"],
        "logical_bytes": result["logical_bytes"],
        "available_files": len(result["references"]),
        "registered_references": result["registered_references"],
    }
    with args.output.open("x") as output:
        json.dump(plan, output, indent=2, sort_keys=True)
        output.write("\n")
    print(
        json.dumps(
            {
                key: plan[key]
                for key in ("scope", "logical_bytes", "available_files", "registered_references")
            }
            | {
                "unavailable": len(plan["unavailable"]),
                "excluded": len(plan["excluded"]),
                "full_recovery": False,
            }
        )
    )


if __name__ == "__main__":
    main()
