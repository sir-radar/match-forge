"""Verify retained provider identifiers and record prospective identity decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from jsonschema import ValidationError
from psycopg import Connection
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.product.historical_manifest import verify_manifest
from football.product.identity_trust import (
    MappingEvidence,
    explicit_target,
    origin_id,
    qualify_mapping,
)
from football.storage.raw import ImmutableFileStore

TABLES = {
    "competition": (
        "competition_provider_mappings",
        "competition_id",
        "provider_competition_id",
        "product_competitions",
    ),
    "team": ("team_provider_mappings", "team_id", "provider_team_id", "product_teams"),
}


class RetainedIdentityVerifier:
    """An operation-scoped index of identities from verified immutable resource bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.knowledge_time = datetime.now(UTC)
        self.indexes: dict[tuple[object, ...], dict[tuple[str, str | None], set[str]]] = {}
        self.source_bytes_verified = 0

    def contains(
        self,
        provider: str,
        entity_type: str,
        identifier: str,
        country: str | None,
        row: tuple[Any, ...],
    ) -> bool:
        if row[9] > self.knowledge_time:
            return False
        key = (provider, row[5], row[7], row[8], row[1])
        if key not in self.indexes:
            try:
                payload = _retained_payload(self.root, provider, row)
                if payload is not None:
                    self.source_bytes_verified += len(payload)
                    self.indexes[key] = _identity_index(provider, payload, row[6], row[2])
                else:
                    self.indexes[key] = {}
            except (OSError, ValueError, KeyError, TypeError, ValidationError, RecursionError):
                self.indexes[key] = {}
        index = self.indexes[key]
        if provider not in {"openfootball", "football_data_uk"}:
            return identifier in index.get((entity_type, None), set())
        return any(
            identifier in values
            for (kind, context), values in index.items()
            if kind == entity_type and (country is None or context == country)
        )


def classify_mapping(
    connection: Connection[Any],
    entity_type: Literal["team", "competition"],
    row: tuple[Any, ...],
    data_root: Path,
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    if len(row) > 9 and row[9] is not None:
        from football.product.identity_correction import revalidate_team_correction

        return revalidate_team_correction(connection, data_root, row[9])
    mapping_id, canonical_id, provider, identifier, method, confidence, country, snapshot_id = row[
        :8
    ]
    proof = verify_source_identifier(
        connection, data_root, snapshot_id, provider, entity_type, identifier, country, verifier
    )
    target = explicit_target(entity_type, provider, identifier)
    target_id = origin_id(entity_type, *target, country) if target else None
    context_verified = False
    if target_id is not None:
        _, canonical_column, _, product_table = TABLES[entity_type]
        context = connection.execute(
            f"SELECT country FROM football.{product_table} WHERE {canonical_column} = %s",
            (target_id,),
        ).fetchone()
        context_verified = bool(
            context and country and context[0] and country.casefold() == context[0].casefold()
        )
    manual_review = _manual_review(connection, entity_type, row) if method == "manual" else None
    if proof is not None:
        proof["policy_version"] = "ProductIdentityTrustV1"
        if target is not None:
            proof["crosswalk_target"] = {"provider": target[0], "provider_entity_id": target[1]}
        if manual_review is not None:
            proof["operator_review"] = manual_review
    disposition, reason = qualify_mapping(
        MappingEvidence(
            entity_type,
            canonical_id,
            provider,
            identifier,
            method,
            confidence,
            country,
            proof is not None,
            proof is not None,
            target_id,
            context_verified,
            manual_review is not None,
        )
    )
    return {
        "mapping_id": str(mapping_id),
        "canonical_id": str(canonical_id),
        "entity_type": entity_type,
        "provider": provider,
        "provider_id": identifier,
        "disposition": disposition,
        "reason": reason,
        "source_snapshot_id": str(snapshot_id),
        "evidence": proof or {},
        "source_observed_at": (
            row[8].isoformat() if len(row) >= 9 else proof.get("acquired_at") if proof else None
        ),
    }


def admit_provider_mappings(
    connection: Connection[Any],
    data_root: Path,
    provider: str,
    snapshot_id: UUID | None = None,
) -> list[dict[str, Any]]:
    decisions = []
    verifier = RetainedIdentityVerifier(data_root)
    for entity_type in ("competition", "team"):
        for row in mapping_rows(connection, entity_type, provider, snapshot_id):
            decision = classify_mapping(connection, entity_type, row, data_root, verifier)
            if len(row) > 9 and row[9] is not None:
                if decision["disposition"] not in {"CROSSWALK", "REVOKED"}:
                    from football.product.identity_correction import revoke_team_correction

                    revoke_team_correction(
                        connection, UUID(row[9]["decision_id"]), "CORRECTION_EVIDENCE_UNVERIFIED"
                    )
            else:
                _record_decision(connection, decision)
            decisions.append(decision)
    return decisions


def _manual_review(
    connection: Connection[Any],
    entity_type: str,
    row: tuple[Any, ...],
) -> dict[str, str] | None:
    _, canonical_id, provider, identifier, _, _, _, snapshot_id = row[:8]
    context = (
        "f.competition_id = %s AND o.provider_competition_id = %s"
        if entity_type == "competition"
        else "((f.home_team_id = %s AND o.provider_home_team_id = %s) OR "
        "(f.away_team_id = %s AND o.provider_away_team_id = %s))"
    )
    values = (
        (canonical_id, identifier)
        if entity_type == "competition"
        else (canonical_id, identifier) * 2
    )
    review = connection.execute(
        f"""SELECT d.decision_id, d.created_at FROM football.product_provider_mapping_decisions d
            JOIN football.product_fixtures f ON f.fixture_id = d.candidate_fixture_id
            JOIN football.product_provider_fixture_observations o
              ON o.provider_code = d.provider_code AND o.provider_match_id = d.provider_match_id
             AND o.source_snapshot_id = d.source_snapshot_id
            WHERE d.provider_code = %s AND d.source_snapshot_id = %s
              AND d.disposition = 'MANUAL_ACCEPTED'
              AND d.evidence->>'reviewed_fixture_id' = f.fixture_id::text AND {context}
            ORDER BY d.created_at DESC, d.decision_id DESC
            LIMIT 1""",
        (provider, snapshot_id, *values),
    ).fetchone()
    return {"decision_id": str(review[0]), "decided_at": review[1].isoformat()} if review else None


def mapping_rows(
    connection: Connection[Any],
    entity_type: Literal["team", "competition"],
    provider: str | None = None,
    snapshot_id: UUID | None = None,
) -> list[tuple[Any, ...]]:
    table, canonical, identifier, product = TABLES[entity_type]
    corrected = connection.execute(
        "SELECT to_regprocedure('football.product_team_identity_at(uuid,timestamptz)') IS NOT NULL"
    ).fetchone()
    correction = (
        """, (SELECT to_jsonb(a) FROM (SELECT * FROM football.product_identity_admissions
             WHERE entity_type='team' AND mapping_id=mapping.id
             ORDER BY decided_at DESC,decision_id DESC LIMIT 1) a
             WHERE a.corrects_decision_id IS NOT NULL)"""
        if entity_type == "team" and corrected and corrected[0]
        else ""
    )
    return connection.execute(
        f"""SELECT mapping.id, mapping.{canonical}, provider.code, mapping.{identifier},
                   mapping.mapping_method, mapping.mapping_confidence, product.country,
                   mapping.source_snapshot_id, snapshot.acquired_at {correction}
            FROM football.{table} mapping
            JOIN football.providers provider ON provider.id = mapping.provider_id
            JOIN football.source_snapshots snapshot ON snapshot.id = mapping.source_snapshot_id
            LEFT JOIN football.{product} product ON product.{canonical} = mapping.{canonical}
            WHERE mapping.valid_to IS NULL AND (%s::text IS NULL OR provider.code = %s)
              AND (%s::uuid IS NULL OR mapping.source_snapshot_id = %s)
            ORDER BY mapping.id""",
        (provider, provider, snapshot_id, snapshot_id),
    ).fetchall()


def _record_decision(connection: Connection[Any], decision: dict[str, Any]) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended('product-identity-admission', 0))"
    )
    semantic = {key: value for key, value in decision.items() if key != "source_observed_at"}
    key = sha256_json(semantic)
    previous = connection.execute(
        """SELECT disposition, evidence_sha256, reason, decided_at
           FROM football.product_identity_admissions
           WHERE entity_type = %s AND mapping_id = %s
           ORDER BY decided_at DESC, decision_id DESC LIMIT 1""",
        (decision["entity_type"], decision["mapping_id"]),
    ).fetchone()
    if previous and previous[:2] == (decision["disposition"], key):
        return
    if (
        previous
        and previous[0] == "REVOKED"
        and previous[2] != "MAPPING_CHANGED_REVALIDATION_REQUIRED"
    ):
        review = decision["evidence"].get("operator_review")
        if not review or datetime.fromisoformat(review["decided_at"]) <= previous[3]:
            decision.update(disposition="REVOKED", reason=previous[2])
            return
    connection.execute(
        """INSERT INTO football.product_identity_admissions
           (entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
            disposition, reason, source_snapshot_id, source_observed_at, evidence, evidence_sha256)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            decision["entity_type"],
            decision["mapping_id"],
            decision["canonical_id"],
            decision["provider"],
            decision["provider_id"],
            decision["disposition"],
            decision["reason"],
            decision["source_snapshot_id"],
            decision["source_observed_at"],
            Jsonb(decision["evidence"]),
            key,
        ),
    )


def verify_source_identifier(
    connection: Connection[Any],
    root: Path,
    snapshot_id: UUID,
    provider: str,
    entity_type: str,
    identifier: str,
    country: str | None,
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any] | None:
    if provider not in {
        "api_football",
        "football_data_org",
        "openfootball",
        "football_data_uk",
        "fotmob",
        "pitchapi",
    }:
        return None
    verifier = verifier or RetainedIdentityVerifier(root)
    rows = connection.execute(
        """SELECT snapshot.manifest_path, snapshot.manifest_sha256, snapshot.source_identity,
                  snapshot.source_revision, snapshot.git_sha, resource.id, resource.provider_path,
                  resource.sha256, resource.size_bytes, resource.acquired_at
           FROM football.source_snapshots snapshot
           JOIN football.providers provider ON provider.id = snapshot.provider_id
           JOIN football.source_resources resource ON resource.source_snapshot_id = snapshot.id
           WHERE snapshot.id = %s AND provider.code = %s AND snapshot.status = 'validated'
             AND resource.parse_status = 'parsed'
             AND resource.validation_status IN ('valid','warnings')
           ORDER BY resource.id""",
        (snapshot_id, provider),
    ).fetchall()
    for row in rows:
        try:
            if verifier.contains(provider, entity_type, identifier, country, row):
                return {
                    "provider": provider,
                    "provider_entity_id": identifier,
                    "source_resource_id": str(row[5]),
                    "sha256": row[7],
                    "acquired_at": row[9].isoformat(),
                    "country": country,
                    "manifest_classification": (
                        "BYTE_VERIFIED"
                        if row[3].startswith("manifest-v1:")
                        or (
                            provider not in {"openfootball", "football_data_uk"}
                            and row[1] == row[7]
                        )
                        else "LEGACY_MANIFEST_UNVERIFIED"
                    ),
                }
        except (OSError, ValueError, KeyError, TypeError, ValidationError):
            # Missing, malformed or tampered retained evidence is unverified, never repaired here.
            continue
    return None


def _retained_payload(root: Path, provider: str, row: tuple[Any, ...]) -> bytes | None:
    files = ImmutableFileStore(root)
    if row[3].startswith("manifest-v1:"):
        revision = row[3].removeprefix("manifest-v1:").rsplit(":", 1)[0]
        manifest, digest = verify_manifest(root, row[0], provider, row[2], revision)
        if digest != row[1]:
            return None
        entries = [entry for entry in manifest["resources"] if entry["provider_path"] == row[6]]
        if len(entries) != 1:
            return None
        path = files.path_for(entries[0]["raw_path"])
    else:
        # Legacy manifest registration remains classified separately; verify the raw resource bytes.
        relative = f"openfootball/{row[4]}/{row[6]}" if provider == "openfootball" else row[0]
        path = files.path_for(relative)
    if path.is_symlink():
        return None
    payload = path.read_bytes()
    return (
        payload
        if len(payload) == row[8] and hashlib.sha256(payload).hexdigest() == row[7]
        else None
    )


def _identity_index(
    provider: str, payload: bytes, path: str, identity: str
) -> dict[tuple[str, str | None], set[str]]:
    if provider == "football_data_uk":
        from football.product.football_data_uk import csv_members, parse_csv_resource

        sources = csv_members(payload) if path.casefold().endswith(".zip") else [(path, payload)]
        index: dict[tuple[str, str | None], set[str]] = {}
        for name, raw in sources:
            for match in parse_csv_resource(raw, source_path=name, season=None):
                index.setdefault(("competition", match.country), set()).add(
                    match.provider_competition_id
                )
                index.setdefault(("team", match.country), set()).update(
                    (match.home_team_id, match.away_team_id)
                )
        return index
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("retained provider identity response must be an object")
    if provider == "openfootball":
        from football.product.openfootball import _COUNTRIES

        source_country = _COUNTRIES.get(Path(path).stem.split(".", 1)[0], "World")
        teams = {
            str(name.get("name") or name.get("title")) if isinstance(name, dict) else str(name)
            for match in value.get("matches", [])
            for name in (match.get("team1"), match.get("team2"))
            if name
        }
        return {
            ("competition", source_country): {Path(path).stem} if teams else set(),
            ("team", source_country): teams,
        }
    return {
        (kind, None): _json_identifiers(provider, kind, value, identity)
        for kind in ("competition", "team")
    }


def _json_identifiers(provider: str, entity_type: str, value: Any, identity: str) -> set[str]:
    if provider not in {"api_football", "football_data_org", "pitchapi", "fotmob"}:
        return set()
    keys = (
        {"league", "competition"}
        if entity_type == "competition"
        else {"team", "homeTeam", "awayTeam", "home_team", "away_team", "home", "away"}
    )
    identifiers: set[str] = set()
    for key, item in _objects(value):
        if key in keys and isinstance(item, dict):
            identifiers.update(_native_object_identifiers(provider, entity_type, item))
        if entity_type == "team" and key == "teams" and isinstance(item, dict):
            identifiers.update(
                str(team["id"]) for team in item.values() if isinstance(team, dict) and "id" in team
            )
        if entity_type == "competition" and key == "leagues" and isinstance(item, list):
            identifiers.update(
                str(league["id"]) for league in item if isinstance(league, dict) and "id" in league
            )
    if entity_type == "competition" and identity.startswith("leagues"):
        identifiers.update(
            str(item["id"])
            for item in value.get("response", [])
            if isinstance(item, dict) and "id" in item
        )
    return identifiers


def _native_object_identifiers(provider: str, entity_type: str, item: dict[str, Any]) -> set[str]:
    values = {str(item["id"])} if isinstance(item.get("id"), (int, str)) else set()
    if (
        provider == "football_data_org"
        and entity_type == "competition"
        and isinstance(item.get("code"), str)
    ):
        values.add(item["code"])
    return values


def _objects(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from _objects(item)
