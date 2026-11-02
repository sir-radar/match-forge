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
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks
from football.storage.raw import ImmutableFileStore
from football.storage.transactions import require_idle_connection

TABLES = {
    "competition": (
        "competition_provider_mappings",
        "competition_id",
        "provider_competition_id",
        "product_competitions",
    ),
    "team": ("team_provider_mappings", "team_id", "provider_team_id", "product_teams"),
}


class RetainedEvidenceChanged(RuntimeError):
    """Registered evidence changed after preparation; retry before taking locks."""


class RetainedIdentityVerifier:
    """An operation-scoped index of identities from verified immutable resource bytes."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.knowledge_time = datetime.now(UTC)
        self.indexes: dict[tuple[object, ...], dict[tuple[str, str | None], set[str]]] = {}
        self.source_bytes_verified = 0
        self._payloads: dict[tuple[object, ...], bytes | Exception | None] = {}
        self._sealed = False

    def seal(self) -> None:
        """Permit database rechecks with prepared bytes only, without file I/O."""
        self._sealed = True

    def payload(self, provider: str, row: tuple[Any, ...]) -> bytes | None:
        key = (provider, *row)
        if key not in self._payloads:
            if self._sealed:
                raise RetainedEvidenceChanged(
                    "retained evidence changed; prepare again before locking"
                )
            try:
                self._payloads[key] = _retained_payload(self.root, provider, row)
            except (
                OSError,
                ValueError,
                KeyError,
                TypeError,
                ValidationError,
                RecursionError,
            ) as error:
                self._payloads[key] = error
        prepared = self._payloads[key]
        if isinstance(prepared, Exception):
            raise prepared
        return prepared

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
        key = (provider, *row)
        if key not in self.indexes:
            if self._sealed:
                raise RetainedEvidenceChanged(
                    "retained evidence changed; prepare again before locking"
                )
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

        return revalidate_team_correction(connection, data_root, row[9], verifier=verifier)
    mapping_id, canonical_id, provider, identifier, method, confidence, country, snapshot_id = row[
        :8
    ]
    manual_review = _manual_review(connection, entity_type, row) if method == "manual" else None
    source_competition = (
        manual_review.pop("provider_competition_id", None) if manual_review else None
    )
    source_country = country
    namespace_verified = True
    if provider == "openfootball" and source_competition:
        from football.product.openfootball import _COUNTRIES

        source_country = _COUNTRIES.get(source_competition.split(".", 1)[0], "World")
        namespace_verified = (
            verify_source_identifier(
                connection,
                data_root,
                snapshot_id,
                provider,
                "competition",
                source_competition,
                source_country,
                verifier,
            )
            is not None
        )
    proof = (
        verify_source_identifier(
            connection,
            data_root,
            snapshot_id,
            provider,
            entity_type,
            identifier,
            source_country,
            verifier,
        )
        if namespace_verified
        else None
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
    *,
    entity_types: tuple[Literal["competition", "team"], ...] = ("competition", "team"),
    commit_each: bool = False,
    verifier: RetainedIdentityVerifier | None = None,
) -> list[dict[str, Any]]:
    if commit_each:
        require_idle_connection(connection, "bounded identity admission")
    decisions = []
    verifier = verifier or RetainedIdentityVerifier(data_root)
    candidates = [
        (kind, row)
        for kind in entity_types
        for row in mapping_rows(connection, kind, provider, snapshot_id)
    ]
    if not commit_each:
        for kind, row in candidates:
            classify_mapping(connection, kind, row, data_root, verifier)
        verifier.seal()
    for entity_type, row in candidates:
        decision = classify_mapping(connection, entity_type, row, data_root, verifier)
        if len(row) > 9 and row[9] is not None:
            if decision["disposition"] not in {"CROSSWALK", "REVOKED"}:
                from football.product.identity_correction import revoke_team_correction

                revoke_team_correction(
                    connection, UUID(row[9]["decision_id"]), "CORRECTION_EVIDENCE_UNVERIFIED"
                )
        else:
            _record_decision(connection, decision, row)
        decisions.append(decision)
        if commit_each:
            connection.commit()
    if commit_each:
        connection.commit()
    return decisions


def admit_reviewed_mapping(
    connection: Connection[Any],
    data_root: Path,
    entity_type: Literal["team", "competition"],
    mapping_id: UUID,
    *,
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    """Admit exactly one independently qualified current mapping, prospectively."""
    rows = mapping_rows(connection, entity_type, mapping_id=mapping_id)
    if len(rows) != 1:
        raise ValueError("current mapping not found")
    verifier = verifier or RetainedIdentityVerifier(data_root)
    classify_mapping(connection, entity_type, rows[0], data_root, verifier)
    verifier.seal()
    with connection.transaction():
        acquire_locks(connection, (IDENTITY_ADMISSION_LOCK,))
        rows = mapping_rows(connection, entity_type, mapping_id=mapping_id)
        if len(rows) != 1:
            raise ValueError("current mapping changed; preview again")
        decision = classify_mapping(connection, entity_type, rows[0], data_root, verifier)
        if decision["disposition"] not in {"ORIGIN_ANCHOR", "CROSSWALK"}:
            raise ValueError(decision["reason"])
        previous = connection.execute(
            """SELECT disposition FROM football.product_identity_admissions
               WHERE entity_type=%s AND mapping_id=%s
               ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
            (entity_type, mapping_id),
        ).fetchone()
        if previous and previous[0] == "REVOKED":
            raise ValueError("revoked mapping requires a separately qualified correction")
        if len(rows[0]) > 9 and rows[0][9] is not None:
            raise ValueError(
                "linked correction requires the existing reviewed revalidation workflow"
            )
        _record_decision(connection, decision, rows[0])
    return decision


def fixture_identity_blockers(
    connection: Connection[Any],
    fixture_ids: list[UUID],
    cutoff: datetime,
    *,
    provider_code: str | None = None,
) -> dict[UUID, str | None]:
    """Require qualified provider mappings before using a provider-derived target."""
    rows = connection.execute(
        """WITH admissions AS MATERIALIZED (
            SELECT DISTINCT ON (entity_type,mapping_id) *
            FROM football.product_identity_admissions WHERE decided_at<=%s
            ORDER BY entity_type,mapping_id,decided_at DESC,decision_id DESC
        ), targets AS MATERIALIZED (
            SELECT f.*, football.product_fixture_team_at(f.fixture_id,f.home_team_id,%s) home_id,
                   football.product_fixture_team_at(f.fixture_id,f.away_team_id,%s) away_id
            FROM football.product_fixtures f WHERE f.fixture_id=ANY(%s::uuid[])
        ), candidates AS (
            SELECT t.fixture_id, mm.id source_mapping,
              COALESCE(home.qualified,false) home_ok, COALESCE(away.qualified,false) away_ok,
              COALESCE(competition.qualified,false) competition_ok
            FROM targets t
            LEFT JOIN football.match_provider_mappings mm ON mm.match_id=t.fixture_id
              AND mm.valid_to IS NULL
              AND (%s::text IS NULL OR mm.provider_id=(
                  SELECT id FROM football.providers WHERE code=%s))
            LEFT JOIN LATERAL (
                SELECT bool_and(m.mapping_confidence=1 AND
                    football.product_mapping_trusted('team',m.id,t.home_id) AND
                    COALESCE(a.disposition IN ('ORIGIN_ANCHOR','CROSSWALK')
                             AND a.canonical_id=t.home_id,false)) qualified
                FROM football.team_provider_mappings m
                LEFT JOIN admissions a ON a.entity_type='team' AND a.mapping_id=m.id
                WHERE m.provider_id=mm.provider_id AND m.team_id=t.home_team_id
                  AND m.valid_to IS NULL
            ) home ON true
            LEFT JOIN LATERAL (
                SELECT bool_and(m.mapping_confidence=1 AND
                    football.product_mapping_trusted('team',m.id,t.away_id) AND
                    COALESCE(a.disposition IN ('ORIGIN_ANCHOR','CROSSWALK')
                             AND a.canonical_id=t.away_id,false)) qualified
                FROM football.team_provider_mappings m
                LEFT JOIN admissions a ON a.entity_type='team' AND a.mapping_id=m.id
                WHERE m.provider_id=mm.provider_id AND m.team_id=t.away_team_id
                  AND m.valid_to IS NULL
            ) away ON true
            LEFT JOIN LATERAL (
                SELECT bool_and(m.mapping_confidence=1 AND
                    football.product_mapping_trusted('competition',m.id,t.competition_id) AND
                    COALESCE(a.disposition IN ('ORIGIN_ANCHOR','CROSSWALK')
                             AND a.canonical_id=t.competition_id,false)) qualified
                FROM football.competition_provider_mappings m
                LEFT JOIN admissions a ON a.entity_type='competition' AND a.mapping_id=m.id
                WHERE m.provider_id=mm.provider_id AND m.competition_id=t.competition_id
                  AND m.valid_to IS NULL
            ) competition ON true
        ), best AS (
            SELECT fixture_id,max(CASE
                WHEN source_mapping IS NULL THEN CASE WHEN %s::text IS NULL THEN 3 ELSE 0 END
                WHEN NOT home_ok THEN 0 WHEN NOT away_ok THEN 1
                WHEN NOT competition_ok THEN 2 ELSE 3 END) progress
            FROM candidates GROUP BY fixture_id
        ) SELECT fixture_id,CASE progress
            WHEN 0 THEN 'HOME_IDENTITY_NOT_ADMITTED'
            WHEN 1 THEN 'AWAY_IDENTITY_NOT_ADMITTED'
            WHEN 2 THEN 'COMPETITION_IDENTITY_NOT_ADMITTED' ELSE NULL END
          FROM best""",
        (cutoff, cutoff, cutoff, fixture_ids, provider_code, provider_code, provider_code),
    ).fetchall()
    return dict(rows)


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
        f"""SELECT d.decision_id, d.created_at, o.provider_competition_id
            FROM football.product_provider_mapping_decisions d
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
    if review is None:
        return None
    result = {"decision_id": str(review[0]), "decided_at": review[1].isoformat()}
    if review[2] is not None:
        result["provider_competition_id"] = review[2]
    return result


def mapping_rows(
    connection: Connection[Any],
    entity_type: Literal["team", "competition"],
    provider: str | None = None,
    snapshot_id: UUID | None = None,
    *,
    mapping_id: UUID | None = None,
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
              AND (%s::uuid IS NULL OR mapping.id = %s)
            ORDER BY mapping.id""",
        (provider, provider, snapshot_id, snapshot_id, mapping_id, mapping_id),
    ).fetchall()


def _record_decision(
    connection: Connection[Any], decision: dict[str, Any], expected_mapping: tuple[Any, ...]
) -> None:
    acquire_locks(connection, (IDENTITY_ADMISSION_LOCK,))
    current = mapping_rows(
        connection,
        decision["entity_type"],
        decision["provider"],
        mapping_id=UUID(decision["mapping_id"]),
    )
    if current != [expected_mapping]:
        raise RetainedEvidenceChanged("mapping changed; prepare again before locking")
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
        "statsbomb_open_data",
        "espn",
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
                        if provider == "statsbomb_open_data"
                        or row[3].startswith("manifest-v1:")
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
    if provider == "statsbomb_open_data":
        from football.ingestion.registration import read_registered_statsbomb_resource

        return read_registered_statsbomb_resource(root, row[:9])
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
    if provider == "espn":
        from football.product.retained_identities import espn_summary_identifiers

        return espn_summary_identifiers(payload, path)
    if provider == "statsbomb_open_data":
        from football.product.retained_identities import statsbomb_identifiers

        return statsbomb_identifiers(payload, path)
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
        if (
            provider == "fotmob"
            and entity_type == "competition"
            and key == "details"
            and identity.startswith("league-")
            and isinstance(item, dict)
        ):
            identifiers.update(_native_object_identifiers(provider, entity_type, item))
        if entity_type == "team" and key == "teams" and isinstance(item, dict):
            identifiers.update(
                str(team["id"]) for team in item.values() if isinstance(team, dict) and "id" in team
            )
        if entity_type == "competition" and key == "leagues" and isinstance(item, list):
            identifiers.update(
                identifier
                for league in item
                if isinstance(league, dict)
                for identifier in _native_object_identifiers(provider, entity_type, league)
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
        provider == "fotmob"
        and entity_type == "competition"
        and isinstance(item.get("primaryId"), (int, str))
    ):
        values.add(str(item["primaryId"]))
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
