"""Classify recovery contradictions without changing registrations or fabricating files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def short_digest_universe(length: int) -> set[str]:
    if length not in (1, 2):
        raise ValueError("exhaustive proof is bounded to one or two bytes")
    return {
        hashlib.sha256(value.to_bytes(length, "big")).hexdigest() for value in range(256**length)
    }


def investigate(plan: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    universes = {length: short_digest_universe(length) for length in (1, 2)}
    candidates: dict[str, list[str]] = {}
    for group in manifest["duplicate_groups"]:
        if group["byte_redundancy_verified"]:
            candidates[group["sha256"]] = [copy["location"] for copy in group["copies"]]
    findings = []
    for original in plan["unavailable"]:
        length, digest = original.get("size"), original.get("sha256")
        impossible = (
            isinstance(digest, str)
            and type(length) is int
            and length in universes
            and digest not in universes[length]
        )
        findings.append(
            {
                "original_registration": original,
                "classification": "IMPOSSIBLE_CHECKSUM_FOR_REGISTERED_LENGTH"
                if impossible
                else "ORIGINAL_STILL_UNAVAILABLE",
                "exhaustively_tested_byte_values": 256**length if impossible else None,
                "exact_candidate_locations": candidates.get(digest, []),
                "required_action": "Governed registration correction; preserve original audit trail"
                if impossible
                else "Find and independently verify original bytes; no substitution",
            }
        )
    return {
        "scope": "read-only classification of the preserved unavailable inventory",
        "original_gap_digest": plan["unavailable_sha256"],
        "unavailable": len(findings),
        "impossible_checksum_length_pairs": sum(
            row["classification"] == "IMPOSSIBLE_CHECKSUM_FOR_REGISTERED_LENGTH" for row in findings
        ),
        "full_recovery": False,
        "registrations_modified": 0,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--reclamation-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.inventory.read_bytes()
    result = investigate(json.loads(original), json.loads(args.reclamation_manifest.read_bytes()))
    result["inventory_file_sha256"] = hashlib.sha256(original).hexdigest()
    with args.output.open("x") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    assert args.inventory.read_bytes() == original
    print(json.dumps({key: value for key, value in result.items() if key != "findings"}))


if __name__ == "__main__":
    main()
