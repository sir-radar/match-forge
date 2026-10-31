"""Operator review of existing admissions; names discover candidates, never grant trust."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection

from football.product.domain import normalize_team_name, sha256_json
from football.product.identity_admission import (
    RetainedIdentityVerifier,
    classify_mapping,
    mapping_rows,
)
from football.product.identity_trust import explicit_target


def review_status(disposition: str, admitted: bool, has_candidates: bool, reason: str = "") -> str:
    if disposition == "CONTRADICTORY":
        return "CONTRADICTORY"
    if disposition == "REVOKED":
        return "BLOCKED"
    if disposition in {"ORIGIN_ANCHOR", "CROSSWALK"}:
        return "VERIFIED" if admitted else "NEEDS_REVIEW"
    if admitted or reason == "RETAINED_SOURCE_EVIDENCE_REQUIRED":
        return "BLOCKED"
    return "NEEDS_REVIEW" if has_candidates else "UNRESOLVED"


def mapping_detail(
    connection: Connection[Any],
    root: Path,
    kind: Literal["team", "competition"],
    key: UUID,
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    rows = mapping_rows(connection, kind, mapping_id=key)
    if len(rows) != 1:
        raise ValueError("current mapping not found")
    row = rows[0]
    decision = classify_mapping(connection, kind, row, root, verifier)
    latest = connection.execute(
        """SELECT to_jsonb(a), football.product_mapping_trusted(entity_type,mapping_id,canonical_id)
           FROM football.product_identity_admissions a WHERE entity_type=%s AND mapping_id=%s
           ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
        (kind, key),
    ).fetchone()
    candidates = mapping_candidates(connection, kind, row)
    if latest and latest[0]["disposition"] == "REVOKED":
        decision["evidence_disposition"] = decision["disposition"]
        decision["disposition"] = "REVOKED"
    impacts = connection.execute(
        """SELECT fixture_id FROM football.product_fixtures
           WHERE home_team_id=%s OR away_team_id=%s OR competition_id=%s
           ORDER BY fixture_id LIMIT 101""",
        (row[1], row[1], row[1]),
    ).fetchall()
    correction_options = (
        connection.execute(
            """SELECT d.decision_id,m.id,f.fixture_id,
                  CASE WHEN f.home_team_id=%s THEN 'HOME' ELSE 'AWAY' END
           FROM football.product_provider_mapping_decisions d
           JOIN football.product_fixtures f ON f.fixture_id=d.candidate_fixture_id
           JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
           JOIN football.providers p ON p.id=m.provider_id
           WHERE d.disposition='CONTRADICTORY' AND d.provider_code='fotmob'
             AND p.code=%s AND m.valid_to IS NULL
             AND (f.home_team_id=%s OR f.away_team_id=%s)
           ORDER BY d.decision_id,m.id LIMIT 20""",
            (row[1], row[2], row[1], row[1]),
        ).fetchall()
        if kind == "team"
        else []
    )
    result = {
        "case_key": f"{kind}:{key}",
        "status": review_status(
            decision["disposition"],
            bool(latest and latest[1]),
            bool(candidates),
            decision["reason"],
        ),
        "decision": decision,
        "mapping_version": [str(value) if value is not None else None for value in row],
        "admission": latest[0] if latest else None,
        "candidates": candidates,
        "correction_options": [
            dict(
                original_decision_id=str(d),
                fixture_registration_id=str(m),
                fixture_id=str(f),
                orientation=o,
            )
            for d, m, f, o in correction_options
        ],
        "affected_fixtures": [str(item[0]) for item in impacts[:100]],
        "affected_fixtures_has_more": len(impacts) > 100,
        "historical_effect": "Prospective decisions; earlier knowledge cutoffs stay unchanged.",
        "downstream_status": "NOT_REQUESTED",
    }
    result["evidence_version"] = sha256_json(result)
    return result


def mapping_candidates(
    connection: Connection[Any], kind: str, row: tuple[Any, ...]
) -> list[dict[str, Any]]:
    target = explicit_target(kind, row[2], row[3])
    if kind == "competition":
        return (
            [
                {
                    "provider": target[0],
                    "provider_id": target[1],
                    "reason": "EXISTING_EXPLICIT_CROSSWALK",
                    "admission_permission": False,
                }
            ]
            if target
            else []
        )
    source_name = connection.execute(
        "SELECT name FROM football.product_teams WHERE team_id=%s", (row[1],)
    ).fetchone()
    name = normalize_team_name(source_name[0]) if source_name else ""
    candidates = connection.execute(
        """SELECT DISTINCT m.id,m.team_id,p.code,m.provider_team_id,t.name,t.country,
                  m.mapping_method,m.source_snapshot_id
           FROM football.team_provider_mappings m JOIN football.providers p ON p.id=m.provider_id
           JOIN football.product_teams t ON t.team_id=m.team_id
           LEFT JOIN football.product_team_aliases a ON a.team_id=t.team_id
           WHERE m.valid_to IS NULL AND m.id<>%s AND (
               (p.code=%s AND m.provider_team_id=%s) OR
               (a.normalized_name=%s AND lower(coalesce(a.country,''))=lower(coalesce(%s,''))))
           ORDER BY p.code,m.provider_team_id,m.id LIMIT 50""",
        (row[0], target[0] if target else None, target[1] if target else None, name, row[6]),
    ).fetchall()
    return [
        dict(
            mapping_id=str(key),
            canonical_id=str(team),
            provider=provider,
            provider_id=identifier,
            name=label,
            country=country,
            method=method,
            source_snapshot_id=str(snapshot),
            admission_permission=False,
            reason="EXISTING_EXPLICIT_CROSSWALK"
            if target == (provider, identifier)
            else "ALIAS_DISCOVERY_ONLY_CATEGORY_AND_FIXTURE_EVIDENCE_REQUIRED",
        )
        for key, team, provider, identifier, label, country, method, snapshot in candidates
    ]
