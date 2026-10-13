"""Evidence-based audit using the same trust predicate as product ingestion."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import psycopg
from psycopg import Connection

from football.product.identity_admission import (
    RetainedIdentityVerifier,
    admit_provider_mappings,
    classify_mapping,
    mapping_rows,
)


def audit_report(
    connection: Connection[Any],
    data_root: Path = Path(".local/football-data"),
) -> dict[str, object]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    counts: Counter[str] = Counter()
    manifest_counts: Counter[str] = Counter()
    admissions = _admission_states(connection)
    admitted = 0
    verifier = RetainedIdentityVerifier(data_root)
    entity_types: tuple[Literal["team", "competition"], ...] = ("competition", "team")
    for entity_type in entity_types:
        for row in mapping_rows(connection, entity_type):
            decision = classify_mapping(connection, entity_type, row, data_root, verifier)
            state = admissions.get((entity_type, decision["mapping_id"]))
            decision["admission_disposition"] = state[0] if state else "NOT_ADMITTED"
            decision["currently_admitted"] = bool(state and state[1])
            admitted += int(decision["currently_admitted"])
            if state and state[0] == "REVOKED":
                decision["evidence_disposition"] = decision["disposition"]
                decision["disposition"] = "REVOKED"
            manifest_counts[
                decision["evidence"].get("manifest_classification", "NOT_VERIFIED")
            ] += 1
            groups[(entity_type, decision["canonical_id"])].append(decision)
            counts[decision["disposition"]] += 1
    findings = []
    verified_shared = 0
    for (group_type, canonical_id), decisions in sorted(groups.items()):
        providers = sorted({decision["provider"] for decision in decisions})
        if len(providers) <= 1:
            continue
        unsafe = [
            decision
            for decision in decisions
            if decision["disposition"] not in {"ORIGIN_ANCHOR", "CROSSWALK"}
        ]
        if not unsafe:
            verified_shared += 1
            continue
        findings.append(
            {
                "entity_type": group_type,
                "matchforge_id": canonical_id,
                "providers": providers,
                "mapping_count": len(decisions),
                "classification": "CONTRADICTORY"
                if any(decision["disposition"] == "CONTRADICTORY" for decision in unsafe)
                else "UNRESOLVED",
                "mapping_decisions": decisions,
            }
        )
    return {
        "contract": "ProviderIdentityAuditV2",
        "policy_version": "ProductIdentityTrustV1",
        "status": "FAIL" if findings or counts["CONTRADICTORY"] or counts["REVOKED"] else "PASS",
        "unsafe_shared_identity_count": len(findings),
        "verified_shared_identity_count": verified_shared,
        "mapping_classifications": dict(sorted(counts.items())),
        "manifest_classifications": dict(sorted(manifest_counts.items())),
        "legacy_manifest_unverified_snapshots": _legacy_manifest_counts(connection),
        "currently_admitted_mapping_count": admitted,
        "resources_checked": len(verifier.indexes),
        "source_bytes_verified": verifier.source_bytes_verified,
        "findings": findings,
    }


def _legacy_manifest_counts(connection: Connection[Any]) -> dict[str, int]:
    rows = connection.execute(
        """SELECT p.code, count(*) FROM football.source_snapshots s
           JOIN football.providers p ON p.id = s.provider_id
           WHERE p.code IN ('openfootball', 'football_data_uk')
             AND s.source_revision NOT LIKE 'manifest-v1:%'
           GROUP BY p.code ORDER BY p.code"""
    ).fetchall()
    return dict(rows)


def _admission_states(connection: Connection[Any]) -> dict[tuple[str, str], tuple[str, bool]]:
    exists = connection.execute(
        "SELECT to_regclass('football.product_identity_admissions') IS NOT NULL"
    ).fetchone()
    if not exists or not exists[0]:
        return {}
    rows = connection.execute(
        """SELECT entity_type, mapping_id, disposition,
                  football.product_mapping_trusted(entity_type, mapping_id, canonical_id)
           FROM (SELECT DISTINCT ON (entity_type, mapping_id) *
                 FROM football.product_identity_admissions
                 ORDER BY entity_type, mapping_id, decided_at DESC, decision_id DESC) latest"""
    ).fetchall()
    return {
        (kind, str(mapping)): (disposition, trusted) for kind, mapping, disposition, trusted in rows
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--data-root", type=Path, default=Path(".local/football-data"))
    parser.add_argument(
        "--admit-verified",
        action="store_true",
        help="Record prospective decisions from verified retained evidence; never backdate.",
    )
    args = parser.parse_args(argv)
    with psycopg.connect(args.database_url) as connection:
        if args.admit_verified:
            providers = connection.execute(
                "SELECT code FROM football.providers ORDER BY code"
            ).fetchall()
            for (provider,) in providers:
                admit_provider_mappings(connection, args.data_root, provider)
            connection.commit()
        report = audit_report(connection, args.data_root)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
