#!/usr/bin/env python3
"""Acquire H2H development history and requalify fixed-target coverage only."""

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
    research_rows,
)
from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiSeasonAuditInput,
    validate_pitchapi_audit,
)
from football.validation.pitchapi_contingency import (
    PitchApiSnapshotIdentityV1,
    PitchApiSnapshotResourceIdentityV1,
)

from scripts.analyze_h2h_incremental_signal_design import analyze_frozen_h2h_coverage
from scripts.run_pitchapi_multi_domain_development_acquisition import (
    CATALOG_CAP_BYTES,
    CATALOG_PATH,
    NAMESPACE,
    SEASON_CAP_BYTES,
    SHOT_CAP_BYTES,
    GroupSpec,
    _name_key,
    _prior_spent_pitchapi,
    _progress,
    _publish_request_ledger,
    _publish_resource_manifest,
    _register_mappings,
    _resolve_scopes,
    _schema_failure_count,
    _seal_read_only,
    _select_valid_manifest,
    _semantic_failure_count,
    _shot_semantics,
    _statsbomb_protected_ids,
    _v5_evaluation_scopes,
    _v5_target_ids,
)
from scripts.run_pitchapi_snapshot_v1_acquisition import (
    Client,
    Resource,
    SnapshotStop,
    Store,
    _resource,
    _shot_count,
)
from scripts.run_pitchapi_validation_pilot import (
    PilotStop,
    _dependency_lock_sha256,
    _git_sha,
    _read_env_secret,
)
from scripts.run_transferable_npxg_dixon_coles_v2_research import (
    MAPPING_SHA256,
    _observation,
    load_development,
)

ACQUISITION_ID = "MATCHFORGE_H2H_DEVELOPMENT_HISTORY_ACQUISITION_V1"
CONFIG_PATH = Path(
    "docs/evaluation/matchforge-h2h-development-history-acquisition-v1-configuration.json"
)
OUTPUT_ROOT = Path(".local/pitchapi-h2h-development-history-v1")
CURRENT_DEVELOPMENT_ROOT = Path(".local/pitchapi-multi-domain-development-v1-r3/primary")
TOKEN_NAME = "PITCH_API_TOKEN"
ADAPTER_VERSION = "matchforge-h2h-development-history-adapter-v1"
XG_SERIES = "PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_V1_RAW_XG"
EXPECTED_TARGET_COUNT = 1_270
PRIOR_SCOPES = {
    "bundesliga_2025_26": "bundesliga_2024_25",
    "premier_league_2024_25": "premier_league_2023_24",
    "la_liga_2024_25": "la_liga_2023_24",
    "serie_a_2024_25": "serie_a_2023_24",
}
CURRENT_MAPPING_PATH = (
    CURRENT_DEVELOPMENT_ROOT
    / "manifests"
    / "sha256"
    / MAPPING_SHA256[:2]
    / f"{MAPPING_SHA256}.json"
)


def acquire(config_path: Path = CONFIG_PATH, root: Path = OUTPUT_ROOT) -> dict[str, object]:
    config = _load_config(config_path)
    groups = _groups(config)
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
    snapshot_id = uuid5(NAMESPACE, f"{ACQUISITION_ID}:{started_at.isoformat()}")
    resources: list[Resource] = []
    try:
        catalog, catalog_resource = _resource(
            store,
            client,
            scope_key="authorized_catalog",
            kind="league_catalog",
            resource_ref="catalog:h2h-history-scope-resolution",
            path=CATALOG_PATH,
            cap=CATALOG_CAP_BYTES,
        )
        resources.append(catalog_resource)
        scopes = _resolve_scopes(catalog, groups)
        result = _acquire_groups(
            config,
            groups,
            scopes,
            snapshot_id,
            store,
            client,
            started_at,
            resources,
            config_path,
        )
        _seal_read_only(store.primary)
        _seal_read_only(store.backup)
        return result
    except (PilotStop, SnapshotStop) as error:
        report = _stop_report(config, client, store, started_at, error.code)
        (root / "STOPPED.json").write_bytes(canonical_json_bytes(report) + b"\n")
        _seal_read_only(store.primary)
        return report
    except (KeyError, TypeError, ValueError):
        report = _stop_report(config, client, store, started_at, "ACQUISITION_VALIDATION_FAILED")
        (root / "STOPPED.json").write_bytes(canonical_json_bytes(report) + b"\n")
        _seal_read_only(store.primary)
        return report


def _acquire_groups(
    config: Mapping[str, object],
    groups: tuple[GroupSpec, ...],
    scopes: Mapping[str, Any],
    snapshot_id: UUID,
    store: Store,
    client: Client,
    started_at: datetime,
    resources: list[Resource],
    config_path: Path,
) -> dict[str, object]:
    season_inputs: list[PitchApiSeasonAuditInput] = []
    group_inputs: list[dict[str, object]] = []
    mappings: dict[tuple[str, str], str] = {}
    for group in groups:
        scope = scopes[group.scope_key]
        manifest, manifest_resource = _resource(
            store,
            client,
            scope_key=group.scope_key,
            kind="season_manifest",
            resource_ref=f"season:{group.scope_key}",
            path=scope.manifest_path,
            cap=SEASON_CAP_BYTES,
        )
        resources.append(manifest_resource)
        selection, status_exclusions, validation_scope = _select_valid_manifest(
            manifest, scope, group.expected_matches
        )
        _register_mappings(mappings, selection.ordered_matches)
        shots: dict[str, Mapping[str, Any]] = {}
        lineage: dict[str, dict[str, str]] = {}
        for index, match in enumerate(selection.ordered_matches, start=1):
            match_id = str(match["id"])
            payload, resource = _resource(
                store,
                client,
                scope_key=group.scope_key,
                kind="match_shots",
                resource_ref=f"shots:{group.scope_key}:{match_id}",
                path=f"/v1/matches/{match_id}/shots",
                cap=SHOT_CAP_BYTES,
            )
            _shot_count(payload, match_id)
            resources.append(resource)
            shots[match_id] = payload
            lineage[match_id] = {
                "resource_ref": resource.resource_ref,
                "raw_sha256": resource.raw_sha256,
                "normalized_sha256": resource.normalized_sha256,
            }
            if index % 50 == 0 or index == len(selection.ordered_matches):
                _progress(group.scope_key, index, len(selection.ordered_matches), client)
        season_inputs.append(PitchApiSeasonAuditInput(validation_scope, selection.payload, shots))
        group_inputs.append(
            {
                "group": group,
                "matches": selection.ordered_matches,
                "shots": shots,
                "lineage": lineage,
                "status_exclusions": status_exclusions,
            }
        )

    base_requests = (
        1 + len(groups) + sum(len(cast(Sequence[object], item["matches"])) for item in group_inputs)
    )
    if client.state.attempts - client.state.retries != base_requests:
        raise SnapshotStop("REQUEST_LEDGER_MISMATCH")
    audit = _audit(config, groups, season_inputs, client, started_at, base_requests)
    reports = {report.scope_key: report for report in audit.seasons}
    current_aliases = _current_aliases()
    continuity = _mapping_continuity(mappings, current_aliases)
    aliases = {**current_aliases, **mappings}
    history_observations: list[ResearchObservationV2] = []
    summaries: list[dict[str, object]] = []
    history_rows: list[dict[str, object]] = []
    for item in group_inputs:
        group = cast(GroupSpec, item["group"])
        matches = cast(Sequence[Mapping[str, object]], item["matches"])
        group_shots = cast(Mapping[str, Mapping[str, Any]], item["shots"])
        group_lineage = cast(Mapping[str, Mapping[str, str]], item["lineage"])
        report = reports[group.scope_key]
        semantic = _shot_semantics(group_shots)
        failures = _qualification_failures(report.to_dict(), len(matches))
        for match in matches:
            match_id = str(match["id"])
            observation = _observation(
                match, group_shots[match_id], group.scope_key, group.competition, aliases
            )
            history_observations.append(observation)
            history_rows.append(
                _history_row(match, observation, group, group_lineage[match_id], snapshot_id)
            )
        summaries.append(
            {
                "scope_key": group.scope_key,
                "role": "DEVELOPMENT_HISTORY_ONLY",
                "competition": group.competition,
                "season": group.season,
                "league_id": scopes[group.scope_key].league_id,
                "nominal_fixtures": group.expected_matches,
                "finished_fixtures": len(matches),
                "mapped_fixtures": len(matches),
                "fixture_status_exclusions": dict(
                    sorted(cast(Mapping[str, int], item["status_exclusions"]).items())
                ),
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
                "admitted": not failures,
            }
        )

    fixed_observations = load_development(CURRENT_DEVELOPMENT_ROOT)
    targets = research_rows(fixed_observations)
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise SnapshotStop("FIXED_TARGET_COUNT_MISMATCH")
    coverage = analyze_frozen_h2h_coverage(
        (*fixed_observations, *history_observations), targets, PRIOR_SCOPES
    )
    firewall = _firewall(history_rows, targets, summaries)
    classification = _classification(summaries, coverage, firewall)

    mapping_manifest = _publish_mapping(store, mappings, continuity)
    raw_manifest = _publish_resource_manifest(store, resources, groups, scopes, raw=True)
    normalized_manifest = _publish_resource_manifest(store, resources, groups, scopes, raw=False)
    history_rows.sort(key=_history_sort_key)
    history_manifest = store.publish_bytes(
        "manifests",
        canonical_json_bytes(
            {
                "contract": "MatchForgeH2HDevelopmentHistoryManifestV1",
                "snapshot_id": str(snapshot_id),
                "role": "DEVELOPMENT_HISTORY_ONLY",
                "matches": history_rows,
            }
        ),
    )
    coverage_manifest = store.publish_bytes("manifests", canonical_json_bytes(coverage))
    firewall_manifest = store.publish_bytes("manifests", canonical_json_bytes(firewall))
    ledger = _publish_request_ledger(store, resources)
    package = _future_package(classification, coverage)
    package_manifest = (
        store.publish_bytes("reports", canonical_json_bytes(package))
        if package is not None
        else None
    )
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
        "role": "DEVELOPMENT_HISTORY_ONLY",
        "raw_resource_manifest": raw_manifest[0],
        "raw_resource_manifest_sha256": raw_manifest[1],
        "normalized_resource_manifest": normalized_manifest[0],
        "normalized_resource_manifest_sha256": normalized_manifest[1],
        "canonical_mapping_manifest": mapping_manifest[0],
        "history_manifest": history_manifest[0],
        "history_manifest_sha256": history_manifest[1],
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
        "contract": "MatchForgeH2HDevelopmentHistoryAcquisitionReportV1",
        "status": "COMPLETED",
        "classification": classification,
        "snapshot_id": str(snapshot_id),
        "snapshot_sha256": snapshot.sha256,
        "snapshot_document": snapshot_path,
        "snapshot_document_sha256": snapshot_document_sha,
        "raw_resource_manifest_sha256": raw_manifest[1],
        "normalized_resource_manifest_sha256": normalized_manifest[1],
        "canonical_mapping_manifest_sha256": mapping_manifest[1],
        "history_manifest_sha256": history_manifest[1],
        "coverage_manifest_sha256": coverage_manifest[1],
        "firewall_manifest_sha256": firewall_manifest[1],
        "request_ledger_sha256": ledger[1],
        "groups": summaries,
        "coverage": coverage,
        "firewall": firewall,
        "canonical_mapping": continuity,
        "expected_requests": config["expected_requests"],
        "actual_requests": client.state.attempts,
        "retries_used": client.state.retries,
        "hard_request_ceiling": config["hard_request_ceiling"],
        "model_fitting_performed": False,
        "model_evaluation_performed": False,
        "new_target_count": 0,
        "confirmation_data_acquired": False,
        "v6_created": False,
        "future_research_package": (
            {
                "research_id": "MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1",
                "path": package_manifest[0],
                "sha256": package_manifest[1],
                "status": "PREPARED_AWAITING_OWNER_AUTHORIZATION",
            }
            if package_manifest is not None
            else None
        ),
    }
    store.publish_bytes("reports", canonical_json_bytes(result))
    backup_sha, total_bytes = store.seal_backup()
    result["backup_verification"] = "PASS"
    result["backup_inventory_sha256"] = backup_sha
    result["total_primary_and_backup_bytes"] = total_bytes
    (store.root / "RESULT.json").write_bytes(canonical_json_bytes(result) + b"\n")
    return result


def _audit(
    config: Mapping[str, object],
    groups: tuple[GroupSpec, ...],
    seasons: list[PitchApiSeasonAuditInput],
    client: Client,
    started_at: datetime,
    base_requests: int,
) -> Any:
    audit = PitchApiAuditInput(
        seasons=tuple(seasons),
        request_log=tuple(record for record in client.records if record.path != CATALOG_PATH),
        budget=PitchApiRequestBudget(
            base_requests - 1 + _integer(config, "retry_allowance"),
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
            xg_series_by_scope={group.scope_key: XG_SERIES for group in groups},
        ),
    )
    return validate_pitchapi_audit(audit)


def _history_row(
    match: Mapping[str, object],
    observation: ResearchObservationV2,
    group: GroupSpec,
    lineage: Mapping[str, str],
    snapshot_id: UUID,
) -> dict[str, object]:
    return {
        "canonical_fixture_id": str(observation.match_id),
        "provider_fixture_id": str(match["id"]),
        "scope_key": group.scope_key,
        "competition": group.competition,
        "season": group.season,
        "role": "DEVELOPMENT_HISTORY_ONLY",
        "kickoff_at": observation.kickoff_at.isoformat(),
        "home_team_id": str(observation.home_team_id),
        "away_team_id": str(observation.away_team_id),
        "home_goals": observation.home_goals,
        "away_goals": observation.away_goals,
        "home_npxg": observation.home_npxg,
        "away_npxg": observation.away_npxg,
        "source_snapshot_id": str(snapshot_id),
        "source_resource_lineage": dict(lineage),
    }


def _history_sort_key(row: dict[str, object]) -> tuple[str, str]:
    return str(row["kickoff_at"]), str(row["canonical_fixture_id"])


def _current_aliases() -> dict[tuple[str, str], str]:
    if hashlib.sha256(CURRENT_MAPPING_PATH.read_bytes()).hexdigest() != MAPPING_SHA256:
        raise SnapshotStop("CURRENT_MAPPING_HASH_MISMATCH")
    payload = json.loads(CURRENT_MAPPING_PATH.read_text())
    return {
        (str(item["entity_type"]), str(item["provider_entity_id"])): str(item["canonical_id"])
        for item in payload["mappings"]
    }


def _mapping_continuity(
    mappings: Mapping[tuple[str, str], str], current: Mapping[tuple[str, str], str]
) -> dict[str, object]:
    overlaps = {key for key in mappings if key in current}
    mismatches = {key for key in overlaps if mappings[key] != current[key]}
    if mismatches:
        raise SnapshotStop("CANONICAL_MAPPING_CONTINUITY_FAILURE")
    return {
        "status": "PASS",
        "fixture_aliases": sum(kind == "match" for kind, _ in mappings),
        "team_aliases": sum(kind == "team" for kind, _ in mappings),
        "existing_aliases_reused": len(overlaps),
        "existing_team_aliases_reused": sum(kind == "team" for kind, _ in overlaps),
        "ambiguous_admitted_identities": 0,
        "mapping_failures": 0,
    }


def _publish_mapping(
    store: Store,
    mappings: Mapping[tuple[str, str], str],
    continuity: Mapping[str, object],
) -> tuple[str, str, int]:
    return store.publish_bytes(
        "manifests",
        canonical_json_bytes(
            {
                "contract": "MatchForgeH2HDevelopmentHistoryCanonicalMappingManifestV1",
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
    )


def _qualification_failures(report: Mapping[str, object], finished: int) -> list[str]:
    failures: list[str] = []
    if report["observed_matches"] != finished:
        failures.append("MATCH_COUNT")
    if _schema_failure_count(report):
        failures.append("SCHEMA")
    if _semantic_failure_count(report):
        failures.append("SEMANTICS")
    if report["missing_shot_resources"]:
        failures.append("MISSING_RESOURCES")
    return failures


def _firewall(
    history_rows: Sequence[Mapping[str, object]],
    targets: Sequence[Any],
    summaries: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    history_ids = {str(row["canonical_fixture_id"]) for row in history_rows}
    fixed_target_ids = {str(row.match_id) for row in targets}
    v5_ids = _v5_target_ids()
    spent_ids, spent_scopes = _prior_spent_pitchapi()
    statsbomb_ids = _statsbomb_protected_ids()
    scopes = {(_name_key(row["competition"]), str(row["season"])) for row in summaries}
    v5_scopes = _v5_evaluation_scopes()
    statsbomb_scopes = {
        (_name_key(competition), season)
        for competition, season in (
            ("Premier League", "2015/2016"),
            ("Serie A", "2015/2016"),
            ("Bundesliga", "2023/2024"),
            ("Ligue 1", "2022/2023"),
        )
    }
    intersections = {
        "fixed_development_targets": len(history_ids & fixed_target_ids),
        "v5_spent_targets": len(history_ids & v5_ids),
        "prior_spent_pitchapi_fixtures": len(history_ids & spent_ids),
        "statsbomb_protected_fixtures": len(history_ids & statsbomb_ids),
        "v5_protected_scopes": len(scopes & v5_scopes),
        "prior_spent_pitchapi_scopes": len(scopes & spent_scopes),
        "statsbomb_protected_scopes": len(scopes & statsbomb_scopes),
    }
    return {
        "contract": "MatchForgeH2HDevelopmentHistoryFirewallV1",
        "status": "PASS" if not any(intersections.values()) else "FAIL",
        "intersections": intersections,
        "history_role": "DEVELOPMENT_HISTORY_ONLY",
        "new_target_count": 0,
        "future_confirmation_reservation_status": "NO_GROUPS_FROZEN_NO_REUSE",
        "strict_prior_kickoff": True,
        "same_kickoff_sealed": True,
    }


def _classification(
    summaries: Sequence[Mapping[str, object]],
    coverage: Mapping[str, object],
    firewall: Mapping[str, object],
) -> str:
    if firewall["status"] != "PASS" or any(
        cast(Sequence[object], summary["qualification_failures"]) for summary in summaries
    ):
        return "ACQUISITION_FAILED"
    cumulative = cast(Mapping[str, Mapping[str, object]], coverage["coverage"])
    competitions = cast(Mapping[str, Mapping[str, object]], coverage["coverage_by_competition"])
    qualifying_competitions = sum(
        int(cast(int, record["at_least_2"]) >= 150) for record in competitions.values()
    )
    if (
        cast(int, cumulative["at_least_2"]["count"]) >= 600
        and cast(int, cumulative["at_least_3"]["count"]) >= 300
        and qualifying_competitions >= 3
    ):
        return "H2H_DEVELOPMENT_HISTORY_QUALIFIED"
    return "H2H_DEVELOPMENT_HISTORY_INSUFFICIENT"


def _future_package(
    classification: str, coverage: Mapping[str, object]
) -> dict[str, object] | None:
    if classification != "H2H_DEVELOPMENT_HISTORY_QUALIFIED":
        return None
    return {
        "contract": "MatchForgeH2HIncrementalSignalResearchDecisionPackageV1",
        "research_id": "MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1",
        "status": "PREPARED_AWAITING_OWNER_AUTHORIZATION",
        "baseline": "TRANSFERABLE_ROLLING_GOALS_NPXG_FOR_AGAINST_POISSON_RHO_ZERO_NO_H2H",
        "candidate": "IDENTICAL_BASELINE_PLUS_SECONDARY_MATCHUP_PRIOR_ONLY",
        "coverage": coverage,
        "primary_admission": {
            "weighted_joint_score_delta_maximum": -0.003,
            "weighted_joint_score_delta_95_interval_upper_below": 0.0,
        },
        "model_fitting_authorized": False,
        "model_evaluation_authorized": False,
        "confirmation_authorized": False,
        "v6_authorized": False,
    }


def _load_config(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text())
    if payload.get("contract") != "MatchForgeH2HDevelopmentHistoryAcquisitionConfigurationV1":
        raise SnapshotStop("CONFIGURATION_CONTRACT_MISMATCH")
    expected = (
        _integer(payload, "catalog_requests")
        + _integer(payload, "season_manifest_requests")
        + _integer(payload, "shot_requests")
    )
    if expected != payload.get("expected_requests"):
        raise SnapshotStop("CONFIGURATION_REQUEST_BUDGET_MISMATCH")
    if expected + _integer(payload, "retry_allowance") != payload.get("hard_request_ceiling"):
        raise SnapshotStop("CONFIGURATION_REQUEST_CEILING_MISMATCH")
    if payload.get("task_hard_request_ceiling") != payload.get("hard_request_ceiling"):
        raise SnapshotStop("CONFIGURATION_TASK_CEILING_MISMATCH")
    if (
        payload.get("authorization") != ACQUISITION_ID
        or payload.get("base_url") != "https://api.pitchapi.dev"
        or payload.get("concurrency") != 1
        or payload.get("minimum_request_start_interval_seconds") != 1.0
        or payload.get("timeout_seconds") != 30
    ):
        raise SnapshotStop("CONFIGURATION_BOUNDARY_MISMATCH")
    return cast(Mapping[str, object], payload)


def _groups(config: Mapping[str, object]) -> tuple[GroupSpec, ...]:
    values = config.get("history_groups")
    if not isinstance(values, list) or len(values) != 3:
        raise SnapshotStop("CONFIGURATION_GROUP_MISMATCH")
    groups: list[GroupSpec] = []
    for value in values:
        if not isinstance(value, Mapping) or value.get("role") != "DEVELOPMENT_HISTORY_ONLY":
            raise SnapshotStop("CONFIGURATION_ROLE_MISMATCH")
        groups.append(
            GroupSpec(
                scope_key=str(value["scope_key"]),
                competition=str(value["competition"]),
                country_code=str(value["country_code"]),
                season=str(value["season"]),
                expected_matches=cast(int, value["expected_matches"]),
                projected_targets=cast(int, value["projected_targets"]),
            )
        )
    exact = {
        ("Premier League", "2023/2024"),
        ("La Liga", "2023/2024"),
        ("Serie A", "2023/2024"),
    }
    if (
        {(group.competition, group.season) for group in groups} != exact
        or any(group.projected_targets != 0 for group in groups)
        or sum(group.expected_matches for group in groups) != _integer(config, "shot_requests")
    ):
        raise SnapshotStop("CONFIGURATION_SCOPE_MISMATCH")
    return tuple(groups)


def _integer(values: Mapping[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotStop("CONFIGURATION_INTEGER_MISMATCH")
    return value


def _stop_report(
    config: Mapping[str, object],
    client: Client,
    store: Store,
    started_at: datetime,
    code: str,
) -> dict[str, object]:
    provider_codes = {
        "AUTHORIZATION_FAILED",
        "REQUIRED_RESOURCE_NOT_FOUND",
    }
    classification = (
        "PROVIDER_OR_RIGHTS_BLOCKED"
        if code.startswith("AUTHORIZED_SCOPE_") or code in provider_codes
        else "ACQUISITION_FAILED"
    )
    return {
        "contract": "MatchForgeH2HDevelopmentHistoryAcquisitionStopV1",
        "status": "STOPPED",
        "classification": classification,
        "stop_code": code,
        "started_at": started_at.isoformat(),
        "stopped_at": datetime.now(UTC).isoformat(),
        "expected_requests": config["expected_requests"],
        "actual_requests": client.state.attempts,
        "retries_used": client.state.retries,
        "hard_request_ceiling": config["hard_request_ceiling"],
        "primary_bytes": store.primary_bytes,
        "partial_acquisition_is_qualified": False,
        "owner_review_required": True,
        "model_fitting_performed": False,
        "model_evaluation_performed": False,
        "v6_created": False,
    }


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
