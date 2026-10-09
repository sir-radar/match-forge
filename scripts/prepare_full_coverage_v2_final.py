#!/usr/bin/env python3
"""Freeze V1.3 controls after canonical audit, without reading target outcomes."""

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
from typing import cast

import psycopg
from football.forecasting.fresh_corpus import semantic_sha256
from football.forecasting.replacement_holdout import (
    REFERENCE_STACK_ID,
    ChampionEligibility,
    ChampionEligibilityInput,
    ReferenceStackV1,
    champion_eligibility,
)
from football.history.fixture_identity import (
    RESOLUTION_VERSION,
    load_persisted_resolved_metadata,
)

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-10-09"
PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_3"
PARENT_PROTOCOL_ID = "MATCHFORGE_FULL_COVERAGE_CHALLENGERS_V2_REEVALUATION_V1_2"
AUTHORIZATION_ID = "AUTHORIZE_CANONICAL_HISTORY_REPAIR_AND_V2_FINAL_REPLACEMENT_EVALUATION_V1"
REPLACEMENT_MANIFEST_ID = "MATCHFORGE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V2"
REHEARSAL_ID = "MATCHFORGE_V2_PREOUTCOME_READINESS_REHEARSAL_V1"
AMENDMENT_REASON = "CANONICAL_REAL_FIXTURE_IDENTITY_AND_EXHAUSTIVE_PREOUTCOME_READINESS"
FIT_CUTOFF = datetime.fromisoformat("2022-05-14T13:35:00+00:00")
RESEARCH_CUTOFF = datetime.fromisoformat("2026-10-09T00:00:00+00:00")
TARGET_COUNT = 750
DOMAIN_TARGET_COUNT = 250
DOMAIN_ELIGIBLE_COUNT = 150
DOMAIN_INELIGIBLE_COUNT = 100

OLD_CONFIG = ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-1-config.json"
OLD_FIREWALL = ROOT / "docs/evaluation/full-coverage-v2-global-forbidden-targets-v1-2.json"
SPENT_V1_2 = ROOT / "docs/evaluation/full-coverage-v2-replacement-holdout-v1.json"
REFERENCE_CONFIG = ROOT / "docs/evaluation/competition-prior-poisson-v1-artifact.json"
LOCAL_AUDIT = ROOT / ".local/reports/canonical-history-audit.json"

AUDIT = ROOT / "docs/evidence/canonical-history-integrity-audit-v1-2026-10-09.json"
QUARANTINE = ROOT / "docs/evaluation/fixture-resolution-quarantine-manifest-v1.json"
FIREWALL = ROOT / "docs/evaluation/full-coverage-v2-global-forbidden-targets-v1-3.json"
TARGET_MANIFEST = ROOT / "docs/evaluation/full-coverage-v2-replacement-holdout-v2.json"
RESOLVED_HISTORY_MANIFEST = ROOT / "docs/evaluation/resolved-history-manifest-v1.json"
READINESS = ROOT / "docs/evidence/v2-preoutcome-readiness-rehearsal-v1-2026-10-09.json"
CONFIG = ROOT / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-3-config.json"
OWNER_DECISION = ROOT / (
    "docs/evidence/owner-decision-authorize-canonical-history-repair-v2-final-2026-10-09.json"
)
PREREGISTRATION = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-3-preregistration.json"
)
EXECUTION_STATE = ROOT / (
    "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-3-execution-state.json"
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
    _verify_v1_2_spent(root)
    audit = _json(root / LOCAL_AUDIT.relative_to(ROOT))
    if (
        audit.get("status") != "PASS"
        or cast(dict[str, int], audit["counts"])["unresolved_admitted_timeline_conflicts"]
    ):
        raise RuntimeError("CANONICAL_HISTORY_REPAIR_REQUIRED")
    resolution_manifest = cast(list[dict[str, object]], audit.pop("resolution_manifest"))
    audit["resolution_manifest_sha256"] = semantic_sha256(resolution_manifest)
    quarantine = {
        "contract": "MatchForgeFixtureResolutionQuarantineManifestV1",
        "resolution_version": RESOLUTION_VERSION,
        "entries": [row for row in resolution_manifest if row["resolution_status"] != "UNIQUE"],
    }
    quarantine["manifest_sha256"] = semantic_sha256(quarantine["entries"])

    firewall = _global_firewall(root)
    forbidden = frozenset(cast(list[str], firewall["unique_forbidden_target_ids"]))
    with psycopg.connect(database_url) as connection:
        metadata = load_persisted_resolved_metadata(connection)
    targets = _select_targets(metadata, forbidden)
    qualification = _qualify(targets, forbidden)
    if qualification["failures"]:
        raise RuntimeError(str(cast(list[str], qualification["failures"])[0]))
    relevant_history = _relevant_history_manifest(metadata, targets)
    resolved_history_sha = semantic_sha256(relevant_history)
    resolved_history = {
        "contract": "MatchForgeResolvedHistoryManifestV1",
        "resolution_version": RESOLUTION_VERSION,
        "protocol_id": PROTOCOL_ID,
        "resolved_history_manifest_sha256": resolved_history_sha,
        "rows": relevant_history,
    }
    target_sha = semantic_sha256(targets)
    target_manifest = {
        "contract": "MatchForgeReplacementHoldoutManifestV2",
        "manifest_id": REPLACEMENT_MANIFEST_ID,
        "protocol_id": PROTOCOL_ID,
        "selection_mode": "OUTCOME_BLIND_RESOLVED_METADATA_ONLY",
        "outcome_fields_read_for_selection": False,
        "research_cutoff": RESEARCH_CUTOFF.isoformat(),
        "global_firewall_sha256": semantic_sha256(firewall),
        "resolved_history_manifest_sha256": resolved_history_sha,
        "target_manifest_sha256": target_sha,
        "qualification": qualification,
        "targets": targets,
    }

    old_config = _json(root / OLD_CONFIG.relative_to(ROOT))
    candidate_shas = {
        key: value["artifact_sha256"]
        for key, value in cast(
            dict[str, dict[str, object]], old_config["candidate_artifacts"]
        ).items()
    }
    expected_v2b = {
        "matchforge-ensemble-v2b": (
            "d61625324300e310b8c1d8e7e2f4df86bb55f218e4b3735486dc391765f5387c"
        ),
        "pb-dixon-coles-transferable-v2b": (
            "62041a5c67c5673e173368986c1c9f9c3e57ac4f15ac4e1e7a6d292723ea3b27"
        ),
        "pb-negative-binomial-transferable-v2b": (
            "e5d87b998a80e03b2aae730c8b1782826aacf4a0fad1f7345d03b6a8a92e863b"
        ),
        "pb-weibull-copula-transferable-v2b": (
            "93c8fb0ae16bb166b4fb537280fc2ba9ea178f55cf58236aed6db57b261f2763"
        ),
    }
    if any(candidate_shas.get(key) != value for key, value in expected_v2b.items()):
        raise RuntimeError("FAIL_CLOSED_FROZEN_CANDIDATE_MISMATCH")
    reference = _json(root / REFERENCE_CONFIG.relative_to(ROOT))
    config = {
        "contract": "MatchForgeFullCoverageV2FinalConfigurationV1",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "frozen_v2_configuration_ref": OLD_CONFIG.relative_to(ROOT).as_posix(),
        "frozen_v2_configuration_file_sha256": _file_sha(root / OLD_CONFIG.relative_to(ROOT)),
        "frozen_v2_candidate_artifact_sha256": candidate_shas,
        "selected_cold_start": old_config["selected_cold_start"],
        "selected_transfer_weight": old_config["selected_transfer_weight"],
        "ensemble_status": "PREVIOUSLY_VALID_FROZEN_DEVELOPMENT",
        "ensemble_weights": old_config["ensemble_weights"],
        "reference_stack_id": REFERENCE_STACK_ID,
        "reference_artifact_ref": REFERENCE_CONFIG.relative_to(ROOT).as_posix(),
        "reference_artifact_sha256": reference["artifact_sha256"],
        "source_commit": source_commit,
    }
    decision = {
        "contract": "MatchForgeOwnerDecisionV1",
        "decision_id": AUTHORIZATION_ID,
        "authorized_at": f"{DATE}T00:00:00Z",
        "recorded_at": f"{DATE}T00:00:00Z",
        "protocol_id": PROTOCOL_ID,
        "parent_protocol_id": PARENT_PROTOCOL_ID,
        "amendment_reason": AMENDMENT_REASON,
        "authorized": [
            "canonical fixture integrity investigation",
            "real-fixture identity resolution",
            "duplicate-history repair",
            "ambiguous-history quarantine",
            "canonical ingestion hardening",
            "resolved-history abstraction",
            "fresh target discovery and qualification",
            "pre-outcome structural and model rehearsal",
            "one new development HOLDOUT execution",
            "evidence generation",
        ],
        "not_authorized": [
            "V2B retuning",
            "new hyperparameters or ensemble weights",
            "new feature families, H2H, or context features",
            "changing acceptance criteria",
            "production promotion",
            "reuse of consumed targets",
        ],
    }
    state = {
        "logical_executions": 0,
        "outcomes_loaded": False,
        "readiness_rehearsal": "PENDING",
        "canonical_history_audit": "PASS",
        "protocol_id": PROTOCOL_ID,
    }
    _write(root / AUDIT.relative_to(ROOT), audit)
    _write(root / QUARANTINE.relative_to(ROOT), quarantine)
    _write(root / FIREWALL.relative_to(ROOT), firewall)
    _write(root / TARGET_MANIFEST.relative_to(ROOT), target_manifest)
    _write(root / RESOLVED_HISTORY_MANIFEST.relative_to(ROOT), resolved_history)
    _write(root / CONFIG.relative_to(ROOT), config)
    _write(root / OWNER_DECISION.relative_to(ROOT), decision)
    _write(root / EXECUTION_STATE.relative_to(ROOT), state)
    _record_owner_decision(root)
    return target_manifest


def _select_targets(
    metadata: Sequence[Mapping[str, object]], forbidden: frozenset[str]
) -> list[dict[str, object]]:
    history: dict[str, list[tuple[datetime, str, int | None]]] = defaultdict(list)
    competition_history: dict[str, list[datetime]] = defaultdict(list)
    for row in metadata:
        kickoff = cast(datetime, row["kickoff_at"])
        competition_history[str(row["competition_id"])].append(kickoff)
        for field in ("home_team_id", "away_team_id"):
            history[str(row[field])].append(
                (kickoff, str(row["competition_id"]), cast(int | None, row["division"]))
            )
    for values in history.values():
        values.sort()
    for kickoffs in competition_history.values():
        kickoffs.sort()
    by_domain: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in metadata:
        kickoff = cast(datetime, row["kickoff_at"])
        members = [str(value) for value in cast(Sequence[str], row["member_fixture_ids"])]
        if not FIT_CUTOFF < kickoff < RESEARCH_CUTOFF or set(members) & forbidden:
            continue
        home_id, away_id = str(row["home_team_id"]), str(row["away_team_id"])
        home_history, away_history = history[home_id], history[away_id]
        home_count = bisect_left([item[0] for item in home_history], kickoff)
        away_count = bisect_left([item[0] for item in away_history], kickoff)
        competition_count = bisect_left(competition_history[str(row["competition_id"])], kickoff)
        if competition_count == 0:
            continue
        target = _selection_target(
            row,
            members,
            home_history,
            away_history,
            home_count,
            away_count,
            competition_count,
        )
        by_domain[str(row["competition_id"])][str(target["champion_eligibility"])].append(target)
    return _select_domain_strata(by_domain)


def _select_domain_strata(
    by_domain: Mapping[str, Mapping[str, Sequence[dict[str, object]]]],
) -> list[dict[str, object]]:
    eligible_domains = [
        competition_id
        for competition_id, strata in by_domain.items()
        if len(strata[ChampionEligibility.ELIGIBLE.value]) >= DOMAIN_ELIGIBLE_COUNT
        and len(strata[ChampionEligibility.INELIGIBLE.value]) >= DOMAIN_INELIGIBLE_COUNT
    ]
    if len(eligible_domains) < 3:
        raise RuntimeError("DEFER_INSUFFICIENT_FRESH_HOLDOUT")
    domains = sorted(
        eligible_domains,
        key=lambda key: (
            -sum(len(values) for values in by_domain[key].values()),
            key,
        ),
    )[:3]
    selected: list[dict[str, object]] = []
    for competition_id in domains:
        strata = by_domain[competition_id]
        for status, count in (
            (ChampionEligibility.ELIGIBLE.value, DOMAIN_ELIGIBLE_COUNT),
            (ChampionEligibility.INELIGIBLE.value, DOMAIN_INELIGIBLE_COUNT),
        ):
            ordered = sorted(
                strata[status], key=lambda item: (str(item["kickoff"]), str(item["fixture_id"]))
            )
            selected.extend(ordered[:count])
    return sorted(selected, key=lambda item: (str(item["kickoff"]), str(item["fixture_id"])))


def _selection_target(
    row: Mapping[str, object],
    members: list[str],
    home_history: Sequence[tuple[datetime, str, int | None]],
    away_history: Sequence[tuple[datetime, str, int | None]],
    home_count: int,
    away_count: int,
    competition_count: int,
) -> dict[str, object]:
    kickoff = cast(datetime, row["kickoff_at"])
    home_id, away_id = str(row["home_team_id"]), str(row["away_team_id"])
    eligibility = champion_eligibility(
        ChampionEligibilityInput(True, True, True, True, True, home_count, away_count)
    )
    reference = ReferenceStackV1().select(eligibility)
    season = _season(str(row["country"]), kickoff)
    return {
        "fixture_id": str(row["representative_fixture_id"]),
        "real_fixture_id": str(row["real_fixture_id"]),
        "member_fixture_ids": members,
        "kickoff": kickoff.astimezone(UTC).isoformat(),
        "competition_id": str(row["competition_id"]),
        "competition": str(row["competition_name"]),
        "country": str(row["country"]),
        "division": cast(int | None, row["division"]),
        "season": season,
        "home_team": home_id,
        "away_team": away_id,
        "home_team_name": str(row["home_team_name"]),
        "away_team_name": str(row["away_team_name"]),
        "home_prior_match_count": home_count,
        "away_prior_match_count": away_count,
        "competition_prior_match_count": competition_count,
        "champion_eligibility": eligibility.status.value,
        "champion_ineligibility_reason": eligibility.reason.value if eligibility.reason else None,
        "home_promotion_state": _promotion(home_history, season, cast(int | None, row["division"])),
        "away_promotion_state": _promotion(away_history, season, cast(int | None, row["division"])),
        "reference_model_id": reference.model_id,
        "reference_mode": reference.mode.value,
        "V2B_expected_route": "PENDING_REHEARSAL",
        "source_provider": str(row["source_provider_code"]),
        "representative_fixture_id": str(row["representative_fixture_id"]),
        "source_snapshot_id": str(row["source_snapshot_id"]),
        "identity_status": str(row["resolution_status"]),
        "source_evidence_sha256": str(row["evidence_sha256"]),
    }


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
    fixture_ids = [str(row["fixture_id"]) for row in targets]
    real_ids = [str(row["real_fixture_id"]) for row in targets]
    team_slots = Counter(
        (str(row[field]), str(row["kickoff"]))
        for row in targets
        for field in ("home_team", "away_team")
    )
    failures: list[str] = []
    if len(targets) < 500 or len(targets) != TARGET_COUNT:
        failures.append("DEFER_INSUFFICIENT_FRESH_HOLDOUT")
    if sum(value >= 100 for value in competitions.values()) < 3:
        failures.append("DEFER_INSUFFICIENT_FRESH_HOLDOUT")
    if competitions and max(competitions.values()) / len(targets) > 0.60:
        failures.append("DEFER_INSUFFICIENT_FRESH_HOLDOUT")
    if eligibility[ChampionEligibility.ELIGIBLE.value] < 200:
        failures.append("INSUFFICIENT_CHAMPION_ELIGIBLE_REPLACEMENT_SAMPLE")
    if eligibility[ChampionEligibility.INELIGIBLE.value] < 75:
        failures.append("DEFER_INSUFFICIENT_CHAMPION_INELIGIBLE_SAMPLE")
    if len(real_ids) != len(set(real_ids)):
        failures.append("FAIL_CLOSED_DUPLICATE_TARGET_REAL_FIXTURE")
    if any(value > 1 for value in team_slots.values()):
        failures.append("IMPOSSIBLE_TEAM_TIMELINE")
    if any(int(cast(int, row["competition_prior_match_count"])) < 1 for row in targets):
        failures.append("MODEL_READINESS_FAILURE")
    overlaps = sorted(set(fixture_ids) & forbidden)
    if overlaps:
        failures.append("FAIL_CLOSED_SPENT_OR_PROTECTED_INTERSECTION")
    return {
        "target_count": len(targets),
        "competition_counts": dict(sorted(competitions.items())),
        "season_counts": dict(sorted(seasons.items())),
        "champion_eligibility_counts": dict(sorted(eligibility.items())),
        "champion_ineligibility_reason_counts": dict(sorted(reasons.items())),
        "global_firewall_overlap": len(overlaps),
        "target_real_fixture_duplicates": len(real_ids) - len(set(real_ids)),
        "team_timestamp_target_conflicts": sum(value > 1 for value in team_slots.values()),
        "failures": failures,
    }


def _relevant_history_manifest(
    metadata: Sequence[Mapping[str, object]], targets: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    teams = {str(row[field]) for row in targets for field in ("home_team", "away_team")}
    competitions = {str(row["competition_id"]) for row in targets}
    target_real_ids = {str(row["real_fixture_id"]) for row in targets}
    maximum = max(datetime.fromisoformat(str(row["kickoff"])) for row in targets)
    return [
        {
            "real_fixture_id": str(row["real_fixture_id"]),
            "member_fixture_ids": list(cast(Sequence[str], row["member_fixture_ids"])),
            "representative_fixture_id": str(row["representative_fixture_id"]),
            "competition_id": str(row["competition_id"]),
            "kickoff": cast(datetime, row["kickoff_at"]).astimezone(UTC).isoformat(),
            "home_team_id": str(row["home_team_id"]),
            "away_team_id": str(row["away_team_id"]),
            "resolution_status": str(row["resolution_status"]),
            "source_evidence_sha256": str(row["evidence_sha256"]),
        }
        for row in metadata
        if str(row["real_fixture_id"]) not in target_real_ids
        and cast(datetime, row["kickoff_at"]) <= maximum
        and (
            str(row["competition_id"]) in competitions
            or str(row["home_team_id"]) in teams
            or str(row["away_team_id"]) in teams
        )
    ]


def _global_firewall(root: Path) -> dict[str, object]:
    previous = _json(root / OLD_FIREWALL.relative_to(ROOT))
    spent = _json(root / SPENT_V1_2.relative_to(ROOT))
    groups = list(cast(list[dict[str, object]], previous["groups"]))
    spent_ids = sorted(
        str(row["fixture_id"]) for row in cast(list[dict[str, object]], spent["targets"])
    )
    groups.append(
        {
            "group_id": "MATCHFORGE_FULL_COVERAGE_V2_REPLACEMENT_HOLDOUT_V1_ALL_TARGETS",
            "reason": "V1_2_PROTOCOL_OUTCOMES_LOADED_CORPUS_SPENT_AS_UNIT",
            "target_ids": spent_ids,
        }
    )
    unique = sorted(
        {str(value) for group in groups for value in cast(list[str], group["target_ids"])}
    )
    return {
        "contract": "MatchForgeSpentTargetManifestV1_3",
        "manifest_id": "MATCHFORGE_GLOBAL_FORBIDDEN_TARGETS_2026_10_09_V1_3",
        "generated_from_outcome_fields": False,
        "groups": groups,
        "unique_forbidden_target_count": len(unique),
        "unique_forbidden_target_ids": unique,
        "unique_forbidden_target_ids_sha256": semantic_sha256(unique),
    }


def scientific_source_files(root: Path) -> tuple[str, ...]:
    files = {
        path.relative_to(root).as_posix()
        for path in (root / "python/football/src/football/forecasting").rglob("*.py")
    }
    files.update(
        path.relative_to(root).as_posix()
        for path in (root / "python/football/src/football/history").rglob("*.py")
    )
    files.update(
        {
            "scripts/audit_canonical_history.py",
            "scripts/prepare_full_coverage_v2_final.py",
            "scripts/run_full_coverage_v2_final.py",
        }
    )
    return tuple(sorted(files))


def scientific_source_sha(root: Path, files: Sequence[str]) -> str:
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _verify_v1_2_spent(root: Path) -> None:
    state = _json(
        root / "docs/evaluation/full-coverage-challengers-v2-reevaluation-v1-2-execution-state.json"
    )
    result = _json(
        root / "docs/evidence/full-coverage-challengers-v2-reevaluation-v1-2-2026-10-09.json"
    )
    if not state.get("outcomes_loaded") or state.get("logical_executions") != 1:
        raise RuntimeError("V1.2 spent state changed")
    if result.get("final_disposition") != "FAIL_CLOSED_PROTOCOL_VIOLATION":
        raise RuntimeError("V1.2 disposition changed")


def _verify_clean_source(root: Path, source_commit: str) -> None:
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=root, text=True).strip()
    status = subprocess.check_output(("git", "status", "--porcelain"), cwd=root, text=True)
    if head != source_commit or status:
        raise RuntimeError("preparation requires clean SOURCE_COMMIT at HEAD")


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
