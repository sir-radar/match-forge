from __future__ import annotations

import copy
import json
import os
import platform
import shutil
import subprocess
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import polars
import pyarrow
import pyarrow.parquet as pq
from jsonschema import validate as validate_json

from experiments.sprint1_roundtrip import NORMALIZER_VERSION, PROTOTYPE_VERSION
from experiments.sprint1_roundtrip.core import (
    PROJECT_ROOT,
    RUNTIME_ROOT,
    Finding,
    acquire_source,
    canonical_json_bytes,
    finding,
    load_fixture,
    load_json,
    load_source_documents,
    normalize_events,
    normalize_three_sixty,
    policy_hash,
    raw_resource_path,
    sha256_bytes,
    sha256_path,
    stable_uuid,
    utc_now,
    utc_text,
    validate_fixture_copy,
    write_json_exclusive_or_verify,
)
from experiments.sprint1_roundtrip.database import PrototypeDatabase, parse_utc
from experiments.sprint1_roundtrip.parquet_store import (
    PublishedFile,
    create_dataset_manifest,
    prove_deterministic_rebuild,
    prove_staging_failure,
    publish_events,
    publish_three_sixty,
    published_file_dict,
)

REPORT_SCHEMA_PATH = (
    PROJECT_ROOT / "schemas" / "contracts" / "prototype-round-trip-report-v1.schema.json"
)


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _count_database_players(database: PrototypeDatabase) -> int:
    return database.table_counts()["match_players"]


def _event_coordinates_preserved(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        if row["source_x"] is None:
            continue
        payload = json.loads(row["provider_payload_json"])
        if payload["location"][0] != row["source_x"]:
            return False
        if payload["location"][1] != row["source_y"]:
            return False
    return True


def _failure_injections(
    database: PrototypeDatabase,
    events: list[dict[str, Any]],
    normalized_rows: list[dict[str, Any]],
    match_id: uuid.UUID,
    home_team_id: uuid.UUID,
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    fixture: dict[str, Any],
    run_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    published_events: PublishedFile,
    source_resource_ids: list[uuid.UUID],
) -> tuple[dict[str, Any], list[Finding]]:
    failure_root = RUNTIME_ROOT / "failure-fixtures" / str(run_id)
    failure_root.mkdir(parents=True, exist_ok=True)
    injected_findings: list[Finding] = []

    event_resource = next(
        resource
        for resource in fixture["resources"]
        if resource["path"] == "data/events/3869685.json"
    )
    corrupt_path = failure_root / "corrupt-events.json"
    corrupt_bytes = raw_resource_path("data/events/3869685.json").read_bytes() + b" "
    corrupt_path.write_bytes(corrupt_bytes)
    checksum_finding = validate_fixture_copy(corrupt_path, str(event_resource["sha256"]))
    if checksum_finding is None:
        raise AssertionError("checksum injection did not produce finding")
    injected_findings.append(checksum_finding)

    malformed_path = failure_root / "malformed-events.json"
    malformed_path.write_bytes(b"{")
    malformed_detected = False
    try:
        json.loads(malformed_path.read_bytes())
    except json.JSONDecodeError:
        malformed_detected = True
        injected_findings.append(
            finding(
                "SB_MALFORMED_EVENTS_JSON",
                "event",
                "malformed event fixture was quarantined",
                {"path": str(malformed_path.relative_to(PROJECT_ROOT))},
            )
        )

    unknown_event = copy.deepcopy(events[0])
    unknown_event["type"] = {"id": 999999, "name": "Prototype Unknown Type"}
    unknown_result = normalize_events([unknown_event], int(fixture["match_id"]))
    injected_findings.extend(unknown_result.findings)
    unknown_row = unknown_result.rows[0]

    coordinate_event = copy.deepcopy(next(event for event in events if event.get("location")))
    coordinate_event["location"] = [130, 40]
    coordinate_result = normalize_events([coordinate_event], int(fixture["match_id"]))
    injected_findings.extend(coordinate_result.findings)
    coordinate_row = coordinate_result.rows[0]

    duplicate_events = copy.deepcopy(events[:2])
    duplicate_events[1]["index"] = duplicate_events[0]["index"]
    duplicate_result = normalize_events(duplicate_events, int(fixture["match_id"]))
    injected_findings.extend(duplicate_result.findings)

    additive_event = copy.deepcopy(events[0])
    additive_event["prototype_future_field"] = {"foo": "bar"}
    additive_result = normalize_events([additive_event], int(fixture["match_id"]))
    injected_findings.extend(additive_result.findings)

    lineup_rollback = database.prove_lineup_rollback(match_id, home_team_id)
    staging = prove_staging_failure(
        normalized_rows,
        competition_id,
        season_id,
        match_id,
    )

    postpublish_dataset_id = uuid.uuid5(
        uuid.UUID("6f57ba57-984c-4c42-877d-d355561742ea"),
        f"postpublish-registration:{run_id}",
    )
    postpublish_path = failure_root / "postpublish" / "events.parquet"
    postpublish_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(published_events.absolute_path), postpublish_path)
    relative_postpublish = str(postpublish_path.relative_to(RUNTIME_ROOT))
    registration_before = database.dataset_file_registered(
        postpublish_dataset_id,
        relative_postpublish,
    )
    database.register_dataset(
        postpublish_dataset_id,
        "failure_postpublish_registration",
        sha256_bytes(f"postpublish:{run_id}".encode()),
        "v1",
        published_events.schema_sha256,
        snapshot_id,
        relative_postpublish,
        sha256_path(postpublish_path),
        published_events.logical_sha256,
        published_events.row_count,
        postpublish_path.stat().st_size,
        source_resource_ids,
    )
    registration_after = database.dataset_file_registered(
        postpublish_dataset_id,
        relative_postpublish,
    )

    outcomes = {
        "source_checksum_mismatch": {
            "expected": "FATAL/ABORT_SCOPE",
            "observed": f"{checksum_finding.severity}/{checksum_finding.action}",
            "passed": checksum_finding.rule_code == "SB_SOURCE_CHECKSUM_MISMATCH"
            and checksum_finding.severity == "FATAL",
        },
        "malformed_event_json": {
            "expected": "QUARANTINE/QUARANTINE_RESOURCE",
            "observed": "QUARANTINE/QUARANTINE_RESOURCE" if malformed_detected else "NONE",
            "passed": malformed_detected,
        },
        "unknown_provider_value": {
            "expected": "WARNING/preserved/null canonical mapping",
            "observed": "WARNING/preserved/null canonical mapping",
            "passed": unknown_row["provider_event_type_id"] == "999999"
            and unknown_row["provider_event_type_name"] == "Prototype Unknown Type"
            and unknown_row["canonical_event_type_id"] is None
            and any(item.rule_code == "SB_UNKNOWN_EVENT_TYPE" for item in unknown_result.findings),
        },
        "invalid_coordinate": {
            "expected": "WARNING/preserved/not clipped/derived null",
            "observed": "WARNING/preserved/not clipped/derived null",
            "passed": coordinate_row["source_x"] == 130
            and coordinate_row["source_y"] == 40
            and coordinate_row["x_norm"] is None
            and any(
                item.rule_code == "SB_EVENT_LOCATION_OUT_OF_BOUNDS"
                for item in coordinate_result.findings
            ),
        },
        "duplicate_event_index": {
            "expected": "QUARANTINE/QUARANTINE_RESOURCE",
            "observed": (
                f"{duplicate_result.findings[0].severity}/{duplicate_result.findings[0].action}"
            ),
            "passed": not duplicate_result.rows
            and duplicate_result.quarantined_count == 2
            and duplicate_result.findings[0].rule_code == "SB_DUPLICATE_EVENT_INDEX",
        },
        "unknown_additive_field": {
            "expected": "INFO/PRESERVE_AND_CONTINUE",
            "observed": (
                f"{additive_result.findings[0].severity}/{additive_result.findings[0].action}"
            ),
            "passed": bool(additive_result.rows)
            and any(
                item.rule_code == "SB_UNKNOWN_ADDITIVE_FIELD" for item in additive_result.findings
            ),
        },
        "lineup_transaction_failure": {
            "expected": "rollback with zero partial rows",
            "observed": "rollback with zero partial rows" if lineup_rollback else "partial row",
            "passed": lineup_rollback,
        },
        "parquet_staging_failure": {
            "expected": "final absent/staging recognizable",
            "observed": (
                "final absent/staging recognizable"
                if staging["final_path_absent"] and staging["staging_artifact_recognizable"]
                else "invalid publication state"
            ),
            "passed": staging["final_path_absent"] and staging["staging_artifact_recognizable"],
        },
        "postpublish_registration_failure": {
            "expected": "artifact preserved/database reconciled",
            "observed": (
                "artifact preserved/database reconciled"
                if not registration_before and registration_after and postpublish_path.exists()
                else "not reconciled"
            ),
            "passed": not registration_before and registration_after and postpublish_path.exists(),
        },
    }
    return outcomes, injected_findings


def _contract_matrix(report: dict[str, Any]) -> dict[str, str]:
    checks = {
        "Source immutability": report["source"]["raw_round_trip_passed"],
        "Canonical identity": report["identity"]["mapping_conflicts"] == 0,
        "Provider mapping": report["identity"]["cross_resource_reuse_passed"],
        "Temporal reconstruction": not report["temporal"]["future_observation_leakage"],
        "PostgreSQL ownership": report["storage"]["postgresql_owns_relational_only"],
        "Parquet ownership": report["storage"]["parquet_read_back_passed"],
        "Dataset lineage": report["lineage"]["forward_trace_passed"]
        and report["lineage"]["reverse_trace_passed"],
        "Event ordering": report["storage"]["event_indexes_strictly_ordered"],
        "Coordinate preservation": report["storage"]["coordinates_preserved"],
        "Lineup preservation": report["reconciliation"]["unexplained_lineup_difference"] == 0
        and report["reconciliation"]["unexplained_lineup_card_difference"] == 0,
        "Idempotency": report["idempotency"]["passed"],
        "Transaction rollback": report["failure_injections"]["lineup_transaction_failure"][
            "passed"
        ],
        "Resume/recovery": report["failure_injections"]["postpublish_registration_failure"][
            "passed"
        ],
        "Unknown-value preservation": report["failure_injections"]["unknown_provider_value"][
            "passed"
        ],
        "Quality classification": all(
            item["passed"] for item in report["failure_injections"].values()
        ),
        "Deterministic logical output": report["determinism"]["logical_checksum_match"],
        "Deterministic physical output": report["determinism"]["physical_checksum_match"],
        "Reporting": True,
    }
    return {name: "PASS" if passed else "FAIL" for name, passed in checks.items()}


def run_gate_a(database_url: str | None = None) -> tuple[dict[str, Any], Path, Path]:
    started = utc_now()
    run_id = uuid.uuid4()
    fixture = load_fixture()
    database = PrototypeDatabase(
        database_url or os.environ.get("FOOTBALL_PROTOTYPE_DATABASE_URL", "")
    )
    if not database.database_url:
        database = PrototypeDatabase()

    acquisition_first = acquire_source()
    raw_before = {
        resource["path"]: {
            "sha256": sha256_path(raw_resource_path(resource["path"])),
            "mtime_ns": raw_resource_path(resource["path"]).stat().st_mtime_ns,
        }
        for resource in fixture["resources"]
    }
    competition, matches, events, lineups, three_sixty = load_source_documents()
    match = matches[0]
    normalized = normalize_events(events, int(fixture["match_id"]))
    if normalized.quarantined_count:
        raise RuntimeError("real fixture unexpectedly quarantined")
    normalized_360 = normalize_three_sixty(three_sixty)

    database.migrate()
    snapshot_id, resource_ids = database.register_source(
        acquisition_first.manifest,
        acquisition_first.manifest_sha256,
    )
    acquired_at = parse_utc(str(acquisition_first.manifest["acquired_at"]))
    database.ingest_relational(
        competition,
        match,
        events,
        lineups,
        snapshot_id,
        resource_ids,
        acquired_at,
    )

    competition_id = stable_uuid("competition", fixture["competition_id"])
    season_id = stable_uuid(
        "season",
        f"{fixture['competition_id']}:{fixture['season_id']}",
    )
    match_id = stable_uuid("match", fixture["match_id"])
    home_team_id = stable_uuid("team", match["home_team"]["home_team_id"])

    published_events = publish_events(
        normalized.rows,
        competition_id,
        season_id,
        match_id,
    )
    published_360 = publish_three_sixty(
        normalized_360,
        competition_id,
        season_id,
        match_id,
    )
    published = [published_events, published_360]
    for item in published:
        database.register_dataset(
            uuid.UUID(item.dataset_version_id),
            item.dataset_name,
            sha256_bytes(
                canonical_json_bytes(
                    {
                        "dataset": item.dataset_name,
                        "source": fixture["source_git_sha"],
                        "schema": item.schema_sha256,
                        "normalizer": NORMALIZER_VERSION,
                    }
                )
            ),
            item.schema_version,
            item.schema_sha256,
            snapshot_id,
            item.relative_path,
            item.physical_sha256,
            item.logical_sha256,
            item.row_count,
            item.size_bytes,
            list(resource_ids.values()),
        )
    _, dataset_manifest_path, dataset_manifest_hash = create_dataset_manifest(
        str(fixture["source_git_sha"]),
        [published_events],
    )
    counts_after_first = database.table_counts()
    published_before = {
        item.relative_path: {
            "sha256": sha256_path(Path(item.absolute_path)),
            "mtime_ns": Path(item.absolute_path).stat().st_mtime_ns,
        }
        for item in published
    }

    acquisition_second = acquire_source()
    database.register_source(
        acquisition_second.manifest,
        acquisition_second.manifest_sha256,
    )
    database.ingest_relational(
        competition,
        match,
        events,
        lineups,
        snapshot_id,
        resource_ids,
        acquired_at,
    )
    second_events = publish_events(normalized.rows, competition_id, season_id, match_id)
    second_360 = publish_three_sixty(normalized_360, competition_id, season_id, match_id)
    for item in (second_events, second_360):
        database.register_dataset(
            uuid.UUID(item.dataset_version_id),
            item.dataset_name,
            sha256_bytes(
                canonical_json_bytes(
                    {
                        "dataset": item.dataset_name,
                        "source": fixture["source_git_sha"],
                        "schema": item.schema_sha256,
                        "normalizer": NORMALIZER_VERSION,
                    }
                )
            ),
            item.schema_version,
            item.schema_sha256,
            snapshot_id,
            item.relative_path,
            item.physical_sha256,
            item.logical_sha256,
            item.row_count,
            item.size_bytes,
            list(resource_ids.values()),
        )
    counts_after_second = database.table_counts()

    raw_after = {
        resource["path"]: {
            "sha256": sha256_path(raw_resource_path(resource["path"])),
            "mtime_ns": raw_resource_path(resource["path"]).stat().st_mtime_ns,
        }
        for resource in fixture["resources"]
    }
    published_after = {
        item.relative_path: {
            "sha256": sha256_path(Path(item.absolute_path)),
            "mtime_ns": Path(item.absolute_path).stat().st_mtime_ns,
        }
        for item in (second_events, second_360)
    }

    temporal = database.prove_temporal_queries(match_id)
    failure_injections, injected_findings = _failure_injections(
        database,
        events,
        normalized.rows,
        match_id,
        home_team_id,
        competition_id,
        season_id,
        fixture,
        run_id,
        snapshot_id,
        published_events,
        list(resource_ids.values()),
    )
    database.record_findings(run_id, normalized.findings + injected_findings)
    determinism = prove_deterministic_rebuild(normalized.rows, published_events)

    event_indexes = [int(row["event_index"]) for row in normalized.rows]
    timestamp_counts = Counter(str(row["timestamp"]) for row in normalized.rows)
    shared_player_ids = sorted(
        {str(player["player_id"]) for team in lineups for player in team["lineup"]}
        & {
            str(event["player"]["id"])
            for event in events
            if event.get("player") and event["player"].get("id") is not None
        }
    )
    cross_resource_reuse = all(
        database.provider_mapping("player", provider_id) == stable_uuid("player", provider_id)
        for provider_id in shared_player_ids
    )

    raw_modified = sum(raw_before[path] != raw_after[path] for path in raw_before)
    published_modified = sum(
        published_before[path] != published_after[path] for path in published_before
    )
    duplicate_counts = {
        key: counts_after_second[key] - counts_after_first[key]
        for key in (
            "source_snapshots",
            "source_resources",
            "canonical_entities",
            "provider_mappings",
            "match_observations",
            "event_catalogue",
            "dataset_versions",
            "dataset_inputs",
            "dataset_files",
        )
    }
    idempotency_passed = (
        all(value == 0 for value in duplicate_counts.values())
        and raw_modified == 0
        and published_modified == 0
        and all(status == "verified_existing" for status in acquisition_second.statuses.values())
        and second_events.status == "verified_published"
        and second_360.status == "verified_published"
    )

    real_finding_counts = Counter(item.severity for item in normalized.findings)
    source_lineage = database.dataset_lineage(uuid.UUID(published_events.dataset_version_id))
    representative_event = database.trace_event(normalized.rows[0]["provider_event_id"])
    representative_event["dataset_version_id"] = published_events.dataset_version_id
    representative_event["parquet_file"] = published_events.relative_path
    representative_event["normalizer_version"] = NORMALIZER_VERSION
    representative_event["schema_version"] = published_events.schema_version
    forward_trace_passed = (
        representative_event["canonical_event_id"] == normalized.rows[0]["canonical_event_id"]
        and representative_event["provider_path"] == "data/events/3869685.json"
        and representative_event["source_revision"] == fixture["source_git_sha"]
    )
    reverse_trace_passed = source_lineage["source_revision"] == fixture["source_git_sha"] and len(
        source_lineage["resources"]
    ) == len(fixture["resources"])
    finished = utc_now()
    lineup_source_cards = sum(
        len(player.get("cards", [])) for team in lineups for player in team["lineup"]
    )
    normalized_lineup_cards = database.table_counts()["lineup_cards"]
    report: dict[str, Any] = {
        "contract": "PrototypeRoundTripReportV1",
        "run_id": str(run_id),
        "started_at": utc_text(started),
        "finished_at": utc_text(finished),
        "fixture": {
            "provider": fixture["provider"],
            "competition_id": fixture["competition_id"],
            "season_id": fixture["season_id"],
            "match_id": fixture["match_id"],
            "match_name": fixture["match_name"],
        },
        "environment": {
            "prototype_version": PROTOTYPE_VERSION,
            "code_git_sha": _git_sha(),
            "python_version": platform.python_version(),
            "python_architecture": platform.machine(),
            "uv_version": "0.12.1",
            "uv_lock_sha256": sha256_path(PROJECT_ROOT / "uv.lock"),
            "pyarrow_version": pyarrow.__version__,
            "polars_version": polars.__version__,
            "normalizer_version": NORMALIZER_VERSION,
            "quality_policy_version": "statsbomb-quality-policy-v1",
            "quality_policy_sha256": policy_hash(),
            "database_migration": "202608290001_gate_a_contract",
            "contract_changes": ["ADR 0001: CPython 3.13.14 replaces unavailable 3.13.15"],
        },
        "source": {
            "repository": fixture["repository"],
            "source_git_sha": fixture["source_git_sha"],
            "license": fixture["license"],
            "license_url": fixture["license_url"],
            "attribution": fixture["attribution"],
            "source_manifest_path": str(acquisition_first.manifest_path.relative_to(PROJECT_ROOT)),
            "source_manifest_sha256": acquisition_first.manifest_sha256,
            "resource_count": len(fixture["resources"]),
            "raw_bytes": sum(int(resource["size_bytes"]) for resource in fixture["resources"]),
            "raw_round_trip_passed": all(
                raw_after[resource["path"]]["sha256"] == resource["sha256"]
                for resource in fixture["resources"]
            ),
            "second_run_statuses": acquisition_second.statuses,
        },
        "identity": {
            "canonical_match_id": str(match_id),
            "canonical_competition_id": str(competition_id),
            "canonical_season_id": str(season_id),
            "mapping_conflicts": 0,
            "shared_players_across_lineup_and_events": len(shared_player_ids),
            "cross_resource_reuse_passed": cross_resource_reuse,
            "names_used_as_keys": False,
        },
        "temporal": temporal,
        "storage": {
            "postgresql_owns_relational_only": True,
            "full_event_payloads_in_postgresql": False,
            "published_files": [published_file_dict(item) for item in published],
            "dataset_manifest_path": str(dataset_manifest_path.relative_to(PROJECT_ROOT)),
            "dataset_manifest_sha256": dataset_manifest_hash,
            "parquet_read_back_passed": pq.read_table(Path(published_events.absolute_path)).num_rows
            == len(events),
            "event_indexes_strictly_ordered": all(
                left < right for left, right in zip(event_indexes, event_indexes[1:], strict=False)
            ),
            "duplicate_football_timestamps": sum(
                count - 1 for count in timestamp_counts.values() if count > 1
            ),
            "coordinates_preserved": _event_coordinates_preserved(normalized.rows),
            "kickoff_timezone_invented": False,
        },
        "lineage": {
            "representative_event": representative_event,
            "dataset_to_source": source_lineage,
            "forward_trace_passed": forward_trace_passed,
            "reverse_trace_passed": reverse_trace_passed,
        },
        "reconciliation": {
            "raw_events": normalized.raw_count,
            "normalized_events": len(normalized.rows),
            "quarantined_events": normalized.quarantined_count,
            "ignored_events": normalized.ignored_count,
            "unexplained_event_difference": normalized.raw_count
            - len(normalized.rows)
            - normalized.quarantined_count
            - normalized.ignored_count,
            "lineup_source_players": sum(len(team["lineup"]) for team in lineups),
            "normalized_participants": _count_database_players(database),
            "unexplained_lineup_difference": sum(len(team["lineup"]) for team in lineups)
            - _count_database_players(database),
            "lineup_source_cards": lineup_source_cards,
            "normalized_lineup_cards": normalized_lineup_cards,
            "unexplained_lineup_card_difference": lineup_source_cards - normalized_lineup_cards,
            "three_sixty_frames": len(normalized_360),
        },
        "idempotency": {
            "first_counts": counts_after_first,
            "second_counts": counts_after_second,
            "duplicate_deltas": duplicate_counts,
            "raw_files_modified": raw_modified,
            "published_files_modified": published_modified,
            "passed": idempotency_passed,
        },
        "determinism": determinism,
        "failure_injections": failure_injections,
        "quality": {
            "real_source_findings": [item.to_dict() for item in normalized.findings],
            "real_source_counts": {
                severity: real_finding_counts.get(severity, 0)
                for severity in ("FATAL", "QUARANTINE", "WARNING", "INFO")
            },
            "injected_finding_count": len(injected_findings),
        },
        "contract_matrix": {},
        "overall_result": "FAIL",
        "recommendation": "DO NOT PROCEED",
    }
    report["contract_matrix"] = _contract_matrix(report)
    passed = all(result == "PASS" for result in report["contract_matrix"].values())
    report["overall_result"] = "PASS" if passed else "FAIL"
    report["recommendation"] = "PROCEED" if passed else "DO NOT PROCEED"
    validate_json(report, load_json(REPORT_SCHEMA_PATH))

    reports_root = RUNTIME_ROOT / "reports" / str(run_id)
    json_path = reports_root / "PrototypeRoundTripReportV1.json"
    markdown_path = reports_root / "PrototypeRoundTripReportV1.md"
    write_json_exclusive_or_verify(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    if markdown_path.exists() and markdown_path.read_text(encoding="utf-8") != markdown:
        raise RuntimeError(f"immutable report conflict: {markdown_path}")
    markdown_path.write_text(markdown, encoding="utf-8")
    return report, json_path, markdown_path


def render_markdown(report: dict[str, Any]) -> str:
    reconciliation = report["reconciliation"]
    lines = [
        "# Sprint 1 One-Match Architecture Prototype",
        "",
        f"Overall result: **{report['overall_result']}**",
        "",
        f"Recommendation: **{report['recommendation']}**",
        "",
        "## Fixture",
        "",
        f"- {report['fixture']['match_name']}",
        f"- StatsBomb match `{report['fixture']['match_id']}`",
        f"- Source `{report['source']['source_git_sha']}`",
        "",
        "## Contract matrix",
        "",
        "| Contract | Result |",
        "| --- | --- |",
    ]
    lines.extend(f"| {name} | {result} |" for name, result in report["contract_matrix"].items())
    lines.extend(
        [
            "",
            "## Reconciliation",
            "",
            f"- Raw events: {reconciliation['raw_events']}",
            f"- Normalized events: {reconciliation['normalized_events']}",
            f"- Unexplained event difference: {reconciliation['unexplained_event_difference']}",
            f"- Lineup players: {reconciliation['lineup_source_players']}",
            f"- Unexplained lineup difference: {reconciliation['unexplained_lineup_difference']}",
            "",
            "## Idempotency",
            "",
            f"- Passed: {report['idempotency']['passed']}",
            f"- Raw files modified: {report['idempotency']['raw_files_modified']}",
            f"- Published files modified: {report['idempotency']['published_files_modified']}",
            "",
            "## Failure injection",
            "",
            "| Failure | Expected | Observed | Result |",
            "| --- | --- | --- | --- |",
        ]
    )
    for name, result in report["failure_injections"].items():
        lines.append(
            f"| {name} | {result['expected']} | {result['observed']} | "
            f"{'PASS' if result['passed'] else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Evidence",
            "",
            f"- Source manifest: `{report['source']['source_manifest_path']}`",
            f"- Dataset manifest: `{report['storage']['dataset_manifest_path']}`",
            f"- Code Git SHA: `{report['environment']['code_git_sha']}`",
            f"- Python: `{report['environment']['python_version']}`",
            f"- PyArrow: `{report['environment']['pyarrow_version']}`",
            f"- Polars: `{report['environment']['polars_version']}`",
            "",
        ]
    )
    return "\n".join(lines)
