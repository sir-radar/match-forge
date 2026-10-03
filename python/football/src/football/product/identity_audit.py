"""Fail-closed audit for cross-provider canonical identity mappings."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Any

import psycopg
from psycopg import Connection

_TRUSTED_CROSS_PROVIDER_METHODS = ("explicit_crosswalk", "manual")


def unsafe_shared_identities(connection: Connection[Any]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for entity_type, table, identity_column, provider_identity_column in (
        (
            "competition",
            "football.competition_provider_mappings",
            "competition_id",
            "provider_competition_id",
        ),
        ("team", "football.team_provider_mappings", "team_id", "provider_team_id"),
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT mapping.{identity_column}::text,
                       array_agg(DISTINCT provider.code ORDER BY provider.code),
                       array_agg(DISTINCT mapping.mapping_method ORDER BY mapping.mapping_method),
                       count(DISTINCT (provider.code, mapping.{provider_identity_column}))
                FROM {table} mapping
                JOIN football.providers provider ON provider.id = mapping.provider_id
                WHERE mapping.valid_to IS NULL
                GROUP BY mapping.{identity_column}
                HAVING count(DISTINCT provider.code) > 1
                   AND bool_or(mapping.mapping_method NOT IN (%s, %s))
                ORDER BY mapping.{identity_column}
                """,
                _TRUSTED_CROSS_PROVIDER_METHODS,
            )
            for identity, providers, methods, mapping_count in cursor.fetchall():
                findings.append(
                    {
                        "entity_type": entity_type,
                        "matchforge_id": identity,
                        "providers": providers,
                        "mapping_methods": methods,
                        "mapping_count": mapping_count,
                    }
                )
    return findings


def audit_report(connection: Connection[Any]) -> dict[str, object]:
    findings = unsafe_shared_identities(connection)
    return {
        "contract": "ProviderIdentityAuditV1",
        "status": "FAIL" if findings else "PASS",
        "unsafe_shared_identity_count": len(findings),
        "findings": findings,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    args = parser.parse_args(argv)
    with psycopg.connect(args.database_url) as connection:
        report = audit_report(connection)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
