#!/usr/bin/env python3
"""Qualify the minimum firewall-safe H2H history extension."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

from football.contracts.source import canonical_json_bytes
from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ResearchObservationV2,
    ResearchRowV2,
    research_rows,
)
from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiRequestRecord,
    PitchApiSeasonAuditInput,
    PitchApiSeasonScope,
    validate_pitchapi_audit,
)
from football.validation.pitchapi_contingency import (
    PitchApiSnapshotIdentityV1,
    PitchApiSnapshotResourceIdentityV1,
)

from scripts.analyze_h2h_incremental_signal_design import analyze_frozen_h2h_coverage
from scripts.run_h2h_development_history_acquisition import (
    CURRENT_DEVELOPMENT_ROOT,
    PRIOR_SCOPES,
    V1_INVENTORY_SHA256,
    V1_STOP_PATH,
    _current_aliases,
    _firewall,
    _future_package,
    _history_row,
    _history_sort_key,
    _mapping_continuity,
    _qualification_failures,
    _resource_manifest_records,
    _reuse_manifest_resource,
    _reuse_resource,
)
from scripts.run_h2h_development_history_acquisition import (
    V1_PRIMARY as _V1_PRIMARY,
)
from scripts.run_pitchapi_multi_domain_development_acquisition import (
    NAMESPACE,
    SEASON_CAP_BYTES,
    SHOT_CAP_BYTES,
    GroupSpec,
    _progress,
    _publish_request_ledger,
    _publish_resource_manifest,
    _register_mappings,
    _schema_failure_count,
    _seal_read_only,
    _shot_semantics,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import (
    Client,
    Resource,
    SnapshotStop,
    Store,
    _inventory,
    _resource,
    _sha256_file,
    _shot_count,
)
from scripts.run_pitchapi_validation_pilot import (
    PilotStop,
    _dependency_lock_sha256,
    _git_sha,
    _read_env_secret,
    select_pilot_manifest,
)
from scripts.run_transferable_npxg_dixon_coles_v2_research import (
    _observation,
    load_development,
)

AUTHORIZATION_ID = "MATCHFORGE_FIREWALL_SAFE_H2H_HISTORY_EXTENSION_V1"
SNAPSHOT_NAME = "MATCHFORGE_H2H_DEVELOPMENT_HISTORY_QUALIFIED_V1"
CONFIG_PATH = Path(
    "docs/evaluation/matchforge-firewall-safe-h2h-history-extension-v1-configuration.json"
)
OUTPUT_ROOT = Path(".local/pitchapi-firewall-safe-h2h-history-extension-v1")
V3_ROOT = Path(".local/pitchapi-h2h-development-history-v3")
V3_RESULT_PATH = Path(
    "docs/evidence/matchforge-h2h-development-history-acquisition-v3-result-2026-09-28.json"
)
V3_REPORT_PATH = Path(
    "docs/evidence/matchforge-h2h-development-history-acquisition-v3-result-2026-09-28.md"
)
V3_CONFIG_PATH = Path(
    "docs/evaluation/matchforge-h2h-development-history-acquisition-v3-configuration.json"
)
V3_RESULT_SHA256 = "dfdcc133a482a7c51b738eaf9bfc5f983ed655578999567e2f99632610395b55"
V3_REPORT_SHA256 = "87ceaa4fa7fff3e1257380a545b921b0eb56d351168d6fcf088d9b9908984b61"
V3_CONFIG_SHA256 = "f81c68b8f44e3f692dc76129773876c176d56313eeb56d719a6c609a8237ef50"
V3_SNAPSHOT_ID = "d0da187c-88d0-5eb1-b08b-01bdaf097622"
V3_SNAPSHOT_SHA256 = "09280f173008cffd4a05f7b71859b0588814d552e7dea8b5846474bebbd5e308"
V3_BACKUP_INVENTORY_SHA256 = (
    "430ad4efd52bbd06551dea11547bef1a553d05f42cb67b901f31621dc43a12af"
)
LA_LIGA_2023_24_RAW_SHA256 = (
    "5ab215f10971e8479c06b8869d5118ec4fa98a7ed49cd7eb8333d8719c6dee34"
)
LA_LIGA_2023_24_NORMALIZED_SHA256 = (
    "de3f7dcd0d4cd868fb77138e576f2f98086d3bef7fce52fdb1054a492f552cc9"
)
ADAPTER_VERSION = "matchforge-firewall-safe-h2h-history-extension-adapter-v1"
TOKEN_NAME = "PITCH_API_TOKEN"
EXPECTED_TARGET_COUNT = 1_270
LA_LIGA_LEAGUE_ID = "l_0ErfuF"
XG_SERIES = "PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_V1_RAW_XG"
V1_PRIMARY = _V1_PRIMARY


def acquire(config_path: Path = CONFIG_PATH, root: Path = OUTPUT_ROOT) -> dict[str, object]:
    """Run the frozen capacity check, minimum acquisition, and qualification."""
    _verify_v3_preservation()
    config = _load_config(config_path)
    retained_manifest, retained_manifest_paths = _retained_la_liga_manifest()
    completeness, eligible_matches = _target_pair_completeness(retained_manifest, config)
    fixed_observations = load_development(CURRENT_DEVELOPMENT_ROOT)
    targets = research_rows(fixed_observations)
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise SnapshotStop("FIXED_TARGET_COUNT_MISMATCH")
    v3_result, v3_rows, v3_observations = _v3_history()
    aliases = _current_aliases()
    retained_capacity = _capacity_assessment(
        (*fixed_observations, *v3_observations),
        targets,
        eligible_matches,
        "la_liga_2023_24",
        aliases,
        {frozenset(("t_06N2GA", "t_1pKstK"))},
    )
    if cast(int, retained_capacity["safe_global_2_plus_gain"]) < 7:
        raise SnapshotStop("RETAINED_LA_LIGA_CAPACITY_BELOW_AUTHORIZED_MINIMUM")

    store = Store(root, hard_storage_bytes=_integer(config, "hard_storage_ceiling_bytes"))
    secret = _read_env_secret(Path(".env"), TOKEN_NAME)
    client = Client(
        secret,
        store,
        attempt_ceiling=_integer(config, "hard_request_ceiling"),
        retry_reserve=_integer(config, "retry_allowance"),
        wall_seconds=_integer(config, "wall_clock_ceiling_minutes") * 60,
    )
    del secret
    started_at = datetime.now(UTC)
    snapshot_id = uuid5(NAMESPACE, f"{AUTHORIZATION_ID}:{started_at.isoformat()}")
    resources = _reuse_v3_resources(store, v3_result)
    retained_resource = _reuse_resource(
        store,
        retained_manifest_paths[0],
        retained_manifest_paths[1],
        resource_ref="season:la_liga_2023_24",
        scope_key="la_liga_2023_24",
        kind="season_manifest",
        path=PitchApiSeasonScope(
            "la_liga_2023_24", LA_LIGA_LEAGUE_ID, "2023/2024", 380
        ).manifest_path,
        acquired_at=str(json.loads(V1_STOP_PATH.read_text())["started_at"]),
    )
    resources.append(retained_resource)
    try:
        candidate_payload, candidate_resource = _resource(
            store,
            client,
            scope_key="la_liga_2022_23",
            kind="season_manifest",
            resource_ref="candidate_season:la_liga_2022_23",
            path=PitchApiSeasonScope(
                "la_liga_2022_23", LA_LIGA_LEAGUE_ID, "2022/2023", 380
            ).manifest_path,
            cap=SEASON_CAP_BYTES,
        )
        resources.append(candidate_resource)
        older_candidate = _candidate_capacity_assessment(
            (*fixed_observations, *v3_observations), targets, candidate_payload, aliases
        )
        shots, shot_resources, lineage = _acquire_eligible_shots(
            store, client, eligible_matches
        )
        resources.extend(shot_resources)
        result = _complete(
            config,
            config_path,
            store,
            client,
            started_at,
            snapshot_id,
            resources,
            fixed_observations,
            targets,
            v3_result,
            v3_rows,
            v3_observations,
            eligible_matches,
            shots,
            lineage,
            retained_capacity,
            older_candidate,
            completeness,
        )
        _seal_read_only(store.primary)
        _seal_read_only(store.backup)
        return result
    except (PilotStop, SnapshotStop) as error:
        report = _stop_report(config, client, store, started_at, error.code)
        (root / "STOPPED.json").write_bytes(canonical_json_bytes(report) + b"\n")
        _seal_read_only(store.primary)
        return report


def _complete(
    config: Mapping[str, object],
    config_path: Path,
    store: Store,
    client: Client,
    started_at: datetime,
    snapshot_id: UUID,
    resources: list[Resource],
    fixed_observations: Sequence[ResearchObservationV2],
    targets: Sequence[ResearchRowV2],
    v3_result: Mapping[str, Any],
    v3_rows: list[dict[str, object]],
    v3_observations: Sequence[ResearchObservationV2],
    eligible_matches: Sequence[Mapping[str, object]],
    shots: Mapping[str, Mapping[str, Any]],
    lineage: Mapping[str, Mapping[str, str]],
    retained_capacity: Mapping[str, object],
    older_candidate: Mapping[str, object],
    completeness: Mapping[str, object],
) -> dict[str, object]:
    if client.state.attempts != config["expected_requests"]:
        raise SnapshotStop("REQUEST_LEDGER_MISMATCH")
    mappings = _v3_mappings(v3_result)
    _register_mappings(mappings, eligible_matches)
    continuity = _mapping_continuity(mappings, _current_aliases())
    aliases = {**_current_aliases(), **mappings}
    selection_payload = {
        "data": {
            "league": {"id": LA_LIGA_LEAGUE_ID, "name": "LaLiga", "season": "2023/2024"},
            "matches": list(eligible_matches),
        }
    }
    validation_scope = PitchApiSeasonScope(
        "la_liga_2023_24", LA_LIGA_LEAGUE_ID, "2023/2024", len(eligible_matches)
    )
    selection = select_pilot_manifest(
        selection_payload, validation_scope, full_expected_match_count=len(eligible_matches)
    )
    audit = _audit_selected_history(
        config, selection.payload, validation_scope, shots, client, started_at
    )
    report = audit.seasons[0]
    failures = _qualification_failures(report.to_dict(), len(eligible_matches))
    semantic = _shot_semantics(shots)
    if failures:
        raise SnapshotStop("LA_LIGA_2023_24_NPXG_QUALIFICATION_FAILED")

    added_observations: list[ResearchObservationV2] = []
    added_rows: list[dict[str, object]] = []
    group = GroupSpec("la_liga_2023_24", "La Liga", "ESP", "2023/2024", 378, 0)
    for match in eligible_matches:
        match_id = str(match["id"])
        observation = _observation(
            match, shots[match_id], group.scope_key, group.competition, aliases
        )
        added_observations.append(observation)
        added_rows.append(
            _history_row(match, observation, group, lineage[match_id], snapshot_id)
        )
    all_rows = [*v3_rows, *added_rows]
    all_rows.sort(key=_history_sort_key)
    coverage = analyze_frozen_h2h_coverage(
        (*fixed_observations, *v3_observations, *added_observations), targets, PRIOR_SCOPES
    )
    summaries = [
        *cast(list[Mapping[str, object]], v3_result["groups"]),
        {
            "scope_key": "la_liga_2023_24",
            "role": "DEVELOPMENT_HISTORY_ONLY",
            "competition": "La Liga",
            "season": "2023/2024",
            "league_id": LA_LIGA_LEAGUE_ID,
            "nominal_fixtures": 380,
            "provider_finished_fixtures": 379,
            "target_pair_complete_fixtures": len(eligible_matches),
            "mapped_fixtures": len(eligible_matches),
            "shots": report.shots,
            "valid_npxg_shots": (
                report.shots
                - report.invalid_xg
                - report.penalties
                - cast(int, semantic["own_goals"])
            ),
            "penalty_exclusions": report.penalties,
            "own_goal_exclusions": semantic["own_goals"],
            "shot_situations": semantic["situations"],
            "malformed_or_missing_resources": (
                _schema_failure_count(report.to_dict()) + report.missing_shot_resources
            ),
            "canonical_mapping_failures": 0,
            "qualification_failures": failures,
            "admitted": True,
            "resource_status": "REUSED_RETAINED_V1_MANIFEST_ACQUIRED_PAIR_COMPLETE_SHOTS",
        },
    ]
    firewall = _firewall(all_rows, targets, summaries)
    chronology = _chronology(all_rows, targets)
    classification = _classification(config, coverage, firewall, chronology, failures)
    if classification != "H2H_DEVELOPMENT_HISTORY_QUALIFIED":
        raise SnapshotStop("QUALIFICATION_GATE_FAILED")

    all_groups = (
        GroupSpec("premier_league_2023_24", "Premier League", "ENG", "2023/2024", 380, 0),
        GroupSpec("serie_a_2023_24", "Serie A", "ITA", "2023/2024", 380, 0),
        GroupSpec("premier_league_2022_23", "Premier League", "ENG", "2022/2023", 380, 0),
        GroupSpec("serie_a_2022_23", "Serie A", "ITA", "2022/2023", 380, 0),
        GroupSpec("la_liga_2023_24", "La Liga", "ESP", "2023/2024", 380, 0),
        GroupSpec("la_liga_2022_23", "La Liga", "ESP", "2022/2023", 380, 0),
    )
    scopes = {
        group.scope_key: PitchApiSeasonScope(
            group.scope_key, _league_id(group.competition), group.season, group.expected_matches
        )
        for group in all_groups
    }
    raw_manifest = _publish_resource_manifest(store, resources, all_groups, scopes, raw=True)
    normalized_manifest = _publish_resource_manifest(
        store, resources, all_groups, scopes, raw=False
    )
    mapping_manifest = _publish_mapping(store, mappings, continuity)
    history_manifest = store.publish_bytes(
        "manifests",
        canonical_json_bytes(
            {
                "contract": "MatchForgeH2HDevelopmentHistoryManifestQualifiedV1",
                "snapshot_id": str(snapshot_id),
                "role": "DEVELOPMENT_HISTORY_ONLY",
                "matches": all_rows,
            }
        ),
    )
    completeness_manifest = store.publish_bytes(
        "manifests", canonical_json_bytes(dict(completeness))
    )
    coverage_manifest = store.publish_bytes("manifests", canonical_json_bytes(coverage))
    firewall_manifest = store.publish_bytes("manifests", canonical_json_bytes(firewall))
    ledger = _publish_request_ledger(store, resources)
    package = cast(dict[str, object], _future_package(classification, coverage))
    package_manifest = store.publish_bytes("reports", canonical_json_bytes(package))
    snapshot = PitchApiSnapshotIdentityV1(
        snapshot_id=snapshot_id,
        acquired_at=started_at,
        resources=tuple(
            PitchApiSnapshotResourceIdentityV1(
                item.resource_ref, item.raw_sha256, item.normalized_sha256
            )
            for item in resources
        ),
        canonical_mapping_sha256=mapping_manifest[1],
        adapter_version=ADAPTER_VERSION,
        configuration_sha256=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        code_git_sha=_git_sha(),
    )
    snapshot_document = {
        **snapshot.to_dict(),
        "snapshot_name": SNAPSHOT_NAME,
        "role": "DEVELOPMENT_HISTORY_ONLY",
        "included_history_scopes": [
            summary["scope_key"] for summary in summaries if summary.get("admitted") is True
        ],
        "candidate_capacity_only_scopes": ["la_liga_2022_23"],
        "raw_resource_manifest": raw_manifest[0],
        "raw_resource_manifest_sha256": raw_manifest[1],
        "normalized_resource_manifest": normalized_manifest[0],
        "normalized_resource_manifest_sha256": normalized_manifest[1],
        "canonical_mapping_manifest": mapping_manifest[0],
        "canonical_mapping_manifest_sha256": mapping_manifest[1],
        "history_manifest": history_manifest[0],
        "history_manifest_sha256": history_manifest[1],
        "target_pair_completeness_manifest": completeness_manifest[0],
        "target_pair_completeness_manifest_sha256": completeness_manifest[1],
        "coverage_manifest": coverage_manifest[0],
        "coverage_manifest_sha256": coverage_manifest[1],
        "firewall_manifest": firewall_manifest[0],
        "firewall_manifest_sha256": firewall_manifest[1],
        "request_ledger": ledger[0],
        "request_ledger_sha256": ledger[1],
    }
    snapshot_path, snapshot_document_sha, _ = store.publish_bytes(
        "manifests", canonical_json_bytes(snapshot_document)
    )
    result: dict[str, object] = {
        "contract": "MatchForgeFirewallSafeH2HHistoryExtensionReportV1",
        "status": "COMPLETED",
        "classification": classification,
        "snapshot_name": SNAPSHOT_NAME,
        "snapshot_id": str(snapshot_id),
        "snapshot_sha256": snapshot.sha256,
        "snapshot_document": snapshot_path,
        "snapshot_document_sha256": snapshot_document_sha,
        "qualified_snapshot_created": True,
        "groups": summaries,
        "candidate_scopes": [retained_capacity, older_candidate],
        "target_pair_completeness": dict(completeness),
        "coverage": coverage,
        "firewall": firewall,
        "chronology": chronology,
        "canonical_mapping": continuity,
        "raw_resource_manifest_sha256": raw_manifest[1],
        "normalized_resource_manifest_sha256": normalized_manifest[1],
        "canonical_mapping_manifest_sha256": mapping_manifest[1],
        "history_manifest_sha256": history_manifest[1],
        "target_pair_completeness_manifest_sha256": completeness_manifest[1],
        "coverage_manifest_sha256": coverage_manifest[1],
        "firewall_manifest_sha256": firewall_manifest[1],
        "request_ledger_sha256": ledger[1],
        "expected_requests": config["expected_requests"],
        "actual_requests": client.state.attempts,
        "retries_used": client.state.retries,
        "hard_request_ceiling": config["hard_request_ceiling"],
        "v3_preservation": {
            "status": "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT",
            "snapshot_id": V3_SNAPSHOT_ID,
            "snapshot_sha256": V3_SNAPSHOT_SHA256,
            "mutated": False,
        },
        "model_fitting_performed": False,
        "model_evaluation_performed": False,
        "new_target_count": 0,
        "confirmation_data_acquired": False,
        "v6_created": False,
        "h2h_research_supportable": True,
        "future_research_package": {
            "research_id": "MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1",
            "path": package_manifest[0],
            "sha256": package_manifest[1],
            "status": "PREPARED_AWAITING_OWNER_AUTHORIZATION",
        },
        "next_owner_decision": "AUTHORIZE_OR_DECLINE_MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1",
    }
    store.publish_bytes("reports", canonical_json_bytes(result))
    backup_sha, total_bytes = store.seal_backup()
    result["backup_verification"] = "PASS"
    result["backup_inventory_sha256"] = backup_sha
    result["total_primary_and_backup_bytes"] = total_bytes
    (store.root / "RESULT.json").write_bytes(canonical_json_bytes(result) + b"\n")
    return result


def _load_config(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text())
    if (
        payload.get("contract")
        != "MatchForgeFirewallSafeH2HHistoryExtensionConfigurationV1"
        and "contract" in payload
    ):
        raise SnapshotStop("CONFIGURATION_CONTRACT_MISMATCH")
    expected = _integer(payload, "season_manifest_requests") + _integer(payload, "shot_requests")
    if expected != payload.get("expected_requests"):
        raise SnapshotStop("CONFIGURATION_REQUEST_BUDGET_MISMATCH")
    if expected + _integer(payload, "retry_allowance") > _integer(
        payload, "hard_request_ceiling"
    ):
        raise SnapshotStop("CONFIGURATION_REQUEST_CEILING_MISMATCH")
    if (
        payload.get("authorization") != AUTHORIZATION_ID
        or payload.get("base_url") != "https://api.pitchapi.dev"
        or payload.get("concurrency") != 1
        or payload.get("minimum_request_start_interval_seconds") != 1.0
        or payload.get("timeout_seconds") != 30
        or payload.get("task_hard_request_ceiling") != payload.get("hard_request_ceiling")
    ):
        raise SnapshotStop("CONFIGURATION_BOUNDARY_MISMATCH")
    candidates = payload.get("candidate_scopes")
    if not isinstance(candidates, list) or [item.get("scope_key") for item in candidates] != [
        "la_liga_2023_24",
        "la_liga_2022_23",
    ]:
        raise SnapshotStop("CONFIGURATION_SCOPE_MISMATCH")
    rule = payload.get("target_pair_history_completeness")
    if not isinstance(rule, Mapping) or rule.get("scope") != (
        "ALL_H2H_HISTORY_COMPETITIONS_AND_SCOPES"
    ):
        raise SnapshotStop("TARGET_PAIR_COMPLETENESS_RULE_MISSING")
    return cast(Mapping[str, object], payload)


def _retained_la_liga_manifest() -> tuple[Mapping[str, Any], tuple[Path, Path]]:
    inventory_sha = hashlib.sha256(canonical_json_bytes(_inventory(V1_PRIMARY))).hexdigest()
    stop = json.loads(V1_STOP_PATH.read_text())
    if (
        inventory_sha != V1_INVENTORY_SHA256
        or stop.get("stop_code") != "FULL_SEASON_MATCH_COUNT_MISMATCH"
        or stop.get("partial_primary", {}).get("inventory_sha256") != inventory_sha
    ):
        raise SnapshotStop("V1_RETAINED_EVIDENCE_MISMATCH")
    raw_path = (
        V1_PRIMARY
        / "raw"
        / "sha256"
        / LA_LIGA_2023_24_RAW_SHA256[:2]
        / f"{LA_LIGA_2023_24_RAW_SHA256}.json"
    )
    normalized_path = (
        V1_PRIMARY
        / "normalized"
        / "sha256"
        / LA_LIGA_2023_24_NORMALIZED_SHA256[:2]
        / f"{LA_LIGA_2023_24_NORMALIZED_SHA256}.json"
    )
    if (
        _sha256_file(raw_path) != LA_LIGA_2023_24_RAW_SHA256
        or _sha256_file(normalized_path) != LA_LIGA_2023_24_NORMALIZED_SHA256
    ):
        raise SnapshotStop("LA_LIGA_2023_24_MANIFEST_IDENTITY_MISMATCH")
    return cast(Mapping[str, Any], json.loads(normalized_path.read_text())), (
        raw_path,
        normalized_path,
    )


def _target_pair_completeness(
    payload: Mapping[str, Any], config: Mapping[str, object]
) -> tuple[dict[str, object], tuple[Mapping[str, object], ...]]:
    assessment = _candidate_manifest_assessment(payload, expected_team_count=20)
    expected = cast(
        Sequence[Mapping[str, object]],
        cast(Mapping[str, object], config["target_pair_history_completeness"])[
            "expected_missing_directed_fixtures"
        ],
    )
    expected_pairs = {
        (str(item["home_team_id"]), str(item["away_team_id"])) for item in expected
    }
    missing = cast(Sequence[Mapping[str, object]], assessment["missing_directed_fixtures"])
    observed_pairs = {
        (str(item["home_team_id"]), str(item["away_team_id"])) for item in missing
    }
    if observed_pairs != expected_pairs:
        raise SnapshotStop("TARGET_PAIR_COMPLETENESS_MISMATCH")
    matches = _finished_matches(payload)
    incomplete_pairs = {frozenset(pair) for pair in observed_pairs}
    eligible = tuple(
        match
        for match in matches
        if frozenset(
            (
                str(cast(Mapping[str, object], match["home_team"])["id"]),
                str(cast(Mapping[str, object], match["away_team"])["id"]),
            )
        )
        not in incomplete_pairs
    )
    quarantined = sorted(str(match["id"]) for match in matches if match not in eligible)
    return (
        {
            "contract": "MatchForgeTargetPairHistoryCompletenessV1",
            "rule": cast(Mapping[str, object], config["target_pair_history_completeness"]),
            "scope_key": "la_liga_2023_24",
            "status": "PASS_WITH_TARGET_PAIR_QUARANTINE",
            "provider_finished_fixtures": len(matches),
            "eligible_fixtures": len(eligible),
            "missing_directed_fixtures": list(missing),
            "quarantined_present_fixture_ids": quarantined,
            "affected_target_disposition": "H2H_HISTORY_INCOMPLETE",
        },
        eligible,
    )


def _candidate_manifest_assessment(
    payload: Mapping[str, Any], *, expected_team_count: int
) -> dict[str, object]:
    matches = _finished_matches(payload)
    teams: dict[str, str] = {}
    directed: set[tuple[str, str]] = set()
    for match in matches:
        home = cast(Mapping[str, object], match["home_team"])
        away = cast(Mapping[str, object], match["away_team"])
        home_id, away_id = str(home["id"]), str(away["id"])
        teams[home_id] = str(home.get("name", home_id))
        teams[away_id] = str(away.get("name", away_id))
        if home_id == away_id or (home_id, away_id) in directed:
            raise SnapshotStop("CANDIDATE_MANIFEST_STRUCTURE_INVALID")
        directed.add((home_id, away_id))
    if len(teams) != expected_team_count:
        raise SnapshotStop("CANDIDATE_MANIFEST_TEAM_COUNT_MISMATCH")
    missing = [
        {
            "home_team_id": home,
            "home_team_name": teams[home],
            "away_team_id": away,
            "away_team_name": teams[away],
        }
        for home in sorted(teams)
        for away in sorted(teams)
        if home != away and (home, away) not in directed
    ]
    return {
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "finished_fixtures": len(matches),
        "team_count": len(teams),
        "expected_directed_fixtures": len(teams) * (len(teams) - 1),
        "missing_directed_fixtures": missing,
    }


def _finished_matches(payload: Mapping[str, Any]) -> tuple[Mapping[str, object], ...]:
    data = payload.get("data")
    matches = data.get("matches") if isinstance(data, Mapping) else None
    if not isinstance(matches, list) or any(not isinstance(item, Mapping) for item in matches):
        raise SnapshotStop("CANDIDATE_MANIFEST_INVALID")
    if any(item.get("status") != "finished" for item in matches):
        raise SnapshotStop("CANDIDATE_MANIFEST_UNFINISHED")
    return tuple(cast(Sequence[Mapping[str, object]], matches))


def _capacity_assessment(
    base_observations: Sequence[ResearchObservationV2],
    targets: Sequence[ResearchRowV2],
    matches: Sequence[Mapping[str, object]],
    scope_key: str,
    aliases: Mapping[tuple[str, str], str],
    incomplete_provider_pairs: set[frozenset[str]],
) -> dict[str, object]:
    theoretical = tuple(_theoretical_observation(match, scope_key, aliases) for match in matches)
    configured_scopes = {**PRIOR_SCOPES, "la_liga_2024_25": scope_key}
    base = analyze_frozen_h2h_coverage(base_observations, targets, PRIOR_SCOPES)
    extended = analyze_frozen_h2h_coverage(
        (*base_observations, *theoretical), targets, configured_scopes
    )
    base_count = cast(int, cast(Mapping[str, Any], base["coverage"])["at_least_2"]["count"])
    extended_count = cast(
        int, cast(Mapping[str, Any], extended["coverage"])["at_least_2"]["count"]
    )
    base_three = cast(
        int, cast(Mapping[str, Any], base["coverage"])["at_least_3"]["count"]
    )
    extended_three = cast(
        int, cast(Mapping[str, Any], extended["coverage"])["at_least_3"]["count"]
    )
    la_liga = cast(
        Mapping[str, Mapping[str, int]], extended["coverage_by_competition"]
    )["La Liga"]
    affected = _affected_targets(targets, aliases, incomplete_provider_pairs)
    return {
        "scope_key": scope_key,
        "competition": "La Liga",
        "role": "DEVELOPMENT_HISTORY_ONLY",
        "theoretical_only": True,
        "base_global_2_plus": base_count,
        "safe_global_2_plus_gain": extended_count - base_count,
        "maximum_safe_global_2_plus": extended_count,
        "safe_global_3_plus_gain": extended_three - base_three,
        "maximum_safe_global_3_plus": extended_three,
        "la_liga_targets_with_2_plus": la_liga["at_least_2"],
        "la_liga_targets_with_3_plus": la_liga["at_least_3"],
        "affected_targets": affected,
        "can_close_seven_target_gap": extended_count - base_count >= 7,
    }


def _candidate_capacity_assessment(
    base_observations: Sequence[ResearchObservationV2],
    targets: Sequence[ResearchRowV2],
    payload: Mapping[str, Any],
    aliases: Mapping[tuple[str, str], str],
) -> dict[str, object]:
    manifest = _candidate_manifest_assessment(payload, expected_team_count=20)
    matches = _finished_matches(payload)
    missing = cast(Sequence[Mapping[str, object]], manifest["missing_directed_fixtures"])
    incomplete_pairs = {
        frozenset((str(item["home_team_id"]), str(item["away_team_id"])))
        for item in missing
    }
    eligible = tuple(
        match
        for match in matches
        if frozenset(
            (
                str(cast(Mapping[str, object], match["home_team"])["id"]),
                str(cast(Mapping[str, object], match["away_team"])["id"]),
            )
        )
        not in incomplete_pairs
    )
    capacity = _capacity_assessment(
        base_observations,
        targets,
        eligible,
        "la_liga_2022_23",
        aliases,
        incomplete_pairs,
    )
    return {
        **capacity,
        "manifest_assessment": manifest,
        "qualification_result": "CAPACITY_ONLY_NPXG_NOT_ACQUIRED_MINIMUM_ROUTE_ALREADY_SELECTED",
        "selected_for_full_acquisition": False,
    }


def _affected_targets(
    targets: Sequence[ResearchRowV2],
    aliases: Mapping[tuple[str, str], str],
    incomplete_provider_pairs: set[frozenset[str]],
) -> list[dict[str, object]]:
    incomplete_pairs = {
        frozenset(UUID(aliases[("team", provider_id)]) for provider_id in pair)
        for pair in incomplete_provider_pairs
    }
    inverse_matches = {
        canonical: provider
        for (kind, provider), canonical in aliases.items()
        if kind == "match"
    }
    return [
        {
            "canonical_target_id": str(target.match_id),
            "provider_target_id": inverse_matches.get(str(target.match_id)),
            "kickoff_at": target.kickoff_at.isoformat(),
            "classification": "H2H_HISTORY_INCOMPLETE",
        }
        for target in targets
        if target.competition == "La Liga"
        and frozenset((target.home_team_id, target.away_team_id)) in incomplete_pairs
    ]


def _theoretical_observation(
    match: Mapping[str, object],
    scope_key: str,
    aliases: Mapping[tuple[str, str], str],
) -> ResearchObservationV2:
    home = cast(Mapping[str, object], match["home_team"])
    away = cast(Mapping[str, object], match["away_team"])
    provider_match = str(match["id"])
    match_id = aliases.get(("match", provider_match)) or str(
        uuid5(NAMESPACE, f"pitchapi:match:{provider_match}")
    )
    return ResearchObservationV2(
        UUID(match_id),
        scope_key,
        "La Liga",
        datetime.fromisoformat(str(match["time_utc"]).replace("Z", "+00:00")),
        UUID(
            aliases.get(("team", str(home["id"])))
            or str(uuid5(NAMESPACE, f"pitchapi:team:{home['id']}"))
        ),
        UUID(
            aliases.get(("team", str(away["id"])))
            or str(uuid5(NAMESPACE, f"pitchapi:team:{away['id']}"))
        ),
        int(cast(int, match["score_home"])),
        int(cast(int, match["score_away"])),
        0.0,
        0.0,
    )


def _acquire_eligible_shots(
    store: Store,
    client: Client,
    matches: Sequence[Mapping[str, object]],
) -> tuple[dict[str, Mapping[str, Any]], list[Resource], dict[str, dict[str, str]]]:
    shots: dict[str, Mapping[str, Any]] = {}
    resources: list[Resource] = []
    lineage: dict[str, dict[str, str]] = {}
    for index, match in enumerate(matches, start=1):
        match_id = str(match["id"])
        payload, resource = _resource(
            store,
            client,
            scope_key="la_liga_2023_24",
            kind="match_shots",
            resource_ref=f"shots:la_liga_2023_24:{match_id}",
            path=f"/v1/matches/{match_id}/shots",
            cap=SHOT_CAP_BYTES,
        )
        _shot_count(payload, match_id)
        shots[match_id] = payload
        resources.append(resource)
        lineage[match_id] = {
            "resource_ref": resource.resource_ref,
            "raw_sha256": resource.raw_sha256,
            "normalized_sha256": resource.normalized_sha256,
            "source_manifest_inventory_sha256": V1_INVENTORY_SHA256,
            "target_pair_completeness": "PASS",
        }
        if index % 50 == 0 or index == len(matches):
            _progress("la_liga_2023_24", index, len(matches), client)
    return shots, resources, lineage


def _audit_selected_history(
    config: Mapping[str, object],
    selection_payload: Mapping[str, object],
    scope: PitchApiSeasonScope,
    shots: Mapping[str, Mapping[str, Any]],
    client: Client,
    started_at: datetime,
) -> Any:
    shot_paths = {f"/v1/matches/{match_id}/shots" for match_id in shots}
    records = (
        PitchApiRequestRecord(path=scope.manifest_path, status_code=200, request_id_present=True),
        *(record for record in client.records if record.path in shot_paths),
    )
    audit = PitchApiAuditInput(
        seasons=(PitchApiSeasonAuditInput(scope, selection_payload, shots),),
        request_log=records,
        budget=PitchApiRequestBudget(
            _integer(config, "validation_resource_requests")
            + _integer(config, "retry_allowance"),
            _integer(config, "retry_allowance"),
        ),
        metadata=PitchApiAuditMetadata(
            endpoint_version="v1",
            observed_provider_version=None,
            acquisition_started_at=started_at,
            acquisition_ended_at=datetime.now(UTC),
            code_git_sha=_git_sha(),
            dependency_lock_sha256=_dependency_lock_sha256(),
            credential_reference="env:PITCH_API_TOKEN",
        ),
        qualification_evidence=PitchApiQualificationEvidence(
            automated_private_research_permitted=True,
            immutable_raw_retention_permitted=True,
            attribution_requirements_recorded=True,
            correction_history_available=False,
            immutable_revision_identity_available=True,
            stable_identifier_policy_available=True,
            xg_series_by_scope={"la_liga_2023_24": XG_SERIES},
        ),
    )
    return validate_pitchapi_audit(audit)


def _v3_history() -> tuple[
    Mapping[str, Any], list[dict[str, object]], tuple[ResearchObservationV2, ...]
]:
    result = cast(Mapping[str, Any], json.loads((V3_ROOT / "RESULT.json").read_text()))
    digest = str(result["history_manifest_sha256"])
    path = V3_ROOT / "primary" / "manifests" / "sha256" / digest[:2] / f"{digest}.json"
    if _sha256_file(path) != digest:
        raise SnapshotStop("V3_HISTORY_MANIFEST_MISMATCH")
    payload = json.loads(path.read_text())
    rows = cast(list[dict[str, object]], payload["matches"])
    observations = tuple(_row_observation(row) for row in rows)
    return result, rows, observations


def _row_observation(row: Mapping[str, object]) -> ResearchObservationV2:
    return ResearchObservationV2(
        UUID(str(row["canonical_fixture_id"])),
        str(row["scope_key"]),
        str(row["competition"]),
        datetime.fromisoformat(str(row["kickoff_at"])),
        UUID(str(row["home_team_id"])),
        UUID(str(row["away_team_id"])),
        cast(int, row["home_goals"]),
        cast(int, row["away_goals"]),
        cast(float, row["home_npxg"]),
        cast(float, row["away_npxg"]),
    )


def _reuse_v3_resources(store: Store, result: Mapping[str, Any]) -> list[Resource]:
    primary = V3_ROOT / "primary"
    backup = V3_ROOT / "backup"
    primary_inventory = _inventory(primary)
    if (
        primary_inventory != _inventory(backup)
        or hashlib.sha256(canonical_json_bytes(primary_inventory)).hexdigest()
        != V3_BACKUP_INVENTORY_SHA256
    ):
        raise SnapshotStop("V3_BACKUP_INVENTORY_MISMATCH")
    raw = _resource_manifest_records(primary, str(result["raw_resource_manifest_sha256"]))
    normalized = _resource_manifest_records(
        primary, str(result["normalized_resource_manifest_sha256"])
    )
    raw_by_ref = {str(item["resource_ref"]): item for item in raw}
    normalized_by_ref = {str(item["resource_ref"]): item for item in normalized}
    if raw_by_ref.keys() != normalized_by_ref.keys():
        raise SnapshotStop("V3_RESOURCE_MANIFEST_MISMATCH")
    return [
        _reuse_manifest_resource(store, primary, raw_by_ref[key], normalized_by_ref[key])
        for key in sorted(raw_by_ref)
    ]


def _v3_mappings(result: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    digest = str(result["canonical_mapping_manifest_sha256"])
    path = V3_ROOT / "primary" / "manifests" / "sha256" / digest[:2] / f"{digest}.json"
    if _sha256_file(path) != digest:
        raise SnapshotStop("V3_MAPPING_MANIFEST_MISMATCH")
    payload = json.loads(path.read_text())
    return {
        (str(item["entity_type"]), str(item["provider_entity_id"])): str(item["canonical_id"])
        for item in payload["mappings"]
    }


def _publish_mapping(
    store: Store,
    mappings: Mapping[tuple[str, str], str],
    continuity: Mapping[str, object],
) -> tuple[str, str, int]:
    return cast(
        tuple[str, str, int],
        store.publish_bytes(
            "manifests",
            canonical_json_bytes(
                {
                    "contract": (
                        "MatchForgeH2HDevelopmentHistoryCanonicalMappingManifestQualifiedV1"
                    ),
                    "algorithm": "matchforge-explicit-uuid5-initial-allocation-v1",
                    "role": "DEVELOPMENT_HISTORY_ONLY",
                    "continuity": continuity,
                    "mappings": [
                        {
                            "entity_type": kind,
                            "provider_entity_id": provider_id,
                            "canonical_id": canonical,
                            "mapping_action": "reused_or_initial",
                        }
                        for (kind, provider_id), canonical in sorted(mappings.items())
                    ],
                }
            ),
        ),
    )


def _chronology(
    history_rows: Sequence[Mapping[str, object]], targets: Sequence[ResearchRowV2]
) -> dict[str, object]:
    target_by_pair: dict[frozenset[str], list[datetime]] = {}
    for target in targets:
        target_by_pair.setdefault(
            frozenset((str(target.home_team_id), str(target.away_team_id))), []
        ).append(target.kickoff_at)
    future_only_rows = 0
    for row in history_rows:
        pair = frozenset((str(row["home_team_id"]), str(row["away_team_id"])))
        target_times = target_by_pair.get(pair, [])
        kickoff = datetime.fromisoformat(str(row["kickoff_at"]))
        if target_times and not any(kickoff < target for target in target_times):
            future_only_rows += 1
    return {
        "status": "PASS" if future_only_rows == 0 else "FAIL",
        "strict_prior_rule": "history_kickoff_at < target_kickoff_at",
        "same_kickoff_sealed": True,
        "history_rows_without_any_later_matching_target": future_only_rows,
    }


def _classification(
    config: Mapping[str, object],
    coverage: Mapping[str, object],
    firewall: Mapping[str, object],
    chronology: Mapping[str, object],
    failures: Sequence[str],
) -> str:
    required = cast(Mapping[str, int], config["required_coverage"])
    cumulative = cast(Mapping[str, Mapping[str, int]], coverage["coverage"])
    competitions = cast(Mapping[str, Mapping[str, int]], coverage["coverage_by_competition"])
    passing_domains = sum(
        values["at_least_2"] >= 150 for values in competitions.values()
    )
    qualified = (
        cumulative["at_least_2"]["count"]
        >= required["minimum_targets_with_two_prior_meetings"]
        and cumulative["at_least_3"]["count"]
        >= required["minimum_targets_with_three_prior_meetings"]
        and passing_domains
        >= required["minimum_competitions_with_150_two_meeting_targets"]
        and firewall["status"] == "PASS"
        and chronology["status"] == "PASS"
        and not failures
    )
    return (
        "H2H_DEVELOPMENT_HISTORY_QUALIFIED"
        if qualified
        else "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"
    )


def _league_id(competition: str) -> str:
    return {
        "Premier League": "l_4WFCIZ",
        "Serie A": "l_0ALvwF",
        "La Liga": LA_LIGA_LEAGUE_ID,
    }[competition]


def _verify_v3_preservation() -> None:
    expected = {
        V3_RESULT_PATH: V3_RESULT_SHA256,
        V3_REPORT_PATH: V3_REPORT_SHA256,
        V3_CONFIG_PATH: V3_CONFIG_SHA256,
    }
    if any(_sha256_file(path) != digest for path, digest in expected.items()):
        raise SnapshotStop("V3_EVIDENCE_MUTATED")
    result = json.loads((V3_ROOT / "RESULT.json").read_text())
    if (
        result.get("classification") != "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"
        or result.get("snapshot_id") != V3_SNAPSHOT_ID
        or result.get("snapshot_sha256") != V3_SNAPSHOT_SHA256
        or result.get("backup_inventory_sha256") != V3_BACKUP_INVENTORY_SHA256
    ):
        raise SnapshotStop("V3_INTERMEDIATE_SNAPSHOT_MISMATCH")


def _stop_report(
    config: Mapping[str, object],
    client: Client,
    store: Store,
    started_at: datetime,
    code: str,
) -> dict[str, object]:
    return {
        "contract": "MatchForgeFirewallSafeH2HHistoryExtensionStopV1",
        "status": "STOPPED",
        "classification": "ACQUISITION_FAILED",
        "stop_code": code,
        "started_at": started_at.isoformat(),
        "stopped_at": datetime.now(UTC).isoformat(),
        "actual_requests": client.state.attempts,
        "retries_used": client.state.retries,
        "expected_requests": config["expected_requests"],
        "hard_request_ceiling": config["hard_request_ceiling"],
        "primary_bytes": store.primary_bytes,
        "qualified_snapshot_created": False,
        "owner_review_required": True,
        "model_fitting_performed": False,
        "model_evaluation_performed": False,
        "confirmation_data_acquired": False,
        "v6_created": False,
    }


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotStop("CONFIGURATION_INTEGER_MISMATCH")
    return value


def main() -> int:
    try:
        result = acquire()
    except (PilotStop, SnapshotStop) as error:
        print(json.dumps({"status": "STOPPED", "stop_code": error.code}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result.get("status") == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
