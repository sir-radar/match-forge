#!/usr/bin/env python3
"""Freeze V1.2 replacement-holdout controls without reading target outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psycopg
from football.forecasting.fresh_corpus import semantic_sha256
from football.forecasting.replacement_holdout import (
    COMPETITION_PRIOR_K,
    COMPETITION_PRIOR_MODEL_ID,
    REFERENCE_STACK_ID,
    ChampionEligibility,
    ChampionEligibilityInput,
    ReferenceStackV1,
    champion_eligibility,
)
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-09"
PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_2"
PARENT_PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_1"
AUTHORIZATION_ID = "AUTHORIZE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V1"
REPLACEMENT_MANIFEST_ID = "MATCHFORGE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V1"
AMENDMENT_REASON = "EXPLICIT_CHAMPION_ELIGIBILITY_AND_REFERENCE_STACK"
RESEARCH_CUTOFF = datetime.fromisoformat("2026-10-09T00:00:00+00:00")
FIT_CUTOFF = datetime.fromisoformat("2022-05-14T13:35:00+00:00")
TARGET_COUNT = 500

DOMAINS = {
    "1438be97-8e2f-5cc9-88ae-ceec41a2dd4a": ("Championship", "openfootball", 167),
    "9c79fa40-2247-5b6e-b4d4-4d5e11978c88": (
        "National League",
        "football_data_uk",
        167,
    ),
    "e4cf1cee-9290-5ee0-b1b7-e7eea69ddd41": ("League Two", "football_data_uk", 166),
}

OLD_CORPUS = ROOT / "docs/evaluation/full-coverage-v2-fresh-development-corpus-v1.json"
OLD_CONFIG = ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-config.json"
OLD_PREREG = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-preregistration.json"
)
OLD_STATE = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-execution-state.json"
)
OLD_RESULT = ROOT / "docs/evidence/full-coverage-challengers-v2-reevaluation-v1-1-2026-10-09.json"
OLD_FIREWALL = ROOT / "docs/evaluation/full-coverage-challengers-v2-spent-targets-v1.json"
CONTEXT_TARGETS = ROOT / "docs/evaluation/matchforge-historical-context-corpus-v1-targets.jsonl"

FIREWALL = ROOT / "docs/evaluation/full-coverage-v2-global-forbidden-targets-v1-2.json"
TARGET_MANIFEST = ROOT / "docs/evaluation/full-coverage-v2-replacement-holdout-v1.json"
REFERENCE_CONFIG = ROOT / "docs/evaluation/competition-prior-poisson-v1-artifact.json"
CONFIG = ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-2-config.json"
OWNER_DECISION = ROOT / (
    f"docs/evidence/owner-decision-authorize-full-coverage-v2-replacement-holdout-v1-{DATE}.json"
)
PREREGISTRATION = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-2-preregistration.json"
)
EXECUTION_STATE = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-2-execution-state.json"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    args = parser.parse_args()
    prepare(args.database_url, args.source_commit, args.repository_root.resolve())
    return 0


def prepare(database_url: str, source_commit: str, root: Path = ROOT) -> dict[str, object]:
    _verify_clean_source(root, source_commit)
    _verify_previous_protocol(root)
    old_corpus = _json(root / OLD_CORPUS.relative_to(ROOT))
    old_targets = cast(list[dict[str, object]], old_corpus["targets"])
    firewall = _global_firewall(root, old_targets)
    forbidden = frozenset(cast(list[str], firewall["unique_forbidden_target_ids"]))

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        candidates = _candidate_metadata(connection)
        histories = _history_metadata(connection, candidates)
        _require_identity_mappings(connection, candidates)
        selected = _select_targets(candidates, histories, forbidden)
        global_home_rate, global_away_rate = _global_rates(connection, old_targets)

    qualification = _qualify(selected, forbidden)
    if qualification["failures"]:
        raise RuntimeError(str(cast(list[str], qualification["failures"])[0]))
    target_sha = semantic_sha256(selected)
    target_manifest = {
        "contract": "MatchForgeReplacementHoldoutManifestV1",
        "manifest_id": REPLACEMENT_MANIFEST_ID,
        "protocol_id": PROTOCOL_ID,
        "selection_mode": "OUTCOME_BLIND_METADATA_ONLY",
        "outcome_fields_read_for_selection": False,
        "research_cutoff": RESEARCH_CUTOFF.isoformat(),
        "global_firewall_sha256": semantic_sha256(firewall),
        "target_manifest_sha256": target_sha,
        "qualification": qualification,
        "targets": selected,
    }
    _write(root / TARGET_MANIFEST.relative_to(ROOT), target_manifest)
    _write(root / FIREWALL.relative_to(ROOT), firewall)

    train_rows = [row for row in old_targets if row["split"] == "TRAIN"]
    validation_rows = [row for row in old_targets if row["split"] == "VALIDATION"]
    training_manifest_sha = semantic_sha256(train_rows)
    validation_manifest_sha = semantic_sha256(validation_rows)
    reference_semantic = {
        "contract": "CompetitionPriorPoissonArtifactV1",
        "model_id": COMPETITION_PRIOR_MODEL_ID,
        "global_home_rate": global_home_rate,
        "global_away_rate": global_away_rate,
        "k_prior": COMPETITION_PRIOR_K,
        "source_development_dataset_hash": training_manifest_sha,
        "implementation_source_commit": source_commit,
        "team_specific_inputs": False,
    }
    reference = {**reference_semantic, "artifact_sha256": semantic_sha256(reference_semantic)}
    _write(root / REFERENCE_CONFIG.relative_to(ROOT), reference)

    frozen_config = _json(root / OLD_CONFIG.relative_to(ROOT))
    old_prereg = _json(root / OLD_PREREG.relative_to(ROOT))
    candidate_shas = {
        key: value["artifact_sha256"]
        for key, value in cast(
            dict[str, dict[str, object]], frozen_config["candidate_artifacts"]
        ).items()
    }
    config = {
        "contract": "MatchForgeFullCoverageV2ReplacementConfigurationV1",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "frozen_v2_configuration_ref": OLD_CONFIG.relative_to(ROOT).as_posix(),
        "frozen_v2_configuration_file_sha256": _file_sha(root / OLD_CONFIG.relative_to(ROOT)),
        "frozen_v2_candidate_artifact_sha256": candidate_shas,
        "frozen_training_manifest_sha256": training_manifest_sha,
        "frozen_validation_manifest_sha256": validation_manifest_sha,
        "selected_cold_start": frozen_config["selected_cold_start"],
        "selected_transfer_weight": frozen_config["selected_transfer_weight"],
        "ensemble_status": "PREVIOUSLY_VALID_FROZEN_DEVELOPMENT",
        "ensemble_weights": frozen_config["ensemble_weights"],
        "reference_stack_id": REFERENCE_STACK_ID,
        "reference_artifact_ref": REFERENCE_CONFIG.relative_to(ROOT).as_posix(),
        "reference_artifact_sha256": reference["artifact_sha256"],
        "replacement_target_manifest_ref": TARGET_MANIFEST.relative_to(ROOT).as_posix(),
        "replacement_target_manifest_sha256": target_sha,
        "source_commit": source_commit,
        "v1_1_scientific_source_sha256": old_prereg["scientific_source_sha256"],
    }
    _write(root / CONFIG.relative_to(ROOT), config)
    decision = {
        "contract": "MatchForgeOwnerDecisionV1",
        "decision_id": AUTHORIZATION_ID,
        "authorized_at": f"{DATE}T00:00:00Z",
        "recorded_at": f"{DATE}T00:00:00Z",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "amendment_reason": AMENDMENT_REASON,
        "authorized": [
            "champion eligibility implementation",
            "reference baseline implementation",
            "fresh replacement-HOLDOUT discovery",
            "fresh corpus qualification",
            "execution infrastructure",
            "one replacement development HOLDOUT execution",
            "evidence generation",
        ],
        "not_authorized": [
            "retuning V2B",
            "changing cold-start coefficients",
            "changing selected k or L2",
            "changing transfer or ensemble weights",
            "new context features or H2H",
            "production promotion",
            "reuse of previous HOLDOUT",
        ],
    }
    _write(root / OWNER_DECISION.relative_to(ROOT), decision)
    _record_owner_decision(root)
    _write(
        root / EXECUTION_STATE.relative_to(ROOT),
        {"logical_executions": 0, "outcomes_loaded": False, "protocol_id": PROTOCOL_ID},
    )

    source_files = _scientific_source_files(root)
    allowed = sorted(
        path.relative_to(ROOT).as_posix()
        for path in (
            FIREWALL,
            TARGET_MANIFEST,
            REFERENCE_CONFIG,
            CONFIG,
            OWNER_DECISION,
            PREREGISTRATION,
            EXECUTION_STATE,
            ROOT / "docs/project-status.json",
        )
    )
    preregistration = {
        "contract": "MatchForgeFullCoverageV2ReplacementPreregistrationV1",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "authorization": AUTHORIZATION_ID,
        "amendment_reason": AMENDMENT_REASON,
        "source_commit": source_commit,
        "required_execution_parent": source_commit,
        "execution_commit_policy": "DIRECT_CHILD_CONTROL_ONLY_V1",
        "execution_commit_allowed_files": allowed,
        "scientific_source_files": list(source_files),
        "scientific_source_sha256": _scientific_source_sha(root, source_files),
        "owner_decision_ref": OWNER_DECISION.relative_to(ROOT).as_posix(),
        "owner_decision_sha256": _file_sha(root / OWNER_DECISION.relative_to(ROOT)),
        "configuration_ref": CONFIG.relative_to(ROOT).as_posix(),
        "configuration_sha256": _file_sha(root / CONFIG.relative_to(ROOT)),
        "target_manifest_ref": TARGET_MANIFEST.relative_to(ROOT).as_posix(),
        "target_manifest_file_sha256": _file_sha(root / TARGET_MANIFEST.relative_to(ROOT)),
        "target_manifest_sha256": target_sha,
        "firewall_ref": FIREWALL.relative_to(ROOT).as_posix(),
        "firewall_file_sha256": _file_sha(root / FIREWALL.relative_to(ROOT)),
        "firewall_sha256": semantic_sha256(firewall),
        "reference_artifact_ref": REFERENCE_CONFIG.relative_to(ROOT).as_posix(),
        "reference_artifact_file_sha256": _file_sha(root / REFERENCE_CONFIG.relative_to(ROOT)),
        "reference_artifact_sha256": reference["artifact_sha256"],
        "frozen_v2_configuration_ref": OLD_CONFIG.relative_to(ROOT).as_posix(),
        "frozen_v2_configuration_file_sha256": _file_sha(root / OLD_CONFIG.relative_to(ROOT)),
        "frozen_v2_candidate_artifact_sha256": candidate_shas,
        "execution_state_ref": EXECUTION_STATE.relative_to(ROOT).as_posix(),
        "bootstrap": {
            "type": "MOVING_BLOCK",
            "block_length": 10,
            "replicates": 2000,
            "seed": 20260921,
            "confidence_interval": 0.95,
        },
        "acceptance_criteria": {
            "joint_ll_delta_max": -0.003,
            "joint_ll_ci_upper_max_exclusive": 0,
            "result_ll_delta_max": 0,
            "result_ll_ci_upper_max": 0,
            "brier_ci_upper_max": 0.01,
            "rps_ci_upper_max": 0.01,
            "crps_ci_upper_max": 0.02,
            "domain_joint_ll_delta_max": 0.02,
        },
    }
    _write(root / PREREGISTRATION.relative_to(ROOT), preregistration)
    return preregistration


def _candidate_metadata(connection: psycopg.Connection[dict[str, Any]]) -> list[dict[str, object]]:
    rows = connection.execute(
        """
        SELECT DISTINCT ON (h.fixture_id)
               h.fixture_id::text, h.kickoff_at, h.competition_id::text,
               pc.name AS competition_name, pc.country, pc.division,
               h.home_team_id::text, h.away_team_id::text,
               home.name AS home_team_name, away.name AS away_team_name,
               h.source_provider_code, h.source_snapshot_id::text,
               mapping.provider_match_id AS source_fixture_id
          FROM football.product_team_match_history h
          JOIN football.product_competitions pc ON pc.competition_id = h.competition_id
          JOIN football.product_teams home ON home.team_id = h.home_team_id
          JOIN football.product_teams away ON away.team_id = h.away_team_id
          JOIN LATERAL (
                SELECT m.provider_match_id
                  FROM football.match_provider_mappings m
                  JOIN football.providers p ON p.id = m.provider_id
                 WHERE m.match_id = h.fixture_id AND p.code = h.source_provider_code
                 ORDER BY m.first_seen_at, m.id LIMIT 1
          ) mapping ON true
         WHERE h.competition_id = ANY(%s::uuid[])
           AND h.kickoff_at > %s AND h.kickoff_at < %s
         ORDER BY h.fixture_id, h.source_snapshot_id
        """,
        (list(DOMAINS), FIT_CUTOFF, RESEARCH_CUTOFF),
    ).fetchall()
    return [
        dict(row)
        for row in rows
        if str(row["source_provider_code"]) == DOMAINS[str(row["competition_id"])][1]
    ]


def _history_metadata(
    connection: psycopg.Connection[dict[str, Any]], candidates: Sequence[Mapping[str, object]]
) -> dict[str, tuple[tuple[datetime, str, int | None], ...]]:
    teams = sorted(
        {str(row[key]) for row in candidates for key in ("home_team_id", "away_team_id")}
    )
    rows = connection.execute(
        """
        SELECT DISTINCT h.fixture_id, h.kickoff_at, h.competition_id::text,
               pc.division, h.home_team_id::text, h.away_team_id::text
          FROM football.product_team_match_history h
          JOIN football.product_competitions pc ON pc.competition_id = h.competition_id
         WHERE (h.home_team_id = ANY(%s::uuid[]) OR h.away_team_id = ANY(%s::uuid[]))
           AND h.kickoff_at < %s
        """,
        (teams, teams, RESEARCH_CUTOFF),
    ).fetchall()
    history: dict[str, list[tuple[datetime, str, int | None]]] = defaultdict(list)
    team_set = set(teams)
    for row in rows:
        for key in ("home_team_id", "away_team_id"):
            team = str(row[key])
            if team in team_set:
                history[team].append(
                    (
                        cast(datetime, row["kickoff_at"]),
                        str(row["competition_id"]),
                        cast(int | None, row["division"]),
                    )
                )
    return {key: tuple(sorted(values)) for key, values in history.items()}


def _require_identity_mappings(
    connection: psycopg.Connection[dict[str, Any]], candidates: Sequence[Mapping[str, object]]
) -> None:
    expected = {
        (str(row[key]), str(row["source_provider_code"]))
        for row in candidates
        for key in ("home_team_id", "away_team_id")
    }
    rows = connection.execute(
        """
        SELECT DISTINCT mapping.team_id::text, provider.code
          FROM football.team_provider_mappings mapping
          JOIN football.providers provider ON provider.id = mapping.provider_id
         WHERE mapping.team_id = ANY(%s::uuid[])
           AND provider.code = ANY(%s::text[])
           AND mapping.valid_to IS NULL
        """,
        (sorted({key[0] for key in expected}), sorted({key[1] for key in expected})),
    ).fetchall()
    actual = {(str(row["team_id"]), str(row["code"])) for row in rows}
    missing = sorted(expected - actual)
    if missing:
        raise RuntimeError(f"unresolved provider-neutral team identity: {missing[:10]}")


def _select_targets(
    candidates: Sequence[Mapping[str, object]],
    histories: Mapping[str, Sequence[tuple[datetime, str, int | None]]],
    forbidden: frozenset[str],
) -> list[dict[str, object]]:
    by_domain: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candidates:
        fixture_id = str(row["fixture_id"])
        if fixture_id in forbidden:
            continue
        kickoff = cast(datetime, row["kickoff_at"])
        home_id = str(row["home_team_id"])
        away_id = str(row["away_team_id"])
        home_history = histories.get(home_id, ())
        away_history = histories.get(away_id, ())
        home_count = bisect_left([item[0] for item in home_history], kickoff)
        away_count = bisect_left([item[0] for item in away_history], kickoff)
        eligibility = champion_eligibility(
            ChampionEligibilityInput(
                fixture_identity_resolved=True,
                home_identity_resolved=True,
                away_identity_resolved=True,
                competition_context_available=True,
                required_features_available=True,
                home_prior_match_count=home_count,
                away_prior_match_count=away_count,
            )
        )
        reference = ReferenceStackV1().select(eligibility)
        competition_id = str(row["competition_id"])
        season = _season(str(row["country"]), kickoff)
        home_promotion = _promotion(home_history, season, cast(int | None, row["division"]))
        away_promotion = _promotion(away_history, season, cast(int | None, row["division"]))
        by_domain[competition_id].append(
            {
                "fixture_id": fixture_id,
                "kickoff": kickoff.astimezone(UTC).isoformat(),
                "competition_id": competition_id,
                "competition": str(row["competition_name"]),
                "season": season,
                "home_team": home_id,
                "away_team": away_id,
                "home_team_name": str(row["home_team_name"]),
                "away_team_name": str(row["away_team_name"]),
                "home_prior_match_count": home_count,
                "away_prior_match_count": away_count,
                "champion_eligibility": eligibility.status.value,
                "champion_ineligibility_reason": eligibility.reason.value
                if eligibility.reason
                else None,
                "home_artifact_state": "UNSEEN_TEAM",
                "away_artifact_state": "UNSEEN_TEAM",
                "V2B_expected_route": "COLD_START_BOTH",
                "home_promotion_state": home_promotion,
                "away_promotion_state": away_promotion,
                "reference_model_id": reference.model_id,
                "reference_mode": reference.mode.value,
                "source_provider": str(row["source_provider_code"]),
                "source_fixture_id": str(row["source_fixture_id"]),
                "source_snapshot_id": str(row["source_snapshot_id"]),
            }
        )
    selected: list[dict[str, object]] = []
    for competition_id, (_, _, quota) in DOMAINS.items():
        ordered = sorted(
            by_domain[competition_id],
            key=lambda item: (
                item["champion_eligibility"] == ChampionEligibility.ELIGIBLE.value,
                item["kickoff"],
                item["fixture_id"],
            ),
        )
        if len(ordered) < quota:
            raise RuntimeError("DEFER_INSUFFICIENT_FRESH_REPLACEMENT_HOLDOUT")
        selected.extend(ordered[:quota])
    return sorted(selected, key=lambda item: (str(item["kickoff"]), str(item["fixture_id"])))


def _qualify(
    targets: Sequence[Mapping[str, object]], forbidden: frozenset[str]
) -> dict[str, object]:
    competitions = Counter(str(row["competition"]) for row in targets)
    seasons = Counter(str(row["season"]) for row in targets)
    eligibility = Counter(str(row["champion_eligibility"]) for row in targets)
    reasons = Counter(
        str(row["champion_ineligibility_reason"])
        for row in targets
        if row["champion_ineligibility_reason"] is not None
    )
    cold = sum(str(row["V2B_expected_route"]).startswith("COLD_START") for row in targets)
    failures: list[str] = []
    if len(targets) < 300:
        failures.append("DEFER_INSUFFICIENT_FRESH_REPLACEMENT_HOLDOUT")
    if sum(value >= 75 for value in competitions.values()) < 3:
        failures.append("DEFER_INSUFFICIENT_FRESH_REPLACEMENT_HOLDOUT")
    if competitions and max(competitions.values()) / len(targets) > 0.60:
        failures.append("DEFER_INSUFFICIENT_FRESH_REPLACEMENT_HOLDOUT")
    if eligibility[ChampionEligibility.ELIGIBLE.value] < 100:
        failures.append("INSUFFICIENT_CHAMPION_ELIGIBLE_REPLACEMENT_SAMPLE")
    if cold < 100:
        failures.append("INSUFFICIENT_NATIVE_COLD_START_SAMPLE")
    overlaps = sorted(str(row["fixture_id"]) for row in targets if row["fixture_id"] in forbidden)
    if overlaps:
        failures.append("FAIL_CLOSED_SPENT_OR_PROTECTED_INTERSECTION")
    return {
        "target_count": len(targets),
        "competition_counts": dict(sorted(competitions.items())),
        "season_counts": dict(sorted(seasons.items())),
        "champion_eligibility_counts": dict(sorted(eligibility.items())),
        "champion_ineligibility_reason_counts": dict(sorted(reasons.items())),
        "cold_start_targets": cold,
        "global_firewall_overlap": len(overlaps),
        "champion_ineligible_sample_sufficient": eligibility[ChampionEligibility.INELIGIBLE.value]
        >= 50,
        "failures": failures,
    }


def _global_rates(
    connection: psycopg.Connection[dict[str, Any]], old_targets: Sequence[Mapping[str, object]]
) -> tuple[float, float]:
    train_ids = [str(row["fixture_id"]) for row in old_targets if row["split"] == "TRAIN"]
    row = connection.execute(
        """
        SELECT avg(home_goals)::float8 AS home_rate, avg(away_goals)::float8 AS away_rate,
               count(DISTINCT fixture_id) AS target_count
          FROM football.product_team_match_history
         WHERE fixture_id = ANY(%s::uuid[])
        """,
        (train_ids,),
    ).fetchone()
    if row is None or int(row["target_count"]) != len(train_ids):
        raise RuntimeError("frozen DEVELOPMENT TRAIN data is incomplete")
    return float(row["home_rate"]), float(row["away_rate"])


def _global_firewall(root: Path, old_targets: Sequence[Mapping[str, object]]) -> dict[str, object]:
    previous = _json(root / OLD_FIREWALL.relative_to(ROOT))
    groups = list(cast(list[dict[str, object]], previous["groups"]))
    full_v2 = sorted(str(row["fixture_id"]) for row in old_targets)
    spent_holdout = sorted(
        str(row["fixture_id"]) for row in old_targets if row["split"] == "DEVELOPMENT_HOLDOUT"
    )
    context_ids = sorted(
        str(json.loads(line)["fixture_id"])
        for line in (root / CONTEXT_TARGETS.relative_to(ROOT))
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    )
    groups.extend(
        (
            {
                "group_id": "MATCHFORGE_FULL_COVERAGE_V2_FRESH_DEVELOPMENT_CORPUS_V1_ALL_TARGETS",
                "reason": "SPENT_V2_DEVELOPMENT_V1_1",
                "target_ids": full_v2,
            },
            {
                "group_id": "SPENT_V2_HOLDOUT_V1_1",
                "reason": "OUTCOMES_LOADED_EXACTLY_ONCE",
                "target_ids": spent_holdout,
            },
            {
                "group_id": "MATCHFORGE_HISTORICAL_CONTEXT_CORPUS_V1_ALL_TARGETS",
                "reason": "OTHER_MODEL_SELECTION_OR_EVALUATION_TARGETS",
                "target_ids": context_ids,
            },
        )
    )
    unique = sorted(
        {str(target) for group in groups for target in cast(list[str], group["target_ids"])}
    )
    return {
        "contract": "MatchForgeSpentTargetManifestV1_2",
        "manifest_id": "MATCHFORGE_GLOBAL_FORBIDDEN_TARGETS_2026_10_09_V1_2",
        "generated_from_outcome_fields": False,
        "groups": groups,
        "unique_forbidden_target_count": len(unique),
        "unique_forbidden_target_ids": unique,
        "unique_forbidden_target_ids_sha256": semantic_sha256(unique),
    }


def _verify_previous_protocol(root: Path) -> None:
    state = _json(root / OLD_STATE.relative_to(ROOT))
    result = _json(root / OLD_RESULT.relative_to(ROOT))
    if state != {
        "logical_execution_attempts": 1,
        "outcomes_loaded": True,
        "protocol_id": PARENT_PROTOCOL_ID,
    }:
        raise RuntimeError("previous V1.1 execution state changed")
    if result.get("development_disposition") != "FAIL_CLOSED_PROTOCOL_VIOLATION":
        raise RuntimeError("previous V1.1 disposition changed")


def _record_owner_decision(root: Path) -> None:
    path = root / "docs/project-status.json"
    status = _json(path)
    decisions = cast(list[str], status["owner_decisions"])
    if AUTHORIZATION_ID not in decisions:
        decisions.append(AUTHORIZATION_ID)
    status["updated_at"] = f"{DATE}T00:00:00Z"
    _write_pretty(path, status)


def _promotion(
    history: Sequence[tuple[datetime, str, int | None]],
    season: str,
    target_division: int | None,
) -> str:
    if target_division is None:
        return "PROMOTION_STATUS_UNKNOWN"
    start = int(season.split("/")[0]) - 1
    previous = f"{start}/{start + 1}"
    divisions = {
        division
        for kickoff, _, division in history
        if _season("", kickoff) == previous and division is not None
    }
    if len(divisions) != 1:
        return "PROMOTION_STATUS_UNKNOWN"
    return "PROMOTED_TEAM" if next(iter(divisions)) > target_division else "NOT_PROMOTED"


def _season(country: str, kickoff: datetime) -> str:
    if country == "Brazil":
        return str(kickoff.year)
    year = kickoff.year if kickoff.month >= 7 else kickoff.year - 1
    return f"{year}/{year + 1}"


def _scientific_source_files(root: Path) -> tuple[str, ...]:
    files = {
        path.relative_to(root).as_posix()
        for path in (root / "python/football/src/football/forecasting").rglob("*.py")
    }
    files.update(
        {
            "scripts/prepare_full_coverage_v2_replacement_holdout.py",
            "scripts/run_full_coverage_v2_replacement_holdout.py",
        }
    )
    if any(not (root / path).is_file() for path in files):
        raise RuntimeError("scientific source set is incomplete")
    return tuple(sorted(files))


def _scientific_source_sha(root: Path, files: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _verify_clean_source(root: Path, source_commit: str) -> None:
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True).strip()
    status = subprocess.check_output(("git", "status", "--porcelain"), cwd=root, text=True)
    if head != source_commit or status:
        raise RuntimeError("preparation requires the clean SOURCE_COMMIT at HEAD")


def _json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _write_pretty(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
