"""Read-only qualification of an exact retained StatsBomb match-index population."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from football.contracts.source import canonical_json_bytes
from football.identity.repository import IdentityRepository
from football.ingestion.statsbomb_contracts import LineupPlayer, _parse_events, _parse_lineup
from football.product.identity_admission import (
    RetainedIdentityVerifier,
    classify_mapping,
    mapping_rows,
)
from football.product.resolution_actions import preview
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.common import NormalizationContext, timestamp
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


def native_resources(
    connection: Connection[Any], root: Path, matches: list[dict[str, Any]], kind: str
) -> Iterator[tuple[str, NormalizationContext, bytes]]:
    paths = {f"data/{kind}/{match['match_id']}.json": str(match["match_id"]) for match in matches}
    rows = connection.execute(
        """SELECT r.provider_path,r.id FROM football.source_resources r
        JOIN football.source_snapshots s ON s.id=r.source_snapshot_id
        JOIN football.providers p ON p.id=s.provider_id
        WHERE p.code='statsbomb_open_data' AND r.provider_path=ANY(%s)
        ORDER BY r.provider_path,r.id""",
        (list(paths),),
    ).fetchall()
    if len(rows) != len(paths) or len({row[0] for row in rows}) != len(paths):
        raise ValueError(
            "pilot requires one exact retained resource per fixture; revisions need review"
        )
    for path, key in rows:
        context, raw = registered_resource(connection, root, key)
        yield paths[path], context, raw


def match_clocks(match: dict[str, Any], context: NormalizationContext) -> dict[str, Any]:
    raw = match.get("last_updated")
    try:
        updated = timestamp(raw).isoformat() if raw is not None else None
    except ValueError:
        updated = None
    return {
        "native_fixture_id": str(match["match_id"]),
        "native_match_date": match["match_date"],
        "native_local_kickoff": match.get("kick_off"),
        "football_event_time": None,
        "verified_utc_kickoff": None,
        "provider_update_raw": raw,
        "provider_observation_time": None,
        "provider_updated_at": updated,
        "source_publication_time": None,
        "matchforge_acquisition_time": context.time.acquired_at.isoformat(),
        "canonical_admission_time": None,
        "forecast_knowledge_cutoff": None,
        "own_target_feature_use_allowed": False,
        "kickoff_time_status": "MISSING_PROOF",
    }


def time_report(
    connection: Connection[Any], root: Path, matches: list[dict[str, Any]], resource: UUID
) -> dict[str, Any]:
    context, _ = registered_resource(connection, root, resource)
    clocks = [match_clocks(match, context) for match in matches]
    counts: Counter[str] = Counter()
    periods: Counter[str] = Counter()
    resources = []
    for native, source, raw in native_resources(connection, root, matches, "events"):
        parsed = _parse_events(raw, source.resource_key, native)
        counts.update(event.provider_event_type for event in parsed.events)
        periods.update(str(event.period) for event in parsed.events)
        resources.append(
            {
                "native_fixture_id": native,
                "source_resource_id": str(source.provenance.source_resource_id),
                "source_sha256": source.provenance.source_sha256,
                "events": len(parsed.events),
                "relative_event_clocks": "VERIFIED_NATIVE_ONLY",
                "absolute_event_time": None,
            }
        )
    duplicates = connection.execute(
        """SELECT r.sha256,array_agg(DISTINCT p.code),count(*) FROM football.source_resources r
        JOIN football.source_snapshots s ON s.id=r.source_snapshot_id
        JOIN football.providers p ON p.id=s.provider_id
        WHERE p.code IN ('flashscore','soccerway') GROUP BY r.sha256
        HAVING count(DISTINCT p.code)>1 ORDER BY r.sha256"""
    ).fetchall()
    return {
        "phase": "R02-C",
        "status": "BLOCKED_WITH_EVIDENCE",
        "fixtures": len(matches),
        "clocks": clocks,
        "event_resources": resources,
        "native_event_types": dict(sorted(counts.items())),
        "native_periods": dict(sorted(periods.items())),
        "native_result_pairs": sum(
            row.get("home_score") is not None and row.get("away_score") is not None
            for row in matches
        ),
        "qualified_canonical_outcomes": 0,
        "qualified_market_labels": 0,
        "shared_upstream_groups": [
            {
                "sha256": digest,
                "providers": providers,
                "resource_occurrences": total,
                "independent_confirmations": 1,
            }
            for digest, providers, total in duplicates
        ],
        "target_semantics": {
            "FT_score": "Native pairs retained; regulation/extra-time basis not qualified",
            "HT_score": "No verified period score selected; no event-derived score invented",
            "shots": "Native Shot events counted; target definition and completeness unqualified",
            "SOT": "No settlement equivalence; Saved Off Target must not establish SOT",
            "cards": "Native events only; second-yellow/red and settlement rules unqualified",
            "corners": "No complete target/period/settlement binding established",
            "player_appearances": "Lineup/participation audit is independent of minute exposure",
        },
        "blockers": [
            "380 local kickoff clocks have no independently verified timezone; date-only or "
            "local clocks never become exact UTC timestamps.",
            "Relative period clocks are source evidence, not absolute event/publication times.",
            "Identity, native-to-market meanings, completeness, corrections and settlement "
            "remain unqualified. No missing measurement is treated as zero.",
            "Later acquisition does not become pre-match knowledge. Historical labels require "
            "a separately approved chronological use; own-target feature use stays prohibited.",
        ],
    }


def appearance_status(player: LineupPlayer) -> str:
    if player.was_starter:
        return "STARTED"
    reasons = {position.start_reason for position in player.positions}
    if reasons & {"Substitution - On (Tactical)", "Substitution - On (Injury)"}:
        return "SUBSTITUTE_APPEARANCE"
    return "UNKNOWN"


def lineup_records(
    native: str, context: NormalizationContext, raw: bytes, match: dict[str, Any]
) -> list[dict[str, Any]]:
    lineup = _parse_lineup(raw, context.resource_key, native)
    expected = {str(match[side][side + "_id"]) for side in ("home_team", "away_team")}
    players = [player.provider_id for team in lineup.teams for player in team.players]
    consistent = {team.provider_id for team in lineup.teams} == expected and len(players) == len(
        set(players)
    )
    return [
        {
            "native_fixture_id": native,
            "native_team_id": team.provider_id,
            "native_player_id": player.provider_id,
            "source_name": player.full_name,
            "native_fixture_date": match["match_date"],
            "source_resource_id": str(context.provenance.source_resource_id),
            "source_sha256": context.provenance.source_sha256,
            "source_relationship_status": "VERIFIED" if consistent else "CONTRADICTORY",
            "native_appearance": appearance_status(player),
            "position_stints": len(player.positions),
            "closed_position_stints": sum(p.clock_to is not None for p in player.positions),
            "verified_minutes": None,
            "continuous_membership_interval": None,
            "pre_match_lineup_known": False,
        }
        for team in lineup.teams
        for player in team.players
    ]


def player_report(
    connection: Connection[Any], root: Path, matches: list[dict[str, Any]], cutoff: datetime
) -> dict[str, Any]:
    by_fixture = {str(match["match_id"]): match for match in matches}
    records = [
        record
        for native, source, raw in native_resources(connection, root, matches, "lineups")
        for record in lineup_records(native, source, raw, by_fixture[native])
    ]
    associations: dict[str, set[str]] = defaultdict(set)
    names: dict[str, set[str]] = defaultdict(set)
    for record in records:
        associations[record["native_player_id"]].add(record["native_team_id"])
        names[record["source_name"]].add(record["native_player_id"])
    claims = connection.execute(
        """WITH states AS (
          SELECT DISTINCT ON(mapping_id) * FROM football.provider_mapping_history
          WHERE subject_type='player' AND known_at<=%s
          ORDER BY mapping_id,known_at DESC,history_id DESC)
        SELECT h.provider_entity_id,h.canonical_id,h.mapping_method,h.known_at,h.mapping_id
        FROM states h JOIN football.providers p ON p.id=h.provider_id
        WHERE p.code='statsbomb_open_data' AND h.operation<>'DELETE'
        ORDER BY h.provider_entity_id,h.mapping_id""",
        (cutoff,),
    ).fetchall()
    scoped = [row for row in claims if row[0] in associations]
    return {
        "phase": "R02-D",
        "status": "BLOCKED_WITH_EVIDENCE",
        "native_fixtures": len(matches),
        "native_players": len(associations),
        "native_lineup_occurrences": len(records),
        "native_participation_status_counts": dict(
            Counter(r["native_appearance"] for r in records)
        ),
        "closed_position_stint_occurrences": sum(r["closed_position_stints"] for r in records),
        "contradictory_lineup_occurrences": sum(
            r["source_relationship_status"] == "CONTRADICTORY" for r in records
        ),
        "all_statsbomb_recorded_player_claims": len(claims),
        "pilot_players_with_recorded_claim": len({row[0] for row in scoped}),
        "pilot_claimed_canonical_players": len({row[1] for row in scoped}),
        "claims": [
            {
                "native_player_id": native,
                "claimed_canonical_id": str(canonical),
                "mapping_method": method,
                "known_at": known.isoformat(),
                "mapping_id": str(key),
            }
            for native, canonical, method, known, key in scoped
        ],
        "native_players_with_multiple_team_associations": {
            native: sorted(teams) for native, teams in associations.items() if len(teams) > 1
        },
        "same_name_multiple_native_ids": {
            name: sorted(ids) for name, ids in names.items() if len(ids) > 1
        },
        "canonical_identity_admissions": 0,
        "cross_provider_admissions": 0,
        "qualified_membership_intervals": 0,
        "qualified_transfer_dates": 0,
        "qualified_canonical_appearances": 0,
        "qualified_minutes_exposures": 0,
        "qualified_player_market_labels": {
            key: 0
            for key in (
                "goals",
                "assists",
                "shots",
                "SOT",
                "passes",
                "tackles",
                "fouls",
                "cards",
                "goalkeeper_saves",
            )
        },
        "records": records,
        "limitations": [
            "Native Starting XI/substitution reasons establish source-scoped appearance evidence, "
            "not a canonical identity or knowledge of the lineup before kickoff.",
            "No position or absent player-stat row proves unused substitution or nonappearance. "
            "Unknown source roles remain UNKNOWN.",
            "Closed position stints do not independently establish settlement-compatible minute "
            "exposure; no 90-minute default or invented minute total is used.",
            "Fixture-scoped team associations are not continuous membership intervals. Multiple "
            "teams are transfer-review candidates, not confirmed transfers or exact dates.",
            "Player identity admissions and participant/exposure/void semantics are still missing; "
            "every canonical player-market label remains blocked.",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--match-resource-id", required=True, type=UUID)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--section", choices=("identity", "time", "players"), default="identity")
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
        if args.section == "identity":
            report = identity_report(connection, args.source_root, matches, snapshot[0])
            report["phase"] = "R02-B"
        elif args.section == "time":
            report = time_report(connection, args.source_root, matches, args.match_resource_id)
        else:
            report = player_report(connection, args.source_root, matches, snapshot[0])
        report.update(
            {
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
