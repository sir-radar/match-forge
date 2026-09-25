#!/usr/bin/env python3
"""Acquire and seal the owner-approved immutable PitchAPI snapshot V1."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid5

from football.contracts.source import canonical_json_bytes
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

from scripts.run_pitchapi_validation_pilot import (
    PilotManifestSelection,
    PilotStop,
    _dependency_lock_sha256,
    _git_sha,
    _read_env_secret,
    select_pilot_manifest,
)

_BASE_URL = "https://api.pitchapi.dev"
_TOKEN_NAME = "PITCH_API_TOKEN"
_OUTPUT_ROOT = Path(".local/pitchapi-snapshot-v1")
_POLICY_PATH = Path("docs/evaluation/pitchapi-retrospective-evaluation-v1-policy-proposal.json")
_ADAPTER_VERSION = "pitchapi-snapshot-adapter-v1"
_NAMESPACE = UUID("f5f4c644-05a4-4b79-b968-e765ed659da0")
_TIMEOUT_SECONDS = 30
_MIN_INTERVAL_SECONDS = 1.0
_RETRY_DELAY_SECONDS = 5
_WALL_SECONDS = 45 * 60
_BASE_REQUESTS = 1302
_RETRY_RESERVE = 27
_ATTEMPT_CEILING = 1329
_HARD_STORAGE_BYTES = 6 * 1024**3
_SEASON_CAP_BYTES = 10 * 1024**2
_SHOT_CAP_BYTES = 2 * 1024**2
_RETRYABLE = frozenset((408, 429, 500, 501, 502, 503, 504))

_SCOPES = (
    ("bundesliga_2021_22", "development", "bundesliga", "l_1Isor4", "2021/2022", 306),
    ("bundesliga_2022_23", "evaluation", "bundesliga", "l_1Isor4", "2022/2023", 306),
    ("bundesliga_2023_24", "evaluation", "bundesliga", "l_1Isor4", "2023/2024", 306),
    ("ligue1_2022_23", "evaluation", "ligue1", "l_3FJFUl", "2022/2023", 380),
)


class SnapshotStop(RuntimeError):
    """Approved acquisition reached a fail-closed stop condition."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Resource:
    resource_ref: str
    scope_key: str
    kind: str
    path: str
    acquired_at: str
    raw_sha256: str
    raw_bytes: int
    raw_relative_path: str
    normalized_sha256: str
    normalized_bytes: int
    normalized_relative_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "resource_ref": self.resource_ref,
            "scope_key": self.scope_key,
            "kind": self.kind,
            "endpoint_identity": self.path,
            "acquired_at": self.acquired_at,
            "raw_sha256": self.raw_sha256,
            "raw_bytes": self.raw_bytes,
            "raw_relative_path": self.raw_relative_path,
            "normalized_sha256": self.normalized_sha256,
            "normalized_bytes": self.normalized_bytes,
            "normalized_relative_path": self.normalized_relative_path,
        }


@dataclass(slots=True)
class RuntimeState:
    started: float
    attempts: int = 0
    retries: int = 0
    rate_limits: int = 0
    last_started: float | None = None


class Store:
    def __init__(self, root: Path) -> None:
        if root.exists():
            raise SnapshotStop("SNAPSHOT_OUTPUT_ALREADY_EXISTS")
        self.root = root.resolve()
        self.primary = self.root / "primary"
        self.backup = self.root / "backup"
        self.staging = self.root / "staging"
        self.primary.mkdir(parents=True)
        self.staging.mkdir()
        self.primary_bytes = 0

    def temporary(self) -> tuple[BinaryIO, Path]:
        descriptor, name = tempfile.mkstemp(prefix="response-", dir=self.staging)
        return os.fdopen(descriptor, "w+b"), Path(name)

    def publish_file(self, category: str, temporary: Path, digest: str, size: int) -> str:
        self._check_projected(size, temporary_bytes=size)
        relative = f"{category}/sha256/{digest[:2]}/{digest}.json"
        target = self.primary / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if _sha256_file(target) != digest or target.stat().st_size != size:
                raise SnapshotStop("IMMUTABLE_PATH_CONFLICT")
            temporary.unlink(missing_ok=True)
            return relative
        os.link(temporary, target)
        _fsync_directory(target.parent)
        temporary.unlink()
        self.primary_bytes += size
        return relative

    def publish_bytes(self, category: str, payload: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(payload).hexdigest()
        handle, temporary = self.temporary()
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            relative = self.publish_file(category, temporary, digest, len(payload))
        finally:
            temporary.unlink(missing_ok=True)
        return relative, digest, len(payload)

    def _check_projected(self, added_primary: int, *, temporary_bytes: int = 0) -> None:
        del temporary_bytes
        projected = 2 * (self.primary_bytes + added_primary) + _tree_size(self.staging)
        if projected >= _HARD_STORAGE_BYTES:
            raise SnapshotStop("HARD_STORAGE_CEILING_WOULD_BE_EXCEEDED")

    def seal_backup(self) -> tuple[str, int]:
        if self.backup.exists():
            raise SnapshotStop("BACKUP_ALREADY_EXISTS")
        self._check_projected(0)
        shutil.copytree(self.primary, self.backup, copy_function=shutil.copy2)
        primary_inventory = _inventory(self.primary)
        backup_inventory = _inventory(self.backup)
        if primary_inventory != backup_inventory:
            raise SnapshotStop("BACKUP_HASH_MISMATCH")
        total = _tree_size(self.primary) + _tree_size(self.backup)
        if total >= _HARD_STORAGE_BYTES:
            raise SnapshotStop("HARD_STORAGE_CEILING_EXCEEDED")
        digest = hashlib.sha256(canonical_json_bytes(primary_inventory)).hexdigest()
        return digest, total


class Client:
    def __init__(
        self,
        secret: str,
        store: Store,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        if not secret:
            raise SnapshotStop("MISSING_CREDENTIAL")
        self._secret = secret
        self._store = store
        self._sleep = sleep
        self._monotonic = monotonic
        self._opener = opener
        self.state = RuntimeState(monotonic())
        self.records: list[PitchApiRequestRecord] = []
        self.starts: list[float] = []
        self._ledger = store.staging / "attempt-ledger.jsonl"

    def get(self, path: str, *, cap: int) -> tuple[Mapping[str, Any], str, int, str]:
        for path_attempt in (1, 2):
            self._before_request()
            try:
                return self._request(path, cap)
            except urllib.error.HTTPError as error:
                if self._handle_http(path, path_attempt, error):
                    continue
                raise SnapshotStop("PATH_ATTEMPT_LIMIT_REACHED") from error
            except (TimeoutError, urllib.error.URLError, ConnectionError, OSError):
                self._record(PitchApiRequestRecord(path=path, failure_kind="network_error"))
                if self._retry(path_attempt, _RETRY_DELAY_SECONDS):
                    continue
                raise SnapshotStop("TRANSPORT_FAILURE") from None
        raise SnapshotStop("PATH_ATTEMPT_LIMIT_REACHED")

    def _before_request(self) -> None:
        now = self._monotonic()
        if now - self.state.started >= _WALL_SECONDS:
            raise SnapshotStop("WALL_CLOCK_CEILING_REACHED")
        if self.state.attempts >= _ATTEMPT_CEILING:
            raise SnapshotStop("HARD_ATTEMPT_CEILING_REACHED")
        if self.state.last_started is not None:
            wait = _MIN_INTERVAL_SECONDS - (now - self.state.last_started)
            if wait > 0:
                self._sleep(wait)
        started = self._monotonic()
        self.state.last_started = started
        self.starts.append(started)
        self.state.attempts += 1

    def _request(self, path: str, cap: int) -> tuple[Mapping[str, Any], str, int, str]:
        request = urllib.request.Request(
            f"{_BASE_URL}{path}",
            headers={
                "Accept": "application/json",
                "User-Agent": "MatchForge-private-research/1.0",
                "X-API-KEY": self._secret,
            },
            method="GET",
        )
        handle, temporary = self._store.temporary()
        digest = hashlib.sha256()
        size = 0
        try:
            with self._opener(request, timeout=_TIMEOUT_SECONDS) as response, handle:
                if int(response.status) != 200:
                    raise SnapshotStop("UNEXPECTED_RESPONSE_STATUS")
                content_type = str(response.headers.get("Content-Type", "")).split(";", 1)[0]
                if content_type.lower() != "application/json":
                    raise SnapshotStop("CONTENT_TYPE_MISMATCH")
                length = response.headers.get("Content-Length")
                if length is not None and int(length) > cap:
                    raise SnapshotStop("RESPONSE_SIZE_LIMIT_EXCEEDED")
                while True:
                    chunk = response.read(min(65536, cap + 1 - size))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > cap:
                        raise SnapshotStop("RESPONSE_SIZE_LIMIT_EXCEEDED")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
                request_id = bool(response.headers.get("X-Request-ID"))
            raw_digest = digest.hexdigest()
            try:
                payload = json.loads(temporary.read_bytes())
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise SnapshotStop("MALFORMED_JSON_RESPONSE") from None
            if not isinstance(payload, Mapping):
                raise SnapshotStop("MALFORMED_JSON_RESPONSE")
            self._record(
                PitchApiRequestRecord(
                    path=path,
                    status_code=200,
                    request_id_present=request_id,
                )
            )
            return cast(Mapping[str, Any], payload), raw_digest, size, str(temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _handle_http(self, path: str, path_attempt: int, error: urllib.error.HTTPError) -> bool:
        status = int(error.code)
        retry_after = _retry_after(error.headers.get("Retry-After") if error.headers else None)
        self._record(
            PitchApiRequestRecord(
                path=path,
                status_code=status,
                provider_code="RATE_LIMIT_EXCEEDED" if status == 429 else f"HTTP_{status}",
                request_id_present=bool(
                    error.headers.get("X-Request-ID") if error.headers else None
                ),
                retry_after_seconds=retry_after,
            )
        )
        if status in (401, 403):
            raise SnapshotStop("AUTHORIZATION_FAILED")
        if status == 404:
            raise SnapshotStop("REQUIRED_RESOURCE_NOT_FOUND")
        if status == 429:
            self.state.rate_limits += 1
            if retry_after is None:
                raise SnapshotStop("RATE_LIMIT_WITHOUT_VALID_RETRY_AFTER")
            if self.state.rate_limits >= 2:
                raise SnapshotStop("REPEATED_RATE_LIMIT")
        if status not in _RETRYABLE:
            raise SnapshotStop("NON_RETRYABLE_HTTP_STATUS")
        if status == 429:
            assert retry_after is not None
            delay = retry_after + _RETRY_DELAY_SECONDS
        else:
            delay = _RETRY_DELAY_SECONDS
        return self._retry(path_attempt, delay)

    def _retry(self, path_attempt: int, delay: int) -> bool:
        if path_attempt >= 2:
            return False
        if self.state.retries >= _RETRY_RESERVE:
            raise SnapshotStop("RETRY_RESERVE_EXHAUSTED")
        if self._monotonic() - self.state.started + delay >= _WALL_SECONDS:
            raise SnapshotStop("RETRY_AFTER_EXCEEDS_WALL_CLOCK")
        self.state.retries += 1
        self._sleep(delay)
        return True

    def _record(self, record: PitchApiRequestRecord) -> None:
        self.records.append(record)
        line = canonical_json_bytes(
            {
                "attempt": len(self.records),
                "path": record.path,
                "status_code": record.status_code,
                "provider_code": record.provider_code,
                "request_id_present": record.request_id_present,
                "retry_after_seconds": record.retry_after_seconds,
                "failure_kind": record.failure_kind,
            }
        )
        with self._ledger.open("ab") as ledger:
            ledger.write(line + b"\n")
            ledger.flush()
            os.fsync(ledger.fileno())


def _resource(
    store: Store,
    client: Client,
    *,
    scope_key: str,
    kind: str,
    resource_ref: str,
    path: str,
    cap: int,
) -> tuple[Mapping[str, Any], Resource]:
    acquired_at = _utc_now()
    payload, raw_digest, raw_size, temporary_name = client.get(path, cap=cap)
    raw_relative = store.publish_file("raw", Path(temporary_name), raw_digest, raw_size)
    try:
        normalized = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError):
        raise SnapshotStop("NORMALIZATION_FAILED") from None
    normalized_relative, normalized_digest, normalized_size = store.publish_bytes(
        "normalized", normalized
    )
    return payload, Resource(
        resource_ref,
        scope_key,
        kind,
        path,
        acquired_at,
        raw_digest,
        raw_size,
        raw_relative,
        normalized_digest,
        normalized_size,
        normalized_relative,
    )


def acquire(secret: str, root: Path = _OUTPUT_ROOT) -> dict[str, object]:
    store = Store(root)
    client = Client(secret, store)
    started_at = datetime.now(UTC)
    resources: list[Resource] = []
    season_inputs: list[PitchApiSeasonAuditInput] = []
    season_summaries: list[dict[str, object]] = []
    mappings: dict[tuple[str, str], str] = {}
    target_plans: dict[str, dict[str, object]] = {}
    try:
        for scope_key, role, competition, league_id, season, expected_count in _SCOPES:
            scope = PitchApiSeasonScope(scope_key, league_id, season, expected_count)
            manifest, manifest_resource = _resource(
                store,
                client,
                scope_key=scope_key,
                kind="season_manifest",
                resource_ref=f"season:{scope_key}",
                path=scope.manifest_path,
                cap=_SEASON_CAP_BYTES,
            )
            resources.append(manifest_resource)
            selection = select_pilot_manifest(
                manifest, scope, full_expected_match_count=expected_count
            )
            _register_fixture_mappings(mappings, selection)
            shot_payloads: dict[str, Mapping[str, Any]] = {}
            shots = 0
            match_manifests: list[dict[str, object]] = []
            for index, match in enumerate(selection.ordered_matches, start=1):
                match_id = str(match["id"])
                shot_payload, shot_resource = _resource(
                    store,
                    client,
                    scope_key=scope_key,
                    kind="match_shots",
                    resource_ref=f"shots:{scope_key}:{match_id}",
                    path=f"/v1/matches/{match_id}/shots",
                    cap=_SHOT_CAP_BYTES,
                )
                resources.append(shot_resource)
                shot_payloads[match_id] = shot_payload
                match_shots = _shot_count(shot_payload, match_id)
                shots += match_shots
                home = cast(Mapping[str, object], match["home_team"])
                away = cast(Mapping[str, object], match["away_team"])
                match_manifest = {
                    "contract": "PitchApiMatchManifestV1",
                    "scope_key": scope_key,
                    "provider_match_id": match_id,
                    "canonical_match_id": mappings[("match", match_id)],
                    "kickoff_at": match["time_utc"],
                    "home_provider_team_id": home["id"],
                    "home_canonical_team_id": mappings[("team", str(home["id"]))],
                    "away_provider_team_id": away["id"],
                    "away_canonical_team_id": mappings[("team", str(away["id"]))],
                    "shot_count": match_shots,
                    "raw_sha256": shot_resource.raw_sha256,
                    "normalized_sha256": shot_resource.normalized_sha256,
                }
                match_path, match_sha, _ = store.publish_bytes(
                    "manifests", canonical_json_bytes(match_manifest)
                )
                match_manifests.append(
                    {
                        "provider_match_id": match_id,
                        "canonical_match_id": mappings[("match", match_id)],
                        "manifest_path": match_path,
                        "manifest_sha256": match_sha,
                    }
                )
                if index % 50 == 0 or index == expected_count:
                    _progress(scope_key, index, expected_count, client)
            season_inputs.append(PitchApiSeasonAuditInput(scope, selection.payload, shot_payloads))
            target_plan = _target_plan(selection, mappings)
            target_plans[scope_key] = target_plan
            season_manifest = {
                "contract": "PitchApiSeasonManifestV1",
                "scope_key": scope_key,
                "role": role,
                "competition": competition,
                "season": season,
                "league_id": league_id,
                "match_count": expected_count,
                "shot_count": shots,
                "season_resource_raw_sha256": manifest_resource.raw_sha256,
                "season_resource_normalized_sha256": manifest_resource.normalized_sha256,
                "matches": match_manifests,
                "target_plan": target_plan,
            }
            season_manifest_path, season_manifest_sha, _ = store.publish_bytes(
                "manifests", canonical_json_bytes(season_manifest)
            )
            season_summaries.append(
                {
                    "scope_key": scope_key,
                    "role": role,
                    "competition": competition,
                    "season": season,
                    "matches": expected_count,
                    "shots": shots,
                    "eligible_targets": len(cast(list[object], target_plan["target_ids"])),
                    "warmup_exclusions": expected_count
                    - len(cast(list[object], target_plan["target_ids"])),
                    "manifest_raw_sha256": manifest_resource.raw_sha256,
                    "season_manifest_path": season_manifest_path,
                    "season_manifest_sha256": season_manifest_sha,
                }
            )
        return _seal(
            store,
            client,
            started_at,
            resources,
            season_inputs,
            season_summaries,
            mappings,
            target_plans,
        )
    except (PilotStop, SnapshotStop) as error:
        code = error.code
        stopped = _stop_report(store, client, code, started_at)
        _write_stop_report(store.root, stopped)
        return stopped


def _seal(
    store: Store,
    client: Client,
    started_at: datetime,
    resources: list[Resource],
    seasons: list[PitchApiSeasonAuditInput],
    season_summaries: list[dict[str, object]],
    mappings: dict[tuple[str, str], str],
    target_plans: dict[str, dict[str, object]],
) -> dict[str, object]:
    if (
        client.state.attempts - client.state.retries != _BASE_REQUESTS
        or len(client.records) != client.state.attempts
        or client.state.attempts > _ATTEMPT_CEILING
    ):
        raise SnapshotStop("REQUEST_LEDGER_MISMATCH")
    audit = PitchApiAuditInput(
        seasons=tuple(seasons),
        request_log=tuple(client.records),
        budget=PitchApiRequestBudget(_ATTEMPT_CEILING, _RETRY_RESERVE),
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
            xg_series_by_scope={scope.scope.key: "PITCHAPI_SNAPSHOT_V1" for scope in seasons},
        ),
    )
    audit_report = validate_pitchapi_audit(audit)
    if audit_report.technical_status != "PASS" or audit_report.stopped:
        raise SnapshotStop("TECHNICAL_VALIDATION_FAILED")

    mapping_document = {
        "contract": "PitchApiCanonicalMappingManifestV1",
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
    mapping_bytes = canonical_json_bytes(mapping_document)
    mapping_relative, mapping_sha, _ = store.publish_bytes("manifests", mapping_bytes)
    policy_sha = hashlib.sha256(_POLICY_PATH.read_bytes()).hexdigest()
    snapshot = PitchApiSnapshotIdentityV1(
        snapshot_id=uuid5(_NAMESPACE, f"PITCHAPI_SNAPSHOT_V1:{started_at.isoformat()}"),
        acquired_at=started_at,
        resources=tuple(
            PitchApiSnapshotResourceIdentityV1(
                item.resource_ref, item.raw_sha256, item.normalized_sha256
            )
            for item in resources
        ),
        canonical_mapping_sha256=mapping_sha,
        adapter_version=_ADAPTER_VERSION,
        configuration_sha256=policy_sha,
        code_git_sha=_git_sha(),
    )
    evaluation_targets = sum(
        cast(int, summary["eligible_targets"])
        for summary in season_summaries
        if summary["role"] == "evaluation"
    )
    role_sets = {
        role: {
            match_id
            for summary in season_summaries
            if summary["role"] == role
            for match_id in cast(list[str], target_plans[str(summary["scope_key"])]["match_ids"])
        }
        for role in ("development", "evaluation")
    }
    firewall_status = "PASS" if not role_sets["development"] & role_sets["evaluation"] else "FAIL"
    if evaluation_targets < 500 or firewall_status != "PASS":
        raise SnapshotStop("CORPUS_OR_FIREWALL_GATE_FAILED")
    corpus_document = {
        "contract": "PitchApiRetrospectiveCorpusPreparationV1",
        "evaluation_protocol_id": "PITCHAPI_RETROSPECTIVE_EVALUATION_V1",
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_sha256": snapshot.sha256,
        "groups": season_summaries,
        "target_plans": target_plans,
        "exact_evaluation_targets": evaluation_targets,
        "final_admission_authorized": False,
    }
    corpus_bytes = canonical_json_bytes(corpus_document)
    corpus_relative, corpus_sha, _ = store.publish_bytes("manifests", corpus_bytes)
    firewall_document = {
        "contract": "PitchApiFirewallPreparationV1",
        "status": firewall_status,
        "strict_prior_kickoff": True,
        "same_kickoff_batching": True,
        "development_evaluation_intersection": len(
            role_sets["development"] & role_sets["evaluation"]
        ),
        "protected_scope_intersection": 0,
        "protected_scope_basis": ["sprint2:epl"],
        "limitation": "cross-provider canonical overlap requires final corpus-admission review",
    }
    firewall_relative, firewall_sha, _ = store.publish_bytes(
        "manifests", canonical_json_bytes(firewall_document)
    )
    snapshot_document = {
        **snapshot.to_dict(),
        "snapshot_sha256": snapshot.sha256,
        "resources": [
            item.to_dict() for item in sorted(resources, key=lambda value: value.resource_ref)
        ],
        "mapping_manifest": mapping_relative,
        "corpus_manifest": corpus_relative,
        "corpus_sha256": corpus_sha,
        "firewall_manifest": firewall_relative,
        "firewall_sha256": firewall_sha,
        "dependency_lock_sha256": _dependency_lock_sha256(),
    }
    snapshot_relative, document_sha, _ = store.publish_bytes(
        "manifests", canonical_json_bytes(snapshot_document)
    )
    result = {
        "contract": "PitchApiSnapshotV1AcquisitionReportV1",
        "status": "COMPLETED",
        "snapshot_id": str(snapshot.snapshot_id),
        "snapshot_sha256": snapshot.sha256,
        "snapshot_document_sha256": document_sha,
        "snapshot_manifest": snapshot_relative,
        "corpus_sha256": corpus_sha,
        "firewall_sha256": firewall_sha,
        "firewall_status": firewall_status,
        "groups": season_summaries,
        "exact_evaluation_targets": evaluation_targets,
        "attempts_used": client.state.attempts,
        "retries_used": client.state.retries,
        "rate_limit_responses": client.state.rate_limits,
        "primary_bytes_before_report": store.primary_bytes,
        "configuration_sha256": policy_sha,
        "code_git_sha": _git_sha(),
        "evaluation_execution_authorized": False,
    }
    store.publish_bytes("reports", canonical_json_bytes(result))
    backup_sha, total_bytes = store.seal_backup()
    result["backup_inventory_sha256"] = backup_sha
    result["total_primary_and_backup_bytes"] = total_bytes
    _write_result(store.root, result)
    return result


def _register_fixture_mappings(
    mappings: dict[tuple[str, str], str], selection: PilotManifestSelection
) -> None:
    for match in selection.ordered_matches:
        match_id = str(match["id"])
        _mapping(mappings, "match", match_id)
        for side in ("home_team", "away_team"):
            team = match.get(side)
            if not isinstance(team, Mapping):
                raise SnapshotStop("MALFORMED_TEAM_MAPPING")
            _mapping(mappings, "team", str(team.get("id", "")))


def _mapping(mappings: dict[tuple[str, str], str], kind: str, provider_id: str) -> str:
    if not provider_id:
        raise SnapshotStop("MISSING_PROVIDER_ALIAS")
    key = (kind, provider_id)
    canonical = str(uuid5(_NAMESPACE, f"pitchapi:{kind}:{provider_id}"))
    existing = mappings.setdefault(key, canonical)
    if existing != canonical:
        raise SnapshotStop("PROVIDER_ALIAS_COLLISION")
    return existing


def _target_plan(
    selection: PilotManifestSelection,
    mappings: dict[tuple[str, str], str],
) -> dict[str, object]:
    appearances: Counter[str] = Counter()
    match_ids: list[str] = []
    target_ids: list[str] = []
    exclusions: Counter[str] = Counter()
    batches: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for match in selection.ordered_matches:
        batches[str(match["time_utc"])].append(match)
    for kickoff in sorted(batches):
        batch = batches[kickoff]
        for match in batch:
            canonical_match = mappings[("match", str(match["id"]))]
            match_ids.append(canonical_match)
            home = cast(Mapping[str, object], match["home_team"])
            away = cast(Mapping[str, object], match["away_team"])
            team_ids = (str(home["id"]), str(away["id"]))
            if all(appearances[team_id] >= 10 for team_id in team_ids):
                target_ids.append(canonical_match)
            else:
                exclusions["TEAM_PRIOR_APPEARANCES_LT_10"] += 1
        for match in batch:
            home = cast(Mapping[str, object], match["home_team"])
            away = cast(Mapping[str, object], match["away_team"])
            appearances[str(home["id"])] += 1
            appearances[str(away["id"])] += 1
    return {
        "match_ids": match_ids,
        "target_ids": target_ids,
        "exclusions": dict(sorted(exclusions.items())),
        "target_plan_sha256": hashlib.sha256(canonical_json_bytes(target_ids)).hexdigest(),
        "same_kickoff_batch_count": len(batches),
    }


def _shot_count(payload: Mapping[str, Any], expected_match_id: str) -> int:
    data = payload.get("data")
    if not isinstance(data, Mapping) or data.get("match_id") != expected_match_id:
        raise SnapshotStop("SHOT_RESPONSE_MATCH_MISMATCH")
    periods = data.get("periods")
    if not _sequence(periods):
        raise SnapshotStop("MALFORMED_SHOT_RESOURCE")
    total = 0
    for period in cast(Sequence[object], periods):
        if not isinstance(period, Mapping) or not _sequence(period.get("shots")):
            raise SnapshotStop("MALFORMED_SHOT_RESOURCE")
        total += len(cast(Sequence[object], period["shots"]))
    return total


def _stop_report(
    store: Store, client: Client, code: str, started_at: datetime
) -> dict[str, object]:
    return {
        "contract": "PitchApiSnapshotV1AcquisitionStopV1",
        "status": "STOPPED",
        "stop_code": code,
        "started_at": started_at.isoformat(),
        "stopped_at": datetime.now(UTC).isoformat(),
        "attempts_used": client.state.attempts,
        "retries_used": client.state.retries,
        "rate_limit_responses": client.state.rate_limits,
        "primary_bytes": store.primary_bytes,
        "hard_attempt_ceiling": _ATTEMPT_CEILING,
        "hard_storage_ceiling_bytes": _HARD_STORAGE_BYTES,
        "partial_acquisition_is_snapshot": False,
        "owner_review_required": True,
    }


def _write_stop_report(root: Path, report: Mapping[str, object]) -> None:
    path = root / "STOPPED.json"
    path.write_bytes(canonical_json_bytes(report) + b"\n")


def _write_result(root: Path, result: Mapping[str, object]) -> None:
    (root / "RESULT.json").write_bytes(canonical_json_bytes(result) + b"\n")


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


def _retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> list[dict[str, object]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def _tree_size(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def main() -> int:
    try:
        secret = _read_env_secret(Path(".env"), _TOKEN_NAME)
        report = acquire(secret)
    except (PilotStop, SnapshotStop) as error:
        print(json.dumps({"status": "STOPPED", "stop_code": error.code}, sort_keys=True))
        return 2
    finally:
        if "secret" in locals():
            del secret
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
