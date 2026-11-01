"""Read-only qualification of an exact retained StatsBomb match-index population."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from football.contracts.source import canonical_json_bytes
from football.identity.repository import IdentityRepository
from football.product.identity_admission import (
    RetainedIdentityVerifier,
    classify_mapping,
    mapping_rows,
)
from football.product.resolution_actions import preview
from football.providers.normalization.cli import registered_resource
from football.storage.raw import ImmutableFileStore
from psycopg import Connection


def pilot_matches(connection: Connection[Any], root: Path, resource: UUID) -> list[dict[str, Any]]:
    context, raw = registered_resource(connection, root, resource)
    if context.provenance.provider != "statsbomb_open_data":
        raise ValueError("pilot requires an exact retained StatsBomb match index")
    rows: list[dict[str, Any]] = json.loads(raw)
    ids = [str(row["match_id"]) for row in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("pilot fixture IDs must be nonempty and unique")
    scopes = {(row["competition"]["competition_id"], row["season"]["season_id"]) for row in rows}
    if len(scopes) != 1:
        raise ValueError("pilot requires one exact native competition and season")
    return sorted(rows, key=lambda row: str(row["match_id"]))


def identity_report(
    connection: Connection[Any], root: Path, matches: list[dict[str, Any]], cutoff: datetime
) -> dict[str, Any]:
    """Use current owner proofs; no mapping claim is converted into an admission."""
    provider = connection.execute(
        "SELECT id FROM football.providers WHERE code='statsbomb_open_data'"
    ).fetchone()
    assert provider is not None
    repository = IdentityRepository(connection)
    verifier = RetainedIdentityVerifier(root)
    team_ids = {
        str(row[side][side + "_id"]) for row in matches for side in ("home_team", "away_team")
    }
    competition_ids = {str(row["competition"]["competition_id"]) for row in matches}
    mappings = []
    for kind, ids in (("team", team_ids), ("competition", competition_ids)):
        for row in mapping_rows(connection, kind, "statsbomb_open_data"):
            if row[3] in ids:
                decision = classify_mapping(connection, kind, row, root, verifier)
                proof = repository.admission_proof_at(kind, row[0], cutoff)
                mappings.append({**decision, "admitted_proof": proof.to_dict() if proof else None})
    fixtures = []
    for match in matches:
        native = str(match["match_id"])
        claims = repository.mapping_at(
            "match", provider[0], native, valid_at=cutoff, knowledge_cutoff=cutoff
        )
        resolutions = connection.execute(
            """SELECT id,status,selected_canonical_id FROM football.resolution_decisions d
            WHERE provider_id=%s AND subject_type='match' AND provider_entity_id=%s
              AND created_at<=%s AND NOT EXISTS (
                SELECT 1 FROM football.resolution_decisions s
                WHERE s.supersedes_decision_id=d.id AND s.created_at<=%s)
            ORDER BY id""",
            (provider[0], native, cutoff, cutoff),
        ).fetchall()
        fixtures.append(
            {
                "native_fixture_id": native,
                "recorded_match_claims": [str(claim.canonical_id) for claim in claims],
                "current_resolution_decisions": [
                    {"id": str(key), "status": status, "canonical_id": str(canonical)}
                    for key, status, canonical in resolutions
                ],
                "qualification": "MISSING_PROOF",
                "blocker": "No admitted exact StatsBomb fixture/participant/competition chain",
            }
        )
    legacy = connection.execute(
        """SELECT p.code,d.subject_type,d.status,count(*) FROM football.resolution_decisions d
        JOIN football.providers p ON p.id=d.provider_id WHERE d.created_at<=%s
        GROUP BY 1,2,3 ORDER BY 1,2,3""",
        (cutoff,),
    ).fetchall()
    prior = json.loads(Path("docs/evidence/matchforge-v4-phase-02-2026-10-31.json").read_text())
    cases = []
    for case in prior["cases"]:
        result = preview(
            connection,
            root,
            {
                "case_key": case["case_key"],
                "action": "APPROVE",
                "reason": "Issue 2 read-only recheck of retained exact identity evidence",
            },
            verifier,
        )
        cases.append(
            {
                "case_key": result["case_key"],
                "qualification": result["qualification"],
                "evidence_version": result["evidence_version"],
                "approval_required": result["approval_required"],
                "applied": False,
            }
        )
    return {
        "status": "BLOCKED_WITH_EVIDENCE",
        "pilot_fixtures": len(matches),
        "native_teams": len(team_ids),
        "native_competitions": len(competition_ids),
        "owner_mapping_checks": mappings,
        "fixtures": fixtures,
        "existing_resolution_counts": [list(row) for row in legacy],
        "prior_resolution_center_cases": cases,
        "new_canonical_identities": 0,
        "contradictions_resolved": 0,
        "resource_rows_unlocked": 0,
        "historical_eligibility_delta": 0,
        "limitations": [
            "Claims are inspected at the explicit audit cutoff, not reconstructed as prior "
            "knowledge or as football-valid historical mappings.",
            "The ten accepted Football-Data UK match resolutions bind exact CSV record keys; "
            "they do not admit another provider's native fixture references.",
            "StatsBomb retained bytes verify native relationships but the existing R2 source "
            "verifier and origin rules do not admit these UUID claims. No permissive rule added.",
            "Owner review needs independently verified source/canonical anchors and, for "
            "anonymous CSV references, exact source-record publication proof.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--match-resource-id", required=True, type=UUID)
    parser.add_argument("--artifact-root", required=True, type=Path)
    args = parser.parse_args(argv)
    with (
        psycopg.connect(
            args.database_url, options="-c default_transaction_read_only=on", connect_timeout=5
        ) as connection,
        connection.transaction(),
    ):
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = connection.execute("SELECT transaction_timestamp()").fetchone()
        assert snapshot is not None
        matches = pilot_matches(connection, args.source_root, args.match_resource_id)
        report = identity_report(connection, args.source_root, matches, snapshot[0])
        report.update(
            {
                "phase": "R02-B",
                "knowledge_cutoff": snapshot[0].isoformat(),
                "match_resource_id": str(args.match_resource_id),
                "operating_writes": 0,
                "provider_requests": 0,
            }
        )
    payload = canonical_json_bytes(report) + b"\n"
    artifact = ImmutableFileStore(args.artifact_root).publish(
        "pilot/" + hashlib.sha256(payload).hexdigest() + ".json", payload
    )
    print(json.dumps({"report": str(artifact.path), "sha256": artifact.sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
