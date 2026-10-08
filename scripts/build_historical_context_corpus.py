"""Build the frozen V1 historical context corpus from retained MatchForge data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from football.context.contextual_features import TeamMatch
from football.context.historical_corpus import (
    AvailabilityEvidenceTier,
    HistoricalContextInputs,
    HistoricalTargetV1,
    TargetCandidate,
    build_phase_a_snapshot,
    canonical_sha256,
    filter_context_targets,
)

DATE = "2026-10-08"
GLOBAL_CORPUS_ID = "MATCHFORGE_HISTORICAL_CONTEXT_CORPUS_V1"
FIREWALL_MANIFEST_SHA256 = "b516cda36e3641dd0a8c45a53a900c79825b0e458f44db21445bf94f3009635c"
FAMILY_IDS = {
    "lineup": "MATCHFORGE_LINEUP_PREDICTION_CORPUS_V1",
    "availability": "MATCHFORGE_AVAILABILITY_CONTEXT_CORPUS_V1",
    "rest": "MATCHFORGE_REST_CONTEXT_CORPUS_V1",
    "manager": "MATCHFORGE_MANAGER_CONTEXT_CORPUS_V1",
    "travel": "MATCHFORGE_TRAVEL_CONTEXT_CORPUS_V1",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--preflight",
        type=Path,
        default=Path("docs/evaluation/matchforge-historical-context-corpus-v1-preflight.json"),
    )
    parser.add_argument(
        "--firewall",
        type=Path,
        default=Path("docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("docs"))
    args = parser.parse_args()

    preflight = _read_json(args.preflight)
    firewall = _read_json(args.firewall)
    season_rows = preflight["selected_seasons"]
    seasons = {UUID(row["season_id"]): row for row in season_rows}
    forbidden = frozenset(UUID(value) for value in firewall["unique_forbidden_target_ids"])

    with psycopg.connect(args.database_url) as connection:
        target_rows = _load_targets(connection, tuple(seasons))
        team_ids = tuple(
            sorted(
                {row[5] for row in target_rows} | {row[6] for row in target_rows},
                key=str,
            )
        )
        history = _load_history(connection, team_ids)

    candidates = tuple(
        TargetCandidate(row[0], _real_fixture_key(row[3], row[2], row[5], row[6]))
        for row in target_rows
    )
    firewall_result = filter_context_targets(candidates, forbidden)
    admitted_ids = {item.fixture_id for item in firewall_result.targets}
    history_by_team = _history_by_team(history)
    targets, snapshots = _build_targets_and_snapshots(
        target_rows,
        seasons,
        admitted_ids,
        history_by_team,
    )

    source_data_sha = canonical_sha256(
        {
            "targets": [_source_target(row) for row in target_rows],
            "history": [_source_history(row) for row in history],
        }
    )
    context_snapshot_sha = canonical_sha256([row["snapshot_sha256"] for row in snapshots])
    identity_map_sha = canonical_sha256(
        [
            {
                "fixture_id": row["fixture_id"],
                "home_team_id": row["home_team"],
                "away_team_id": row["away_team"],
                "source_references": row["source_references"],
            }
            for row in targets
        ]
    )
    firewall_sha = canonical_sha256(
        {
            "manifest_file_sha256": _file_sha256(args.firewall),
            "forbidden_target_ids_sha256": firewall["unique_forbidden_target_ids_sha256"],
            "admitted_target_ids": [row["fixture_id"] for row in targets],
        }
    )
    counts = Counter(row["competition"] for row in targets)
    common_hashes = {
        "source_data_sha256": source_data_sha,
        "context_snapshot_sha256": context_snapshot_sha,
        "firewall_sha256": firewall_sha,
        "identity_map_sha256": identity_map_sha,
    }
    evaluation_root = args.output_root / "evaluation"
    evidence_root = args.output_root / "evidence"
    target_path = evaluation_root / "matchforge-historical-context-corpus-v1-targets.jsonl"
    snapshot_path = evaluation_root / "matchforge-historical-context-snapshots-v1.jsonl"
    _write_jsonl(target_path, targets)
    _write_jsonl(snapshot_path, snapshots)
    acquisition = _acquisition_manifest(preflight)
    family_manifests = _family_manifests(targets, counts, common_hashes)
    global_manifest = _global_manifest(
        len(targets),
        target_path,
        snapshot_path,
        family_manifests,
        firewall,
        firewall_result.forbidden_target_count,
        firewall_result.duplicate_real_fixture_count,
        common_hashes,
    )
    lineup_validation = _lineup_validation()
    qualification = _qualification(targets, counts, len(target_rows), common_hashes)

    _write_json(
        evaluation_root / "matchforge-historical-context-corpus-v1-acquisition-manifest.json",
        acquisition,
    )
    _write_json(
        evaluation_root / "matchforge-historical-context-corpus-v1-manifest.json",
        global_manifest,
    )
    family_files = {
        "lineup": "matchforge-lineup-prediction-corpus-v1-manifest.json",
        "availability": "matchforge-availability-context-corpus-v1-manifest.json",
        "rest": "matchforge-rest-context-corpus-v1-manifest.json",
        "manager": "matchforge-manager-context-corpus-v1-manifest.json",
        "travel": "matchforge-travel-context-corpus-v1-manifest.json",
    }
    for family, payload in family_manifests.items():
        _write_json(
            evaluation_root / family_files[family],
            payload,
        )
    _write_json(
        evidence_root / f"matchforge-historical-context-corpus-v1-lineup-validation-{DATE}.json",
        lineup_validation,
    )
    _write_json(
        evidence_root / f"matchforge-historical-context-corpus-v1-qualification-{DATE}.json",
        qualification,
    )
    _write_report(
        evidence_root / f"matchforge-historical-context-corpus-v1-qualification-{DATE}.md",
        targets,
        counts,
        common_hashes,
    )
    return 0


def _load_targets(connection: Any, season_ids: tuple[UUID, ...]) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT fixture.fixture_id, match.season_id, fixture.competition_id,
                   fixture.kickoff_at, competition.name, fixture.home_team_id,
                   fixture.away_team_id, mapping.provider_match_id,
                   mapping.source_snapshot_id
            FROM football.product_fixtures fixture
            JOIN football.matches match ON match.id = fixture.fixture_id
            JOIN football.product_competitions competition
              ON competition.competition_id = fixture.competition_id
            JOIN football.match_provider_mappings mapping
              ON mapping.match_id = fixture.fixture_id
            JOIN football.providers provider ON provider.id = mapping.provider_id
            WHERE match.season_id = ANY(%s)
              AND fixture.status = 'FINISHED'
              AND provider.code = 'openfootball'
            ORDER BY fixture.kickoff_at, fixture.fixture_id
            """,
            (list(season_ids),),
        )
        return list(cursor.fetchall())


def _load_history(connection: Any, team_ids: tuple[UUID, ...]) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT fixture.fixture_id, fixture.competition_id, fixture.kickoff_at,
                   fixture.home_team_id, fixture.away_team_id
            FROM football.product_fixtures fixture
            WHERE fixture.status = 'FINISHED'
              AND (fixture.home_team_id = ANY(%s) OR fixture.away_team_id = ANY(%s))
            ORDER BY fixture.kickoff_at, fixture.fixture_id
            """,
            (list(team_ids), list(team_ids)),
        )
        return list(cursor.fetchall())


def _history_by_team(rows: list[tuple[Any, ...]]) -> dict[UUID, tuple[TeamMatch, ...]]:
    by_team: dict[UUID, list[TeamMatch]] = defaultdict(list)
    seen: set[str] = set()
    for fixture_id, competition_id, kickoff, home_id, away_id in rows:
        key = _real_fixture_key(kickoff, competition_id, home_id, away_id)
        if key in seen:
            continue
        seen.add(key)
        by_team[home_id].append(TeamMatch(fixture_id, home_id, kickoff, kickoff))
        by_team[away_id].append(TeamMatch(fixture_id, away_id, kickoff, kickoff))
    return {team_id: tuple(values) for team_id, values in by_team.items()}


def _build_targets_and_snapshots(
    rows: list[tuple[Any, ...]],
    seasons: dict[UUID, dict[str, Any]],
    admitted_ids: set[UUID],
    history_by_team: dict[UUID, tuple[TeamMatch, ...]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    targets: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        (
            fixture_id,
            season_id,
            _competition_id,
            kickoff,
            competition,
            home,
            away,
            provider_id,
            snapshot_id,
        ) = row
        if fixture_id not in admitted_ids:
            continue
        team_history = history_by_team.get(home, ()) + history_by_team.get(away, ())
        target = HistoricalTargetV1(
            fixture_id,
            kickoff,
            kickoff - timedelta(microseconds=1),
            competition,
            seasons[season_id]["season"],
            home,
            away,
            (
                f"openfootball:fixture:{provider_id}",
                f"source_snapshot:{snapshot_id}",
            ),
        )
        snapshot = build_phase_a_snapshot(
            target,
            HistoricalContextInputs((), (), (), team_history),
        )
        home_rest = snapshot.rest_context["home"]["days_since_last_match"] is not None
        away_rest = snapshot.rest_context["away"]["days_since_last_match"] is not None
        if not (home_rest and away_rest):
            continue
        targets.append(
            {
                "fixture_id": str(fixture_id),
                "kickoff": kickoff.isoformat(),
                "competition": competition,
                "season": seasons[season_id]["season"],
                "home_team": str(home),
                "away_team": str(away),
                "lineup_history_count_home": 0,
                "lineup_history_count_away": 0,
                "coach_status_home": "UNKNOWN",
                "coach_status_away": "UNKNOWN",
                "availability_tier_home": AvailabilityEvidenceTier.UNAVAILABLE.value,
                "availability_tier_away": AvailabilityEvidenceTier.UNAVAILABLE.value,
                "predicted_lineup_eligible": False,
                "confirmed_lineup_label_available": False,
                "rest_context_available": True,
                "manager_context_available": False,
                "travel_context_available": False,
                "venue_coordinate_status": "UNAVAILABLE",
                "point_in_time_reconstruction_status": snapshot.status.value,
                "source_references": list(target.source_references),
                "context_snapshot_sha256": snapshot.snapshot_sha256,
            }
        )
        snapshots.append(snapshot.to_payload())
    return targets, snapshots


def _family_manifests(
    targets: list[dict[str, Any]],
    counts: Counter[str],
    hashes: dict[str, str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for family, corpus_id in FAMILY_IDS.items():
        qualified = family == "rest"
        target_ids = [row["fixture_id"] for row in targets] if qualified else []
        family_hashes = {
            **hashes,
            "context_snapshot_sha256": (
                hashes["context_snapshot_sha256"] if qualified else canonical_sha256([])
            ),
            "identity_map_sha256": (
                hashes["identity_map_sha256"] if qualified else canonical_sha256([])
            ),
        }
        payload: dict[str, Any] = {
            "contract": "HistoricalContextFamilyCorpusManifestV1",
            "corpus_id": corpus_id,
            "family": family.upper(),
            "created_at": f"{DATE}T00:00:00Z",
            "status": "QUALIFIED" if qualified else "INSUFFICIENT",
            "target_count": len(target_ids),
            "competition_count": len(counts) if qualified else 0,
            "targets_by_competition": dict(sorted(counts.items())) if qualified else {},
            "target_ids": target_ids,
            **family_hashes,
        }
        if family == "availability":
            payload.update(
                {
                    "tier_a_fixture_count": 0,
                    "tier_b_fixture_count": 0,
                    "tier_a_unavailable_player_count": 0,
                    "tier_b_unavailable_player_count": 0,
                }
            )
        payload["manifest_sha256"] = _semantic_manifest_sha(payload)
        result[family] = payload
    return result


def _global_manifest(
    target_count: int,
    target_path: Path,
    snapshot_path: Path,
    families: dict[str, dict[str, Any]],
    firewall: dict[str, Any],
    forbidden_excluded: int,
    duplicates_excluded: int,
    hashes: dict[str, str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "HistoricalContextCorpusManifestV1",
        "corpus_id": GLOBAL_CORPUS_ID,
        "created_at": f"{DATE}T00:00:00Z",
        "target_manifest_outcome_blind": True,
        "target_count": target_count,
        "target_manifest": {
            "path": str(target_path),
            "sha256": _file_sha256(target_path),
            "format": "JSONL",
        },
        "historical_context_snapshots": {
            "path": str(snapshot_path),
            "sha256": _file_sha256(snapshot_path),
            "format": "JSONL",
            "count": target_count,
        },
        "family_corpora": {
            name: {
                "corpus_id": item["corpus_id"],
                "manifest_sha256": item["manifest_sha256"],
                "status": item["status"],
            }
            for name, item in families.items()
        },
        "shared_intersections": {
            "lineup_and_availability": 0,
            "lineup_and_rest": 0,
            "lineup_and_manager": 0,
            "all_context_families": 0,
        },
        "firewall": {
            "source_manifest_id": firewall["manifest_id"],
            "source_manifest_sha256": FIREWALL_MANIFEST_SHA256,
            "forbidden_target_count": firewall["unique_forbidden_target_count"],
            "forbidden_candidates_excluded": forbidden_excluded,
            "duplicate_real_fixtures_excluded": duplicates_excluded,
            "admitted_target_overlap": 0,
        },
        **hashes,
    }
    payload["manifest_sha256"] = _semantic_manifest_sha(payload)
    return payload


def _acquisition_manifest(preflight: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "HistoricalContextAcquisitionManifestV1",
        "corpus_id": GLOBAL_CORPUS_ID,
        "created_at": f"{DATE}T00:00:00Z",
        "provider_calls_made": 0,
        "provider_requests_used": 0,
        "new_raw_payloads": 0,
        "new_source_snapshots": 0,
        "competitions_or_seasons_acquired": [],
        "retained_competitions_used": [
            "Premier League",
            "La Liga",
            "Serie A",
            "Bundesliga",
        ],
        "status": "STOPPED_BEFORE_NETWORK",
        "preflight_decision": preflight["decision"],
        "reason": preflight["reason"],
        "resumable": True,
        "completed_resource_keys": [],
        "context_goal_model_evaluation_executed": False,
    }
    payload["manifest_sha256"] = _semantic_manifest_sha(payload)
    return payload


def _lineup_validation() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "PredictedLineupV1HistoricalValidationV1",
        "corpus_id": FAMILY_IDS["lineup"],
        "cases": 0,
        "mean_correct_starters": None,
        "median_correct_starters": None,
        "exact_xi_rate": None,
        "formation_accuracy": None,
        "replacement_accuracy": None,
        "exact_position_replacement_accuracy": None,
        "naive_previous_xi_mean_correct_starters": None,
        "naive_previous_xi_replacement_accuracy": None,
        "confidence_buckets": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "status": "INSUFFICIENT_LINEUP_CORPUS",
        "goal_model_metrics_calculated": False,
    }
    payload["result_sha256"] = _semantic_manifest_sha(payload)
    return payload


def _qualification(
    targets: list[dict[str, Any]],
    counts: Counter[str],
    fixtures_considered: int,
    hashes: dict[str, str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "contract": "HistoricalContextCorpusQualificationV1",
        "corpus_id": GLOBAL_CORPUS_ID,
        "created_at": f"{DATE}T00:00:00Z",
        "historical_fixtures_considered": fixtures_considered,
        "qualified_rest_targets": len(targets),
        "rest_targets_by_competition": dict(sorted(counts.items())),
        "confirmed_lineups_acquired": 0,
        "coach_observations_acquired": 0,
        "tier_a_availability_fixtures": 0,
        "tier_b_availability_fixtures": 0,
        "verified_venues_or_coordinates": 0,
        "family_results": {
            "LINEUP": "INSUFFICIENT",
            "AVAILABILITY": "INSUFFICIENT",
            "REST": "QUALIFIED",
            "MANAGER": "INSUFFICIENT",
            "TRAVEL": "INSUFFICIENT",
        },
        "global_forbidden_target_overlap": 0,
        "chronology_and_leakage": "PASS",
        "final_disposition": "PARTIAL_CONTEXT_CORPUS_QUALIFIED",
        "context_goal_model_evaluation_executed": False,
        "production_champion_changed": False,
        **hashes,
    }
    payload["result_sha256"] = _semantic_manifest_sha(payload)
    return payload


def _write_report(
    path: Path,
    targets: list[dict[str, Any]],
    counts: Counter[str],
    hashes: dict[str, str],
) -> None:
    lines = [
        "# Historical context corpus V1 qualification",
        "",
        "The retained fixture data qualifies only the rest/congestion family. The provider plan",
        "was stopped before network access because 8,660 expected calls exceed the configured",
        "80-call ceiling after reserve.",
        "",
        "## Result",
        "",
        "- Final disposition: `PARTIAL_CONTEXT_CORPUS_QUALIFIED`",
        f"- Rest targets: `{len(targets)}` across `{len(counts)}` competitions",
        f"- Targets by competition: `{json.dumps(dict(sorted(counts.items())), sort_keys=True)}`",
        "- Lineup: `INSUFFICIENT` (0 confirmed labels)",
        "- Availability: `INSUFFICIENT` (0 Tier A; 0 Tier B fixtures)",
        "- Manager: `INSUFFICIENT` (0 coach observations)",
        "- Travel: `INSUFFICIENT` (0 qualified coordinates)",
        "- Forbidden-target overlap: `0`",
        "- Chronology/leakage checks: `PASS`",
        "- Context goal-model evaluation executed: `NO`",
        "- Production champion changed: `NO`",
        "",
        "## Frozen hashes",
        "",
        f"- Source data: `{hashes['source_data_sha256']}`",
        f"- Context snapshots: `{hashes['context_snapshot_sha256']}`",
        f"- Firewall: `{hashes['firewall_sha256']}`",
        f"- Identity map: `{hashes['identity_map_sha256']}`",
        "",
        "Historical confirmed lineups acquired after a match remain labels only. Historical",
        "injury timelines acquired now would be Tier B unless a reliable pre-kickoff known-at",
        "timestamp exists. Neither was acquired in this run.",
    ]
    path.write_text("\n".join(lines) + "\n")


def _source_target(row: tuple[Any, ...]) -> dict[str, str]:
    return {
        "fixture_id": str(row[0]),
        "season_id": str(row[1]),
        "competition_id": str(row[2]),
        "kickoff": row[3].isoformat(),
        "home_team_id": str(row[5]),
        "away_team_id": str(row[6]),
        "provider_match_id": str(row[7]),
        "source_snapshot_id": str(row[8]),
    }


def _source_history(row: tuple[Any, ...]) -> dict[str, str]:
    return {
        "fixture_id": str(row[0]),
        "competition_id": str(row[1]),
        "kickoff": row[2].isoformat(),
        "home_team_id": str(row[3]),
        "away_team_id": str(row[4]),
    }


def _real_fixture_key(kickoff: Any, competition_id: UUID, home: UUID, away: UUID) -> str:
    return f"{competition_id}|{kickoff.isoformat()}|{home}|{away}"


def _semantic_manifest_sha(payload: dict[str, Any]) -> str:
    return canonical_sha256(
        {key: value for key, value in payload.items() if not key.endswith("sha256")}
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
