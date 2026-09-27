#!/usr/bin/env python3
"""Acquire and qualify the authorized PitchAPI multi-domain development corpus."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid5

from football.contracts.source import canonical_json_bytes
from football.validation.pitchapi import (
    PitchApiAuditInput,
    PitchApiAuditMetadata,
    PitchApiQualificationEvidence,
    PitchApiRequestBudget,
    PitchApiSeasonAuditInput,
    PitchApiSeasonScope,
    validate_pitchapi_audit,
)
from football.validation.pitchapi_contingency import (
    PitchApiSnapshotIdentityV1,
    PitchApiSnapshotResourceIdentityV1,
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
    PilotManifestSelection,
    PilotStop,
    _dependency_lock_sha256,
    _git_sha,
    _read_env_secret,
    select_pilot_manifest,
)

CONFIG_PATH = Path(
    "docs/evaluation/pitchapi-multi-domain-development-acquisition-v1-r3-configuration.json"
)
OUTPUT_ROOT = Path(".local/pitchapi-multi-domain-development-v1-r3")
TOKEN_NAME = "PITCH_API_TOKEN"
NAMESPACE = UUID("f5f4c644-05a4-4b79-b968-e765ed659da0")
ADAPTER_VERSION = "pitchapi-multi-domain-development-adapter-v1"
CATALOG_PATH = "/v1/leagues"
CATALOG_CAP_BYTES = 4 * 1024**2
SEASON_CAP_BYTES = 10 * 1024**2
SHOT_CAP_BYTES = 2 * 1024**2
XG_SERIES = "PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_V1_RAW_XG"
V5_ROOT = Path(".local/pitchapi-snapshot-v1")
STATSBOMB_PROTECTED_MANIFESTS = (
    Path(
        ".local/football-data/manifests/datasets/"
        "dataset=d62b97d6-f39b-5f14-9773-61f57f7b677b/dataset-manifest-v1.json"
    ),
    Path(
        ".local/phase3a-serie-a-qualification-20260922/manifests/datasets/"
        "dataset=8bfec1dd-5bf7-5162-b56a-7e63f77b0b88/dataset-manifest-v1.json"
    ),
)
PROTECTED_STATSBOMB_SCOPES = frozenset(
    {
        ("Premier League", "2015/2016"),
        ("Serie A", "2015/2016"),
        ("Bundesliga", "2023/2024"),
        ("Ligue 1", "2022/2023"),
    }
)


@dataclass(frozen=True, slots=True)
class GroupSpec:
    scope_key: str
    competition: str
    country_code: str
    season: str
    expected_matches: int
    projected_targets: int


def acquire(config_path: Path = CONFIG_PATH, root: Path = OUTPUT_ROOT) -> dict[str, object]:
    config = _load_config(config_path)
    groups = _groups(config)
    store = Store(
        root,
        hard_storage_bytes=_integer(
            config, "hard_storage_ceiling_bytes", "CONFIGURATION_INTEGER_MISMATCH"
        ),
    )
    secret = _read_env_secret(Path(".env"), TOKEN_NAME)
    client = Client(
        secret,
        store,
        attempt_ceiling=_integer(config, "hard_request_ceiling", "CONFIGURATION_INTEGER_MISMATCH"),
        retry_reserve=_integer(config, "retry_allowance", "CONFIGURATION_INTEGER_MISMATCH"),
        wall_seconds=_integer(
            config, "wall_clock_ceiling_minutes", "CONFIGURATION_INTEGER_MISMATCH"
        )
        * 60,
    )
    del secret
    started_at = datetime.now(UTC)
    snapshot_id = uuid5(NAMESPACE, f"PITCHAPI_MULTI_DOMAIN_DEVELOPMENT_V1:{started_at.isoformat()}")
    resources: list[Resource] = []
    try:
        catalog, catalog_resource = _resource(
            store,
            client,
            scope_key="authorized_catalog",
            kind="league_catalog",
            resource_ref="catalog:authorized-scope-resolution",
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
    scopes: Mapping[str, PitchApiSeasonScope],
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
        shot_payloads: dict[str, Mapping[str, Any]] = {}
        match_lineage: dict[str, dict[str, str]] = {}
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
            shot_payloads[match_id] = payload
            match_lineage[match_id] = {
                "resource_ref": resource.resource_ref,
                "raw_sha256": resource.raw_sha256,
                "normalized_sha256": resource.normalized_sha256,
            }
            if index % 50 == 0 or index == group.expected_matches:
                _progress(group.scope_key, index, group.expected_matches, client)
        season_inputs.append(
            PitchApiSeasonAuditInput(validation_scope, selection.payload, shot_payloads)
        )
        group_inputs.append(
            {
                "spec": group,
                "matches": selection.ordered_matches,
                "shots": shot_payloads,
                "lineage": match_lineage,
                "manifest_resource": manifest_resource,
                "status_exclusions": status_exclusions,
                "valid_match_count": len(selection.ordered_matches),
            }
        )

    expected_base_requests = (
        1 + len(groups) + sum(cast(int, item["valid_match_count"]) for item in group_inputs)
    )
    if (
        client.state.attempts - client.state.retries != expected_base_requests
        or len(client.records) != client.state.attempts
        or client.state.attempts
        > _integer(config, "hard_request_ceiling", "CONFIGURATION_INTEGER_MISMATCH")
    ):
        raise SnapshotStop("REQUEST_LEDGER_MISMATCH")

    audit = PitchApiAuditInput(
        seasons=tuple(season_inputs),
        request_log=tuple(record for record in client.records if record.path != CATALOG_PATH),
        budget=PitchApiRequestBudget(
            expected_base_requests
            - 1
            + _integer(config, "retry_allowance", "CONFIGURATION_INTEGER_MISMATCH"),
            _integer(config, "retry_allowance", "CONFIGURATION_INTEGER_MISMATCH"),
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
    audit_report = validate_pitchapi_audit(audit)
    reports = {report.scope_key: report for report in audit_report.seasons}
    target_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    seen_teams: set[str] = set()
    for item in group_inputs:
        group = cast(GroupSpec, item["spec"])
        matches = cast(tuple[Mapping[str, object], ...], item["matches"])
        shots = cast(Mapping[str, Mapping[str, Any]], item["shots"])
        lineage = cast(Mapping[str, Mapping[str, str]], item["lineage"])
        group_status_exclusions = cast(Mapping[str, int], item["status_exclusions"])
        valid_match_count = cast(int, item["valid_match_count"])
        rows, target_counts, team_ids = _targets(group, matches, lineage, mappings, snapshot_id)
        report = reports[group.scope_key]
        semantic = _shot_semantics(shots)
        group_failures = _group_failures(report.to_dict(), valid_match_count, rows, target_counts)
        summaries.append(
            {
                "scope_key": group.scope_key,
                "role": "DEVELOPMENT_ONLY",
                "competition": group.competition,
                "season": group.season,
                "league_id": scopes[group.scope_key].league_id,
                "nominal_matches": group.expected_matches,
                "valid_matches": report.observed_matches,
                "fixture_status_exclusions": dict(sorted(group_status_exclusions.items())),
                "teams": len(team_ids),
                "new_to_earlier_group_team_count": len(team_ids - seen_teams),
                "total_shots": report.shots,
                "valid_npxg_shots": (
                    report.shots
                    - report.invalid_xg
                    - report.penalties
                    - cast(int, semantic["own_goals"])
                ),
                "penalties": report.penalties,
                "own_goals": semantic["own_goals"],
                "shot_situations": semantic["situations"],
                "history_warmup_exclusions": valid_match_count - len(rows),
                "exact_eligible_targets": len(rows),
                "outcomes": dict(sorted(target_counts.items())),
                "mapping_exclusions": 0,
                "schema_failures": _schema_failure_count(report.to_dict()),
                "semantic_failures": _semantic_failure_count(report.to_dict()),
                "missing_resource_failures": report.missing_shot_resources,
                "qualification_failures": group_failures,
                "admitted": not group_failures,
            }
        )
        seen_teams.update(team_ids)
        target_rows.extend(rows)

    mapping_manifest = _publish_mapping(store, mappings)
    resource_manifest = _publish_resource_manifest(store, resources, groups, scopes, raw=True)
    normalized_manifest = _publish_resource_manifest(store, resources, groups, scopes, raw=False)
    target_manifest = _publish_target_manifest(store, snapshot_id, target_rows)
    firewall = _firewall(target_rows, summaries)
    firewall_path, firewall_sha, _ = store.publish_bytes(
        "manifests", canonical_json_bytes(firewall)
    )
    group_firewalls = cast(Mapping[str, Mapping[str, int]], firewall["groups"])
    for summary in summaries:
        intersections = group_firewalls[cast(str, summary["scope_key"])]
        summary["protected_data_intersections"] = intersections
        if any(intersections.values()):
            cast(list[str], summary["qualification_failures"]).append("PROTECTED_DATA_INTERSECTION")
            summary["admitted"] = False
    total_targets = len(target_rows)
    total_outcomes = Counter(cast(str, row["outcome"]) for row in target_rows)
    package_failures = _package_failures(
        summaries, total_targets, total_outcomes, audit_report.technical_status, firewall
    )
    disposition = (
        "DEVELOPMENT_CORPUS_QUALIFIED"
        if not package_failures
        else "DEVELOPMENT_CORPUS_INSUFFICIENT"
    )
    corpus = {
        "contract": "PitchApiMultiDomainDevelopmentCorpusManifestV1",
        "snapshot_id": str(snapshot_id),
        "role": "DEVELOPMENT_ONLY",
        "groups": summaries,
        "target_manifest_path": target_manifest[0],
        "target_manifest_sha256": target_manifest[1],
        "exact_total_eligible_targets": total_targets,
        "outcomes": dict(sorted(total_outcomes.items())),
        "minimum_target_floor": 1200,
        "qualification_failures": package_failures,
        "disposition": disposition,
    }
    corpus_path, corpus_sha, _ = store.publish_bytes("manifests", canonical_json_bytes(corpus))
    ledger_path, ledger_sha, _ = _publish_request_ledger(store, resources)
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
        "snapshot_sha256": snapshot.sha256,
        "resource_manifest": resource_manifest[0],
        "resource_manifest_sha256": resource_manifest[1],
        "normalized_manifest": normalized_manifest[0],
        "normalized_manifest_sha256": normalized_manifest[1],
        "canonical_mapping_manifest": mapping_manifest[0],
        "corpus_manifest": corpus_path,
        "corpus_sha256": corpus_sha,
        "firewall_manifest": firewall_path,
        "firewall_sha256": firewall_sha,
        "request_ledger": ledger_path,
        "request_ledger_sha256": ledger_sha,
    }
    snapshot_path, snapshot_document_sha, _ = store.publish_bytes(
        "manifests", canonical_json_bytes(snapshot_document)
    )
    result: dict[str, object] = {
        "contract": "PitchApiMultiDomainDevelopmentAcquisitionReportV1",
        "status": "COMPLETED",
        "disposition": disposition,
        "snapshot_id": str(snapshot_id),
        "snapshot_sha256": snapshot.sha256,
        "snapshot_document": snapshot_path,
        "snapshot_document_sha256": snapshot_document_sha,
        "corpus_sha256": corpus_sha,
        "firewall_sha256": firewall_sha,
        "groups": summaries,
        "competitions": len({group.competition for group in groups}),
        "seasons": len({group.season for group in groups}),
        "development_groups": len(groups),
        "competitions_represented": sorted({group.competition for group in groups}),
        "seasons_represented": sorted({group.season for group in groups}),
        "exact_total_eligible_targets": total_targets,
        "minimum_target_floor_passed": total_targets >= 1200,
        "outcomes": dict(sorted(total_outcomes.items())),
        "v5_intersection_count": firewall["v5_intersection_count"],
        "statsbomb_protected_intersection_count": firewall[
            "statsbomb_protected_intersection_count"
        ],
        "canonical_mapping_result": {
            "status": "PASS",
            "fixture_aliases": sum(kind == "match" for kind, _ in mappings),
            "team_aliases": sum(kind == "team" for kind, _ in mappings),
            "unresolved_admitted_fixture_ids": 0,
            "ambiguous_aliases": 0,
        },
        "attempts_used": client.state.attempts,
        "task_attempts_used": _integer(
            config, "prior_attempts_used", "CONFIGURATION_INTEGER_MISMATCH"
        )
        + client.state.attempts,
        "retries_used": client.state.retries,
        "rate_limit_responses": client.state.rate_limits,
        "expected_requests": config["expected_requests"],
        "hard_request_ceiling": config["hard_request_ceiling"],
        "task_hard_request_ceiling": config["task_hard_request_ceiling"],
        "qualification_failures": package_failures,
        "model_fitting_performed": False,
        "v6_created": False,
        "confirmation_executed": False,
        "future_hypothesis": "TRANSFERABLE_ROLLING_NPXG_FOR_AGAINST_DIXON_COLES_V2",
        "future_hypothesis_supportable": disposition == "DEVELOPMENT_CORPUS_QUALIFIED",
        "confirmation_reserve_status": "REQUIREMENTS_DEFINED_BUT_NO_GROUPS_FROZEN",
        "provider_data_limitations": [
            "UPSTREAM_XG_MODEL_VERSION_NOT_EXPOSED",
            "PROVIDER_CORRECTION_HISTORY_NOT_AVAILABLE",
            "CONFIRMATION_RESERVE_REQUIREMENTS_DEFINED_BUT_NO_GROUPS_FROZEN",
        ],
    }
    store.publish_bytes("reports", canonical_json_bytes(result))
    backup_sha, total_bytes = store.seal_backup()
    result["backup_verification"] = "PASS"
    result["backup_inventory_sha256"] = backup_sha
    result["total_primary_and_backup_bytes"] = total_bytes
    (store.root / "RESULT.json").write_bytes(canonical_json_bytes(result) + b"\n")
    return result


def _integer(values: Mapping[str, object], key: str, stop_code: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SnapshotStop(stop_code)
    return value


def _load_config(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text())
    if payload.get("contract") != "PitchApiMultiDomainDevelopmentAcquisitionConfigurationV1":
        raise SnapshotStop("CONFIGURATION_CONTRACT_MISMATCH")
    expected = (
        _integer(payload, "catalog_requests", "CONFIGURATION_INTEGER_MISMATCH")
        + _integer(payload, "season_manifest_requests", "CONFIGURATION_INTEGER_MISMATCH")
        + _integer(payload, "shot_requests", "CONFIGURATION_INTEGER_MISMATCH")
    )
    if expected != payload.get("expected_requests"):
        raise SnapshotStop("CONFIGURATION_REQUEST_BUDGET_MISMATCH")
    if expected + _integer(
        payload, "retry_allowance", "CONFIGURATION_INTEGER_MISMATCH"
    ) != payload.get("hard_request_ceiling"):
        raise SnapshotStop("CONFIGURATION_REQUEST_CEILING_MISMATCH")
    if _integer(payload, "prior_attempts_used", "CONFIGURATION_INTEGER_MISMATCH") + _integer(
        payload, "hard_request_ceiling", "CONFIGURATION_INTEGER_MISMATCH"
    ) != payload.get("task_hard_request_ceiling"):
        raise SnapshotStop("CONFIGURATION_TASK_CEILING_MISMATCH")
    if (
        payload.get("base_url") != "https://api.pitchapi.dev"
        or payload.get("concurrency") != 1
        or payload.get("minimum_request_start_interval_seconds") != 1.0
        or payload.get("timeout_seconds") != 30
        or payload.get("minimum_target_floor") != 1200
    ):
        raise SnapshotStop("CONFIGURATION_BOUNDARY_MISMATCH")
    return cast(Mapping[str, object], payload)


def _groups(config: Mapping[str, object]) -> tuple[GroupSpec, ...]:
    values = config.get("development_groups")
    if not isinstance(values, list) or len(values) != 5:
        raise SnapshotStop("CONFIGURATION_GROUP_MISMATCH")
    groups = tuple(GroupSpec(**cast(dict[str, Any], value)) for value in values)
    if sum(group.expected_matches for group in groups) != _integer(
        config, "shot_requests", "CONFIGURATION_INTEGER_MISMATCH"
    ):
        raise SnapshotStop("CONFIGURATION_MATCH_COUNT_MISMATCH")
    if sum(group.projected_targets for group in groups) != 1272:
        raise SnapshotStop("CONFIGURATION_PROJECTED_TARGET_MISMATCH")
    if len({group.scope_key for group in groups}) != len(groups):
        raise SnapshotStop("CONFIGURATION_DUPLICATE_SCOPE")
    return groups


def _resolve_scopes(
    payload: Mapping[str, Any], groups: tuple[GroupSpec, ...]
) -> dict[str, PitchApiSeasonScope]:
    data = payload.get("data")
    leagues = data.get("leagues") if isinstance(data, Mapping) else None
    if not isinstance(leagues, list):
        raise SnapshotStop("MALFORMED_CATALOG_RESPONSE")
    resolved: dict[str, PitchApiSeasonScope] = {}
    for group in groups:
        matches = [
            item
            for item in leagues
            if isinstance(item, Mapping)
            and _name_key(item.get("name")) == _name_key(group.competition)
            and item.get("country_code") == group.country_code
            and isinstance(item.get("seasons"), list)
            and group.season in item["seasons"]
        ]
        if len(matches) != 1:
            raise SnapshotStop(f"AUTHORIZED_SCOPE_UNAVAILABLE:{group.scope_key}")
        league_id = matches[0].get("id")
        try:
            resolved[group.scope_key] = PitchApiSeasonScope(
                group.scope_key, str(league_id), group.season, group.expected_matches
            )
        except ValueError:
            raise SnapshotStop(f"AUTHORIZED_SCOPE_INVALID:{group.scope_key}") from None
    return resolved


def _select_valid_manifest(
    payload: Mapping[str, Any],
    scope: PitchApiSeasonScope,
    nominal_match_count: int,
) -> tuple[PilotManifestSelection, dict[str, int], PitchApiSeasonScope]:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise PilotStop("MALFORMED_MANIFEST")
    matches = data.get("matches")
    if not isinstance(matches, list):
        raise PilotStop("MALFORMED_MANIFEST")
    if len(matches) != nominal_match_count:
        raise PilotStop("FULL_SEASON_MATCH_COUNT_MISMATCH")
    if any(not isinstance(match, Mapping) for match in matches):
        raise PilotStop("MALFORMED_MANIFEST_FIXTURE")
    status_exclusions = Counter(
        str(match.get("status", "MISSING"))
        for match in matches
        if isinstance(match, Mapping) and match.get("status") != "finished"
    )
    finished = [
        match
        for match in matches
        if isinstance(match, Mapping) and match.get("status") == "finished"
    ]
    if not finished:
        raise PilotStop("NO_VALID_FINISHED_FIXTURES")
    filtered_payload = {
        "data": {
            "league": data.get("league"),
            "matches": finished,
        }
    }
    validation_scope = PitchApiSeasonScope(scope.key, scope.league_id, scope.season, len(finished))
    selection = select_pilot_manifest(
        filtered_payload,
        validation_scope,
        full_expected_match_count=len(finished),
    )
    return selection, dict(status_exclusions), validation_scope


def _name_key(value: object) -> str:
    return "".join(character for character in str(value).casefold() if character.isalnum())


def _register_mappings(
    mappings: dict[tuple[str, str], str], matches: Sequence[Mapping[str, object]]
) -> None:
    for match in matches:
        _mapping(mappings, "match", str(match.get("id", "")))
        for side in ("home_team", "away_team"):
            team = match.get(side)
            if not isinstance(team, Mapping):
                raise SnapshotStop("MALFORMED_TEAM_MAPPING")
            _mapping(mappings, "team", str(team.get("id", "")))


def _mapping(mappings: dict[tuple[str, str], str], kind: str, provider_id: str) -> str:
    if not provider_id:
        raise SnapshotStop("MISSING_PROVIDER_ALIAS")
    canonical = str(uuid5(NAMESPACE, f"pitchapi:{kind}:{provider_id}"))
    existing = mappings.setdefault((kind, provider_id), canonical)
    if existing != canonical:
        raise SnapshotStop("PROVIDER_ALIAS_COLLISION")
    return existing


def _targets(
    group: GroupSpec,
    matches: Sequence[Mapping[str, object]],
    lineage: Mapping[str, Mapping[str, str]],
    mappings: Mapping[tuple[str, str], str],
    snapshot_id: UUID,
) -> tuple[list[dict[str, object]], Counter[str], set[str]]:
    appearances: Counter[str] = Counter()
    batches: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for match in matches:
        batches[str(match["time_utc"])].append(match)
    rows: list[dict[str, object]] = []
    outcomes: Counter[str] = Counter()
    teams: set[str] = set()
    for kickoff in sorted(batches):
        batch = batches[kickoff]
        for match in batch:
            home = cast(Mapping[str, object], match["home_team"])
            away = cast(Mapping[str, object], match["away_team"])
            home_id, away_id = str(home["id"]), str(away["id"])
            teams.update((home_id, away_id))
            if appearances[home_id] < 10 or appearances[away_id] < 10:
                continue
            outcome = _outcome(match)
            outcomes[outcome] += 1
            provider_match_id = str(match["id"])
            rows.append(
                {
                    "canonical_fixture_id": mappings[("match", provider_match_id)],
                    "provider_fixture_id": provider_match_id,
                    "scope_key": group.scope_key,
                    "competition": group.competition,
                    "season": group.season,
                    "kickoff": kickoff,
                    "home_team_id": mappings[("team", home_id)],
                    "away_team_id": mappings[("team", away_id)],
                    "home_prior_appearances": appearances[home_id],
                    "away_prior_appearances": appearances[away_id],
                    "outcome": outcome,
                    "source_snapshot": str(snapshot_id),
                    "source_resource_lineage": lineage[provider_match_id],
                    "football_cutoff": kickoff,
                    "knowledge_cutoff": kickoff,
                    "knowledge_mode": "RETROSPECTIVE_SNAPSHOT_POINT_IN_TIME_REPLAY",
                }
            )
        for match in batch:
            home = cast(Mapping[str, object], match["home_team"])
            away = cast(Mapping[str, object], match["away_team"])
            appearances[str(home["id"])] += 1
            appearances[str(away["id"])] += 1
    return rows, outcomes, teams


def _outcome(match: Mapping[str, object]) -> str:
    home, away = match.get("score_home"), match.get("score_away")
    if (
        isinstance(home, bool)
        or isinstance(away, bool)
        or not isinstance(home, int)
        or not isinstance(away, int)
    ):
        raise SnapshotStop("INVALID_FINISHED_SCORE")
    return "home" if home > away else "away" if away > home else "draw"


def _shot_semantics(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, object]:
    situations: Counter[str] = Counter()
    own_goals = 0
    for payload in payloads.values():
        data = cast(Mapping[str, object], payload["data"])
        for period in cast(Sequence[Mapping[str, object]], data["periods"]):
            for shot in cast(Sequence[Mapping[str, object]], period["shots"]):
                situations[str(shot.get("situation"))] += 1
                if shot.get("is_own_goal") is True:
                    own_goals += 1
    return {"own_goals": own_goals, "situations": dict(sorted(situations.items()))}


def _group_failures(
    report: Mapping[str, object],
    valid_match_count: int,
    rows: list[dict[str, object]],
    outcomes: Counter[str],
) -> list[str]:
    failures: list[str] = []
    if report["observed_matches"] != valid_match_count:
        failures.append("MATCH_COUNT")
    if len(rows) < 200:
        failures.append("TARGET_COUNT_LT_200")
    for outcome in ("home", "draw", "away"):
        if outcomes[outcome] < 40:
            failures.append(f"{outcome.upper()}_OUTCOMES_LT_40")
    if _schema_failure_count(report):
        failures.append("SCHEMA")
    if _semantic_failure_count(report):
        failures.append("SEMANTICS")
    if report["missing_shot_resources"]:
        failures.append("MISSING_RESOURCES")
    return failures


def _schema_failure_count(report: Mapping[str, object]) -> int:
    return sum(
        _integer(report, field, "INVALID_AUDIT_REPORT")
        for field in (
            "malformed_shot_resources",
            "missing_fields",
            "duplicate_shot_ids",
            "invalid_xg",
        )
    )


def _semantic_failure_count(report: Mapping[str, object]) -> int:
    return _integer(report, "unknown_periods", "INVALID_AUDIT_REPORT") + _integer(
        report, "unknown_situations", "INVALID_AUDIT_REPORT"
    )


def _package_failures(
    summaries: list[dict[str, object]],
    total_targets: int,
    outcomes: Counter[str],
    technical_status: str,
    firewall: Mapping[str, object],
) -> list[str]:
    failures = [
        f"GROUP:{summary['scope_key']}:{failure}"
        for summary in summaries
        for failure in cast(list[str], summary["qualification_failures"])
    ]
    if total_targets < 1200:
        failures.append(f"TOTAL_TARGET_SHORTFALL:{1200 - total_targets}")
    for outcome in ("home", "draw", "away"):
        if outcomes[outcome] < 250:
            failures.append(f"TOTAL_{outcome.upper()}_OUTCOMES_LT_250")
    if technical_status != "PASS":
        failures.append(f"TECHNICAL_STATUS:{technical_status}")
    if firewall["status"] != "PASS":
        failures.append("FIREWALL")
    return failures


def _publish_mapping(store: Store, mappings: Mapping[tuple[str, str], str]) -> tuple[str, str, int]:
    payload = {
        "contract": "PitchApiMultiDomainCanonicalMappingManifestV1",
        "algorithm": "matchforge-explicit-uuid5-initial-allocation-v1",
        "mappings": [
            {
                "entity_type": kind,
                "provider_entity_id": provider_id,
                "canonical_id": canonical,
                "mapping_action": "initial",
            }
            for (kind, provider_id), canonical in sorted(mappings.items())
        ],
    }
    return store.publish_bytes("manifests", canonical_json_bytes(payload))


def _publish_resource_manifest(
    store: Store,
    resources: list[Resource],
    groups: tuple[GroupSpec, ...],
    scopes: Mapping[str, PitchApiSeasonScope],
    *,
    raw: bool,
) -> tuple[str, str, int]:
    group_by_key = {group.scope_key: group for group in groups}
    payload = {
        "contract": (
            "PitchApiRawResourceManifestV1" if raw else "PitchApiNormalizedResourceManifestV1"
        ),
        "resources": [
            {
                "resource_ref": item.resource_ref,
                "scope_key": item.scope_key,
                "provider_resource_id": _provider_resource_id(item, scopes),
                "provider_competition_id": (
                    scopes[item.scope_key].league_id if item.scope_key in scopes else None
                ),
                "competition": (
                    group_by_key[item.scope_key].competition
                    if item.scope_key in group_by_key
                    else None
                ),
                "season": (
                    group_by_key[item.scope_key].season if item.scope_key in group_by_key else None
                ),
                "resource_type": item.kind,
                "endpoint": item.path,
                "acquired_at": item.acquired_at,
                "sha256": item.raw_sha256 if raw else item.normalized_sha256,
                "bytes": item.raw_bytes if raw else item.normalized_bytes,
                "path": item.raw_relative_path if raw else item.normalized_relative_path,
                "schema_version": "pitchapi-v1-json",
            }
            for item in sorted(resources, key=lambda value: value.resource_ref)
        ],
    }
    return store.publish_bytes("manifests", canonical_json_bytes(payload))


def _provider_resource_id(resource: Resource, scopes: Mapping[str, PitchApiSeasonScope]) -> str:
    if resource.kind == "league_catalog":
        return "pitchapi-v1-league-catalog"
    if resource.kind == "season_manifest":
        return scopes[resource.scope_key].league_id
    if resource.kind == "match_shots":
        return resource.resource_ref.rsplit(":", maxsplit=1)[-1]
    raise SnapshotStop(f"UNKNOWN_RESOURCE_TYPE:{resource.kind}")


def _publish_request_ledger(store: Store, resources: list[Resource]) -> tuple[str, str, int]:
    response_sha_by_path = {resource.path: resource.raw_sha256 for resource in resources}
    attempts = []
    for line in (store.staging / "attempt-ledger.jsonl").read_text().splitlines():
        attempt = json.loads(line)
        attempt["response_sha256"] = (
            response_sha_by_path.get(str(attempt["path"]))
            if attempt.get("status_code") == 200
            else None
        )
        attempts.append(attempt)
    payload = {
        "contract": "PitchApiAcquisitionRequestLedgerV1",
        "attempts": attempts,
    }
    return store.publish_bytes("manifests", canonical_json_bytes(payload))


def _publish_target_manifest(
    store: Store, snapshot_id: UUID, targets: list[dict[str, object]]
) -> tuple[str, str, int]:
    payload = {
        "contract": "PitchApiDevelopmentTargetManifestV1",
        "snapshot_id": str(snapshot_id),
        "role": "DEVELOPMENT_ONLY",
        "targets": sorted(
            targets,
            key=lambda row: (str(row["kickoff"]), str(row["canonical_fixture_id"])),
        ),
    }
    return store.publish_bytes("manifests", canonical_json_bytes(payload))


def _firewall(
    targets: list[dict[str, object]], summaries: list[dict[str, object]]
) -> dict[str, object]:
    target_ids = {str(row["canonical_fixture_id"]) for row in targets}
    v5_ids = _v5_target_ids()
    spent_ids, spent_scopes = _prior_spent_pitchapi()
    statsbomb_ids = _statsbomb_protected_ids()
    scopes = {(_name_key(item["competition"]), str(item["season"])) for item in summaries}
    v5_scopes = _v5_evaluation_scopes()
    protected_statsbomb_scopes = {
        (_name_key(competition), season) for competition, season in PROTECTED_STATSBOMB_SCOPES
    }
    protected_scope_intersection = scopes & protected_statsbomb_scopes
    v5_scope_intersection = scopes & v5_scopes
    spent_scope_intersection = scopes & spent_scopes
    v5_intersection = target_ids & v5_ids
    spent_intersection = target_ids & spent_ids
    statsbomb_intersection = target_ids & statsbomb_ids
    group_intersections: dict[str, dict[str, int]] = {}
    for summary in summaries:
        scope_key = str(summary["scope_key"])
        group_ids = {
            str(row["canonical_fixture_id"]) for row in targets if row["scope_key"] == scope_key
        }
        scope = (_name_key(summary["competition"]), str(summary["season"]))
        group_intersections[scope_key] = {
            "v5_targets": len(group_ids & v5_ids),
            "prior_spent_targets": len(group_ids & spent_ids),
            "statsbomb_protected_fixtures": len(group_ids & statsbomb_ids),
            "v5_protected_scopes": int(scope in v5_scopes),
            "prior_spent_scopes": int(scope in spent_scopes),
            "statsbomb_protected_scopes": int(scope in protected_statsbomb_scopes),
        }
    status = (
        "PASS"
        if not v5_intersection
        and not spent_intersection
        and not statsbomb_intersection
        and not protected_scope_intersection
        and not v5_scope_intersection
        and not spent_scope_intersection
        else "FAIL"
    )
    return {
        "contract": "PitchApiMultiDomainDevelopmentFirewallV1",
        "status": status,
        "v5_intersection_count": len(v5_intersection),
        "prior_spent_intersection_count": len(spent_intersection),
        "statsbomb_protected_intersection_count": len(statsbomb_intersection),
        "v5_protected_scope_intersection_count": len(v5_scope_intersection),
        "prior_spent_scope_intersection_count": len(spent_scope_intersection),
        "statsbomb_protected_scope_intersection_count": len(protected_scope_intersection),
        "strict_prior_kickoff": True,
        "same_kickoff_batching": True,
        "v5_identity_count_compared": len(v5_ids),
        "prior_spent_identity_count_compared": len(spent_ids),
        "statsbomb_identity_count_compared": len(statsbomb_ids),
        "groups": group_intersections,
    }


def _v5_target_ids() -> set[str]:
    corpus = _v5_corpus()
    return {
        str(target)
        for group in corpus["groups"]
        if group["role"] == "evaluation"
        for target in corpus["target_plans"][group["scope_key"]]["target_ids"]
    }


def _v5_evaluation_scopes() -> set[tuple[str, str]]:
    return {
        (_name_key(group["competition"]), str(group["season"]))
        for group in _v5_corpus()["groups"]
        if group["role"] == "evaluation"
    }


def _prior_spent_pitchapi() -> tuple[set[str], set[tuple[str, str]]]:
    corpus = _v5_corpus()
    ids = {
        str(target)
        for group in corpus["groups"]
        for target in corpus["target_plans"][group["scope_key"]]["target_ids"]
    }
    scopes = {(_name_key(group["competition"]), str(group["season"])) for group in corpus["groups"]}
    return ids, scopes


def _v5_corpus() -> Mapping[str, Any]:
    result = json.loads((V5_ROOT / "RESULT.json").read_text())
    snapshot = json.loads((V5_ROOT / "primary" / result["snapshot_manifest"]).read_text())
    return cast(
        Mapping[str, Any],
        json.loads((V5_ROOT / "primary" / snapshot["corpus_manifest"]).read_text()),
    )


def _statsbomb_protected_ids() -> set[str]:
    identities: set[str] = set()
    for path in STATSBOMB_PROTECTED_MANIFESTS:
        payload = json.loads(path.read_text())
        for item in payload["files"]:
            for part in str(item["relative_path"]).split("/"):
                if part.startswith("match_id="):
                    identities.add(part.removeprefix("match_id="))
    return identities


def _stop_report(
    config: Mapping[str, object],
    client: Client,
    store: Store,
    started_at: datetime,
    code: str,
) -> dict[str, object]:
    if code.startswith("AUTHORIZED_SCOPE_") or code in {
        "AUTHORIZATION_FAILED",
        "REQUIRED_RESOURCE_NOT_FOUND",
    }:
        disposition = "PROVIDER_OR_RIGHTS_BLOCKED"
    else:
        disposition = "ACQUISITION_FAILED"
    return {
        "contract": "PitchApiMultiDomainDevelopmentAcquisitionStopV1",
        "status": "STOPPED",
        "disposition": disposition,
        "stop_code": code,
        "started_at": started_at.isoformat(),
        "stopped_at": datetime.now(UTC).isoformat(),
        "attempts_used": client.state.attempts,
        "task_attempts_used": _integer(
            config, "prior_attempts_used", "CONFIGURATION_INTEGER_MISMATCH"
        )
        + client.state.attempts,
        "retries_used": client.state.retries,
        "rate_limit_responses": client.state.rate_limits,
        "expected_requests": config["expected_requests"],
        "hard_request_ceiling": config["hard_request_ceiling"],
        "task_hard_request_ceiling": config["task_hard_request_ceiling"],
        "primary_bytes": store.primary_bytes,
        "partial_acquisition_is_qualified": False,
        "owner_review_required": True,
    }


def _progress(scope: str, processed: int, expected: int, client: Client) -> None:
    print(
        json.dumps(
            {
                "event": "sanitized_progress",
                "scope": scope,
                "resources_processed": processed,
                "resources_expected": expected,
                "attempts_used": client.state.attempts,
                "retries_used": client.state.retries,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


def _seal_read_only(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        mode = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
        if path.is_dir():
            mode |= stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        os.chmod(path, mode)
    os.chmod(
        root,
        stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
    )


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
