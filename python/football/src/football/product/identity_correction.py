"""Independent, evidence-backed team corrections in the R2 admission log."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from jsonschema import ValidationError
from psycopg import Connection
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.product.identity_admission import (
    _objects,
    _retained_payload,
    classify_mapping,
    verify_source_identifier,
)
from football.product.identity_trust import (
    MappingEvidence,
    explicit_target,
    origin_id,
    qualify_mapping,
)


@dataclass(frozen=True, slots=True)
class TeamIdentityCorrection:
    source_mapping_id: UUID
    target_mapping_id: UUID
    original_decision_id: UUID
    fixture_registration_id: UUID
    orientation: Literal["HOME", "AWAY"]


def _mapping(connection: Connection[Any], key: UUID) -> dict[str, Any]:
    row = connection.execute(
        """SELECT to_jsonb(m) || jsonb_build_object('provider',p.code,'country',t.country)
           FROM football.team_provider_mappings m JOIN football.providers p ON p.id=m.provider_id
           JOIN football.product_teams t ON t.team_id=m.team_id WHERE m.id=%s""",
        (key,),
    ).fetchone()
    if row is None:
        raise ValueError("retained team mapping is missing")
    return cast(dict[str, Any], row[0])


def _target_not_revoked(connection: Connection[Any], key: UUID) -> bool:
    exists = connection.execute(
        "SELECT to_regclass('football.product_identity_admissions') IS NOT NULL"
    ).fetchone()
    if not exists or not exists[0]:
        return True  # Read-only qualification before deployment; no live admission is implied.
    row = connection.execute(
        """SELECT disposition FROM football.product_identity_admissions
           WHERE entity_type='team' AND mapping_id=%s
           ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
        (key,),
    ).fetchone()
    return row is None or row[0] in {"ORIGIN_ANCHOR", "CROSSWALK"}


def _registered_payloads(
    connection: Connection[Any],
    root: Path,
    snapshot: str,
    provider: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = connection.execute(
        """SELECT s.manifest_path,s.manifest_sha256,s.source_identity,s.source_revision,s.git_sha,
                  r.id,r.provider_path,r.sha256,r.size_bytes,r.acquired_at
           FROM football.source_snapshots s JOIN football.providers p ON p.id=s.provider_id
           JOIN football.source_resources r ON r.source_snapshot_id=s.id
           WHERE s.id=%s AND p.code=%s AND s.status='validated' AND r.parse_status='parsed'
             AND r.validation_status IN ('valid','warnings') ORDER BY r.id""",
        (snapshot, provider),
    ).fetchall()
    results = []
    for row in rows:
        payload = _retained_payload(root, provider, row)
        if payload is None or row[9] > datetime.now(UTC):
            raise ValueError("retained context bytes or acquisition time are unverified")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("retained context must be a provider object")
        results.append(
            (
                value,
                {
                    "source_resource_id": str(row[5]),
                    "sha256": row[7],
                    "source_snapshot_id": snapshot,
                    "provider": provider,
                    "acquired_at": row[9].isoformat(),
                },
            )
        )
    if not results:
        raise ValueError("retained context resources are missing")
    return results


def _fixture(
    resources: list[tuple[dict[str, Any], dict[str, Any]]],
    provider: str,
    identifier: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    choices = []
    for payload, proof in resources:
        for row in _records(payload):
            if str(row.get("id")) != identifier:
                continue
            if provider == "football_data_org" and "homeTeam" in row:
                context = {
                    "home": str(row["homeTeam"]["id"]),
                    "away": str(row["awayTeam"]["id"]),
                    "kickoff": datetime.fromisoformat(row["utcDate"]),
                    "country": row["area"]["name"],
                    "league": str(row["competition"]["code"]),
                    "season_start": row["season"]["startDate"],
                    "season_end": row["season"]["endDate"],
                }
            elif provider == "fotmob" and "home" in row and "status" in row:
                details = payload.get("details", {})
                if not isinstance(details, dict):
                    raise ValueError("supporting league metadata is malformed")
                context = {
                    "home": str(row["home"]["id"]),
                    "away": str(row["away"]["id"]),
                    "kickoff": datetime.fromisoformat(row["status"]["utcTime"]),
                    "country": details.get("country"),
                    "league": str(details.get("id")),
                    "season": details.get("selectedSeason", payload.get("selectedSeason")),
                }
            else:
                continue
            choices.append((context, proof, row))
    contexts = {
        sha256_json({**item[0], "kickoff": item[0]["kickoff"].isoformat()}) for item in choices
    }
    if not choices or len(contexts) != 1:
        raise ValueError("retained fixture context is missing or contradictory")
    return choices[0]


def _records(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield payload
    for _, value in _objects(payload):
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, dict):
                yield item


def _source_context(
    connection: Connection[Any],
    root: Path,
    request: TeamIdentityCorrection,
    source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    row = connection.execute(
        """SELECT to_jsonb(d),to_jsonb(m),to_jsonb(f),to_jsonb(s)
           FROM football.product_provider_mapping_decisions d
           JOIN football.match_provider_mappings m ON m.id=%s AND m.match_id=d.candidate_fixture_id
           JOIN football.product_fixtures f ON f.fixture_id=m.match_id
           JOIN football.matches match ON match.id=f.fixture_id
           JOIN football.seasons s ON s.id=match.season_id WHERE d.decision_id=%s""",
        (request.fixture_registration_id, request.original_decision_id),
    ).fetchone()
    if (
        row is None
        or row[0]["disposition"] != "CONTRADICTORY"
        or row[0]["provider_code"] != "fotmob"
        or row[0]["reason"] != "verified team_provider_mappings contradicts exact-name candidate"
    ):
        raise ValueError("exact retained contradiction and fixture registration are required")
    original, registration, fixture, season = row
    if registration["provider_id"] != source["provider_id"] or registration["valid_to"] is not None:
        raise ValueError("fixture registration does not belong to the source provider")
    if connection.execute(
        """SELECT 1 FROM football.product_provider_mapping_decisions
           WHERE candidate_fixture_id=%s AND disposition='CONTRADICTORY'
             AND decision_id<>%s LIMIT 1""",
        (fixture["fixture_id"], request.original_decision_id),
    ).fetchone():
        raise ValueError("additional retained contradiction requires separate review")
    context, proof, _ = _fixture(
        _registered_payloads(
            connection, root, registration["source_snapshot_id"], source["provider"]
        ),
        source["provider"],
        registration["provider_match_id"],
    )
    field = {"HOME": "home", "AWAY": "away"}.get(request.orientation)
    if (
        field is None
        or context[field] != source["provider_team_id"]
        or fixture[field + "_team_id"] != source["team_id"]
    ):
        raise ValueError("source team orientation contradicts the retained fixture")
    if (
        context["kickoff"] != datetime.fromisoformat(fixture["kickoff_at"])
        or context["season_start"] != season["start_date"]
        or context["season_end"] != season["end_date"]
    ):
        raise ValueError("source season or kickoff contradicts its registration")
    return original, context, proof, fixture


def _support_context(
    connection: Connection[Any],
    root: Path,
    original: dict[str, Any],
    context: dict[str, Any],
    request: TeamIdentityCorrection,
    target: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    support, proof, _ = _fixture(
        _registered_payloads(connection, root, original["source_snapshot_id"], "fotmob"),
        "fotmob",
        original["provider_match_id"],
    )
    season = context["season_start"][:4] + "/" + context["season_end"][:4]
    competition = explicit_target("competition", "fotmob", support["league"])
    if (
        support["country"] != "ENG"
        or context["country"] != "England"
        or support["season"] != season
        or support["kickoff"] != context["kickoff"]
        or competition != explicit_target("competition", "football_data_org", context["league"])
    ):
        raise ValueError("supporting competition, season, country or kickoff conflicts")
    native = support["home" if request.orientation == "HOME" else "away"]
    if explicit_target("team", "fotmob", native) != (
        target["provider"],
        target["provider_team_id"],
    ):
        raise ValueError("supporting home/away provider ID conflicts with the target")
    mapping = connection.execute(
        """SELECT m.id,m.team_id,p.code,m.provider_team_id,m.mapping_method,
                  m.mapping_confidence,t.country,m.source_snapshot_id,s.acquired_at
           FROM football.team_provider_mappings m
           JOIN football.providers p ON p.id=m.provider_id
           JOIN football.product_teams t ON t.team_id=m.team_id
           JOIN football.source_snapshots s ON s.id=m.source_snapshot_id
           WHERE p.code='fotmob' AND m.provider_team_id=%s AND m.valid_to IS NULL""",
        (native,),
    ).fetchall()
    if len(mapping) != 1:
        raise ValueError("supporting active crosswalk conflicts with the target UUID")
    qualified = classify_mapping(connection, "team", mapping[0], root)
    if qualified["disposition"] != "CROSSWALK" or qualified["canonical_id"] != target["team_id"]:
        raise ValueError("supporting mapping fails the shared R2 trust predicate")
    mapping_proof = {
        **qualified["evidence"],
        "source_snapshot_id": qualified["source_snapshot_id"],
        "mapping_id": qualified["mapping_id"],
    }
    return proof, mapping_proof


def _target_context(
    connection: Connection[Any],
    root: Path,
    target: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    league = explicit_target("competition", "football_data_org", context["league"])
    for payload, proof in _registered_payloads(
        connection, root, target["source_snapshot_id"], target["provider"]
    ):
        for row in _records(payload):
            if "teams" not in row or "league" not in row:
                continue
            teams, competition = row["teams"], row["league"]
            if not isinstance(teams, dict) or not isinstance(competition, dict):
                continue
            identifiers = {str(team.get("id")) for team in teams.values() if isinstance(team, dict)}
            if (
                target["provider_team_id"] in identifiers
                and league == (target["provider"], str(competition.get("id")))
                and competition.get("country") == context["country"]
                and str(competition.get("season")) == context["season_start"][:4]
            ):
                return proof
    raise ValueError("target team has no retained compatible league/season evidence")


def _qualify(
    connection: Connection[Any], root: Path, request: TeamIdentityCorrection
) -> dict[str, Any]:
    source, target = (
        _mapping(connection, request.source_mapping_id),
        _mapping(connection, request.target_mapping_id),
    )
    if source["provider"] != "football_data_org" or target["provider"] != "api_football":
        raise ValueError("this correction requires retained FDO and API-Football mappings")
    if not _target_not_revoked(connection, request.target_mapping_id):
        raise ValueError("target identity admission is revoked or unresolved")
    if source["valid_to"] is not None or target["valid_to"] is not None:
        raise ValueError("a mapping is no longer current")
    if source["mapping_method"] != "explicit_crosswalk":
        raise ValueError("source row is not an incorrect explicit crosswalk projection")
    if explicit_target("team", source["provider"], source["provider_team_id"]) != (
        target["provider"],
        target["provider_team_id"],
    ):
        raise ValueError("target provider ID is not the approved explicit crosswalk")
    if source["team_id"] != str(
        origin_id("team", source["provider"], source["provider_team_id"], None)
    ):
        raise ValueError("source mapping is not the retained incorrect origin projection")
    original, context, fixture_proof, fixture = _source_context(connection, root, request, source)
    target_proof = _target_context(connection, root, target, context)
    support_proof, support_mapping_proof = _support_context(
        connection, root, original, context, request, target
    )
    source_proof = verify_source_identifier(
        connection,
        root,
        UUID(source["source_snapshot_id"]),
        source["provider"],
        "team",
        source["provider_team_id"],
        context["country"],
    )
    origin_proof = verify_source_identifier(
        connection,
        root,
        UUID(target["source_snapshot_id"]),
        target["provider"],
        "team",
        target["provider_team_id"],
        target["country"],
    )
    target_disposition, _ = qualify_mapping(
        MappingEvidence(
            "team",
            UUID(target["team_id"]),
            target["provider"],
            target["provider_team_id"],
            target["mapping_method"],
            target["mapping_confidence"],
            target["country"],
            bool(origin_proof),
            bool(origin_proof),
        )
    )
    competition_target = explicit_target("competition", source["provider"], context["league"])
    assert competition_target is not None
    competition_id = origin_id("competition", *competition_target, context["country"])
    disposition, reason = qualify_mapping(
        MappingEvidence(
            "team",
            UUID(target["team_id"]),
            source["provider"],
            source["provider_team_id"],
            "explicit_crosswalk",
            source["mapping_confidence"],
            context["country"],
            bool(source_proof),
            bool(source_proof),
            origin_id("team", target["provider"], target["provider_team_id"], target["country"]),
            target_disposition == "ORIGIN_ANCHOR"
            and fixture["competition_id"] == str(competition_id),
        )
    )
    if disposition != "CROSSWALK" or source_proof is None:
        raise ValueError(reason)
    assert origin_proof is not None
    source_proof.update(
        contract="ProductTeamIdentityCorrectionV1",
        reason="INCORRECT_PRIOR_MAPPING",
        original_decision=original,
        fixture_registration_id=str(request.fixture_registration_id),
        orientation=request.orientation,
        target_evidence={**origin_proof, "source_snapshot_id": target["source_snapshot_id"]},
        context_resources=[fixture_proof, target_proof, support_proof, support_mapping_proof],
        context={**context, "kickoff": context["kickoff"].isoformat()},
        policy_version="ProductIdentityTrustV1",
    )
    return {
        "status": "QUALIFIED",
        "entity_type": "team",
        "mapping_id": str(request.source_mapping_id),
        "canonical_id": target["team_id"],
        "provider": source["provider"],
        "provider_id": source["provider_team_id"],
        "source_snapshot_id": source["source_snapshot_id"],
        "source_observed_at": source_proof["acquired_at"],
        "disposition": disposition,
        "reason": "INCORRECT_PRIOR_MAPPING_CORRECTED",
        "evidence": source_proof,
        "corrects_decision_id": str(request.original_decision_id),
        "target_mapping_id": str(request.target_mapping_id),
    }


def qualify_team_correction(
    connection: Connection[Any], root: Path, request: TeamIdentityCorrection
) -> dict[str, Any]:
    """Read-only qualification; never fabricate an operational observation or decision time."""
    try:
        return _qualify(connection, root, request)
    except (ValueError, OSError, KeyError, TypeError, ValidationError, RecursionError) as error:
        return {
            "status": "UNRESOLVED",
            "reason": str(error),
            "source_mapping_id": str(request.source_mapping_id),
        }


def correct_team_identity(
    connection: Connection[Any],
    root: Path,
    request: TeamIdentityCorrection,
    *,
    reviewed_revalidation: bool = False,
) -> dict[str, Any]:
    """Append one qualified correction atomically; callers control outer transaction commit."""
    ready = connection.execute(
        "SELECT to_regprocedure('football.product_team_identity_at(uuid,timestamptz)') IS NOT NULL"
    ).fetchone()
    if not ready or not ready[0]:
        raise ValueError("team identity correction requires migration 202610140100")
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('product-identity-admission',0))"
        )
        previous = connection.execute(
            """SELECT to_jsonb(a) FROM football.product_identity_admissions a
               WHERE mapping_id=%s AND entity_type='team'
               ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
            (request.source_mapping_id,),
        ).fetchone()
        if previous and previous[0]["corrects_decision_id"] is not None:
            decision = previous[0]
            if (
                decision["corrects_decision_id"],
                decision["target_mapping_id"],
                decision["evidence"]["fixture_registration_id"],
                decision["evidence"]["orientation"],
            ) != (
                str(request.original_decision_id),
                str(request.target_mapping_id),
                str(request.fixture_registration_id),
                request.orientation,
            ):
                raise ValueError("existing correction conflicts with the requested operation")
            if decision["disposition"] == "CROSSWALK":
                result = qualify_team_correction(connection, root, request)
                if result["status"] != "QUALIFIED":
                    raise ValueError(result["reason"])
            if reviewed_revalidation and decision["disposition"] == "REVOKED":
                if decision["reason"] != "MAPPING_CHANGED_REVALIDATION_REQUIRED":
                    raise ValueError(
                        "only a mapping-change revocation permits reviewed revalidation"
                    )
            else:
                return {**decision, "decided_at": datetime.fromisoformat(decision["decided_at"])}
        elif previous and previous[0]["disposition"] == "REVOKED":
            raise ValueError("a revoked source mapping requires a new reviewed promotion")
        result = qualify_team_correction(connection, root, request)
        if result["status"] != "QUALIFIED":
            raise ValueError(result["reason"])
        semantic = {
            key: value
            for key, value in result.items()
            if key not in {"status", "source_observed_at"}
        }
        decision = connection.execute(
            """INSERT INTO football.product_identity_admissions
               (entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,disposition,reason,
                source_snapshot_id,source_observed_at,evidence,evidence_sha256,
                corrects_decision_id,target_mapping_id)
               VALUES ('team',%s,%s,%s,%s,'CROSSWALK',%s,%s,%s,%s,%s,%s,%s)
               RETURNING to_jsonb(product_identity_admissions)""",
            (
                result["mapping_id"],
                result["canonical_id"],
                result["provider"],
                result["provider_id"],
                result["reason"],
                result["source_snapshot_id"],
                result["source_observed_at"],
                Jsonb(result["evidence"]),
                sha256_json(semantic),
                request.original_decision_id,
                request.target_mapping_id,
            ),
        ).fetchone()
        assert decision is not None
        return {**decision[0], "decided_at": datetime.fromisoformat(decision[0]["decided_at"])}


def revalidate_team_correction(
    connection: Connection[Any], root: Path, decision: dict[str, Any]
) -> dict[str, Any]:
    """Audit and automated ingestion share qualification without replacing linked decisions."""
    result = {
        "entity_type": "team",
        "mapping_id": decision["mapping_id"],
        "canonical_id": decision["canonical_id"],
        "provider": decision["provider_code"],
        "provider_id": decision["provider_entity_id"],
        "disposition": decision["disposition"],
        "reason": decision["reason"],
        "source_snapshot_id": decision["source_snapshot_id"],
        "source_observed_at": decision["source_observed_at"],
        "evidence": decision["evidence"],
        "corrects_decision_id": decision["corrects_decision_id"],
        "decision_id": decision["decision_id"],
    }
    if decision["disposition"] == "REVOKED":
        return result
    request = TeamIdentityCorrection(
        UUID(decision["mapping_id"]),
        UUID(decision["target_mapping_id"]),
        UUID(decision["corrects_decision_id"]),
        UUID(decision["evidence"]["fixture_registration_id"]),
        decision["evidence"]["orientation"],
    )
    qualified = qualify_team_correction(connection, root, request)
    if qualified["status"] != "QUALIFIED":
        result.update(disposition="UNRESOLVED", reason=qualified["reason"])
    return result


def revoke_team_correction(
    connection: Connection[Any], decision_id: UUID, reason: str
) -> dict[str, Any]:
    """Revoke the effective corrected identity without removing any earlier event."""
    if not reason.strip():
        raise ValueError("revocation reason is required")
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('product-identity-admission',0))"
        )
        row = connection.execute(
            """SELECT to_jsonb(latest) FROM football.product_identity_admissions original
               CROSS JOIN LATERAL (SELECT * FROM football.product_identity_admissions
                   WHERE mapping_id=original.mapping_id AND entity_type='team'
                   ORDER BY decided_at DESC,decision_id DESC LIMIT 1) latest
               WHERE original.decision_id=%s AND original.corrects_decision_id IS NOT NULL""",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise ValueError("linked team correction is missing")
        if row[0]["disposition"] == "REVOKED":
            return cast(dict[str, Any], row[0])
        result = connection.execute(
            """INSERT INTO football.product_identity_admissions
               (entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,disposition,reason,
                source_snapshot_id,source_observed_at,evidence,evidence_sha256,
                corrects_decision_id,target_mapping_id)
               SELECT entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
                      'REVOKED',%s,
                      source_snapshot_id,source_observed_at,evidence,evidence_sha256,
                      corrects_decision_id,target_mapping_id
               FROM football.product_identity_admissions WHERE decision_id=%s
               RETURNING to_jsonb(product_identity_admissions)""",
            (reason, row[0]["decision_id"]),
        ).fetchone()
        assert result is not None
        return cast(dict[str, Any], result[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--data-root", type=Path, default=Path(".local/football-data"))
    for name in (
        "source-mapping-id",
        "target-mapping-id",
        "original-decision-id",
        "fixture-registration-id",
    ):
        parser.add_argument("--" + name, type=UUID, required=True)
    parser.add_argument("--orientation", choices=("HOME", "AWAY"), required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append a prospective correction; requires database mutation authorisation.",
    )
    args = parser.parse_args(argv)
    request = TeamIdentityCorrection(
        args.source_mapping_id,
        args.target_mapping_id,
        args.original_decision_id,
        args.fixture_registration_id,
        args.orientation,
    )
    with psycopg.connect(args.database_url) as connection:
        if not args.apply:
            connection.execute("SET TRANSACTION READ ONLY")
        result = (
            correct_team_identity(connection, args.data_root, request)
            if args.apply
            else qualify_team_correction(connection, args.data_root, request)
        )
    print(json.dumps(result, sort_keys=True, default=str))
    return (
        0 if result.get("status") == "QUALIFIED" or result.get("disposition") == "CROSSWALK" else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
