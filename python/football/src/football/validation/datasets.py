from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from football.contracts.source import canonical_json_bytes
from football.normalization.statsbomb_events import (
    EVENT_SCHEMA_SHA256,
    EVENT_SCHEMA_VERSION,
    NORMALIZER_VERSION,
    logical_sha256,
)
from football.storage.parquet import ImmutableEventParquetStore, ParquetPublicationError
from football.validation.statsbomb import (
    EventFileValidationInput,
    MatchValidationContext,
    PositionStintValidationContext,
    QualityPolicy,
    ValidationFinding,
    make_finding,
    validate_statsbomb_dataset,
)

VALIDATOR_VERSION = "statsbomb-dataset-validator-v3"

_VALIDATION_NAMESPACE = UUID("6f57ba57-984c-4c42-877d-d355561742ea")
_DATASET_PATH = re.compile(
    r"^normalized/events/schema=v1/dataset=([0-9a-f-]{36})/"
    r"competition_id=([0-9a-f-]{36})/season_id=([0-9a-f-]{36})/"
    r"match_id=([0-9a-f-]{36})/events\.parquet$"
)


class DatasetValidationError(RuntimeError):
    """Registered dataset cannot be validated safely."""


@dataclass(frozen=True)
class DatasetValidationResult:
    validation_run_id: UUID
    dataset_version_id: UUID
    status: str
    findings: tuple[ValidationFinding, ...]
    registration_status: str


@dataclass(frozen=True)
class _Dataset:
    dataset_version_id: UUID
    source_snapshot_id: UUID
    provider_id: UUID
    acquired_at: datetime
    manifest_sha256: str
    files: tuple[_DatasetFile, ...]


@dataclass(frozen=True)
class _DatasetFile:
    dataset_file_id: UUID
    relative_path: str
    physical_sha256: str
    logical_sha256: str
    row_count: int
    size_bytes: int
    match_id: UUID
    source_resource_id: UUID
    match: MatchValidationContext


class StatsBombDatasetValidator:
    def __init__(
        self,
        connection: Connection[Any],
        data_root: Path,
        policy: QualityPolicy,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()
        self._policy = policy
        self._clock = clock or (lambda: datetime.now(UTC))

    def validate(self, dataset_version_id: UUID) -> DatasetValidationResult:
        started_at = self._clock()
        _require_aware_time(started_at)
        with self._connection.transaction(), self._connection.cursor() as cursor:
            dataset = _resolve_dataset(cursor, dataset_version_id)
            source_findings = _player_fact_findings(cursor, dataset, self._policy)
        inputs, findings = self._read_files(dataset)
        findings.extend(source_findings)
        findings.extend(validate_statsbomb_dataset(inputs, self._policy))
        ordered = tuple(
            sorted(
                findings,
                key=lambda finding: canonical_json_bytes(_finding_key_payload(finding)),
            )
        )
        status = _status(ordered)
        identity_hash = _run_identity(dataset, self._policy)
        run_id = uuid5(_VALIDATION_NAMESPACE, f"validation:{identity_hash}")
        completed_at = self._clock()
        _require_aware_time(completed_at)
        if completed_at < started_at:
            raise DatasetValidationError("validation clock moved backwards")
        with self._connection.transaction(), self._connection.cursor() as cursor:
            registration_status = _register(
                cursor,
                dataset,
                self._policy,
                run_id,
                identity_hash,
                status,
                started_at,
                completed_at,
                ordered,
            )
        return DatasetValidationResult(
            validation_run_id=run_id,
            dataset_version_id=dataset.dataset_version_id,
            status=status,
            findings=ordered,
            registration_status=registration_status,
        )

    def _read_files(
        self, dataset: _Dataset
    ) -> tuple[tuple[EventFileValidationInput, ...], list[ValidationFinding]]:
        store = ImmutableEventParquetStore(self._data_root)
        inputs: list[EventFileValidationInput] = []
        findings: list[ValidationFinding] = []
        for file in dataset.files:
            try:
                rows = store.read_rows(file.relative_path)
            except (OSError, ValueError, ParquetPublicationError):
                integrity = _physical_integrity_evidence(self._data_root, file)
                if integrity is not None:
                    findings.append(
                        make_finding(
                            self._policy,
                            "SB_DATASET_FILE_INTEGRITY",
                            "file",
                            f"event dataset file conflicts with its registry: {file.relative_path}",
                            integrity,
                            dataset_file_id=file.dataset_file_id,
                            source_resource_id=file.source_resource_id,
                        )
                    )
                    continue
                findings.append(
                    make_finding(
                        self._policy,
                        "SB_MALFORMED_EVENTS_PARQUET",
                        "file",
                        f"event dataset file is not readable Parquet: {file.relative_path}",
                        {"relative_path": file.relative_path},
                        dataset_file_id=file.dataset_file_id,
                        source_resource_id=file.source_resource_id,
                    )
                )
                continue
            integrity = _integrity_evidence(self._data_root, file, rows)
            if integrity is not None:
                findings.append(
                    make_finding(
                        self._policy,
                        "SB_DATASET_FILE_INTEGRITY",
                        "file",
                        f"event dataset file conflicts with its registry: {file.relative_path}",
                        integrity,
                        dataset_file_id=file.dataset_file_id,
                        source_resource_id=file.source_resource_id,
                    )
                )
                continue
            inputs.append(
                EventFileValidationInput(
                    dataset_file_id=file.dataset_file_id,
                    source_resource_id=file.source_resource_id,
                    relative_path=file.relative_path,
                    match=file.match,
                    rows=rows,
                )
            )
        return tuple(inputs), findings


def _player_fact_findings(
    cursor: Cursor[Any], dataset: _Dataset, policy: QualityPolicy
) -> list[ValidationFinding]:
    rows = cursor.execute(
        """
        SELECT fact.provider_player_id, fact.full_name, fact.nickname,
               fact.country_provider_id, fact.nickname_observed,
               fact.country_observed, fact.observation_kind,
               fact.source_resource_id, resource.provider_path
        FROM football.player_source_facts AS fact
        JOIN football.source_resources AS resource
          ON resource.id = fact.source_resource_id
         AND resource.source_snapshot_id = fact.source_snapshot_id
        WHERE fact.source_snapshot_id = %s
        ORDER BY fact.provider_player_id, fact.fact_sha256
        """,
        (dataset.source_snapshot_id,),
    ).fetchall()
    players: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        players[str(row[0])].append(row)
    findings: list[ValidationFinding] = []
    fields = (
        ("full_name", 1, None),
        ("nickname", 2, 4),
        ("country_provider_id", 3, 5),
    )
    for provider_player_id, facts in sorted(players.items()):
        for field_name, value_index, observed_index in fields:
            observed = [
                fact for fact in facts if observed_index is None or bool(fact[observed_index])
            ]
            if len({fact[value_index] for fact in observed}) <= 1:
                continue
            variants = [
                {
                    "value": fact[value_index],
                    "observation_kind": str(fact[6]),
                    "source_resource_id": str(fact[7]),
                    "provider_path": str(fact[8]),
                }
                for fact in observed
            ]
            findings.append(
                make_finding(
                    policy,
                    "SB_CONFLICTING_PLAYER_FACT",
                    "dataset",
                    f"player {provider_player_id} has conflicting {field_name} source facts; "
                    "canonical consensus is null",
                    {"field": field_name, "variants": variants},
                    provider_entity_id=provider_player_id,
                    field_path=f"player.{field_name}",
                )
            )
    return findings


def _resolve_dataset(cursor: Cursor[Any], dataset_version_id: UUID) -> _Dataset:
    row = cursor.execute(
        """
        SELECT version.source_snapshot_id, snapshot.provider_id, snapshot.acquired_at,
               version.manifest_sha256, provider.code, version.dataset_name,
               version.layer, version.schema_version, version.schema_sha256,
               version.normalizer_version, version.status
        FROM football.dataset_versions AS version
        JOIN football.source_snapshots AS snapshot ON snapshot.id = version.source_snapshot_id
        JOIN football.providers AS provider ON provider.id = snapshot.provider_id
        WHERE version.id = %s
        """,
        (dataset_version_id,),
    ).fetchone()
    expected_contract = (
        "statsbomb_open_data",
        "events",
        "normalized",
        EVENT_SCHEMA_VERSION,
        EVENT_SCHEMA_SHA256,
        NORMALIZER_VERSION,
        "published",
    )
    if row is None or row[4:] != expected_contract:
        raise DatasetValidationError(
            "validation requires a published StatsBomb normalized event dataset"
        )
    source_snapshot_id = UUID(str(row[0]))
    provider_id = UUID(str(row[1]))
    acquired_at = row[2]
    if not isinstance(acquired_at, datetime):
        raise DatasetValidationError("dataset source snapshot has invalid acquisition time")
    raw_files = list(
        cursor.execute(
            """
            SELECT id, relative_path, physical_sha256, logical_sha256,
                   row_count, size_bytes, schema_sha256
            FROM football.dataset_files
            WHERE dataset_version_id = %s
            ORDER BY relative_path
            """,
            (dataset_version_id,),
        )
    )
    if not raw_files:
        raise DatasetValidationError("event dataset has no registered files")
    files = tuple(
        _resolve_file(
            cursor,
            dataset_version_id,
            source_snapshot_id,
            provider_id,
            acquired_at,
            file,
        )
        for file in raw_files
    )
    return _Dataset(
        dataset_version_id=dataset_version_id,
        source_snapshot_id=source_snapshot_id,
        provider_id=provider_id,
        acquired_at=acquired_at,
        manifest_sha256=str(row[3]),
        files=files,
    )


def _resolve_file(
    cursor: Cursor[Any],
    dataset_version_id: UUID,
    source_snapshot_id: UUID,
    provider_id: UUID,
    acquired_at: datetime,
    row: tuple[Any, ...],
) -> _DatasetFile:
    relative_path = str(row[1])
    match = _DATASET_PATH.fullmatch(relative_path)
    if match is None or UUID(match.group(1)) != dataset_version_id:
        raise DatasetValidationError(
            f"event dataset file has invalid partition path: {relative_path}"
        )
    match_id = UUID(match.group(4))
    if str(row[6]) != EVENT_SCHEMA_SHA256:
        raise DatasetValidationError(f"event dataset file has invalid schema hash: {relative_path}")
    source_row = cursor.execute(
        """
        SELECT DISTINCT provider_match_id, source_resource_id
        FROM football.event_observations
        WHERE source_snapshot_id = %s AND provider_id = %s AND match_id = %s
        """,
        (source_snapshot_id, provider_id, match_id),
    ).fetchall()
    if len(source_row) != 1:
        raise DatasetValidationError(
            f"event dataset file lacks exact event catalogue lineage: {relative_path}"
        )
    provider_match_id = str(source_row[0][0])
    source_resource_id = UUID(str(source_row[0][1]))
    context = _match_context(
        cursor,
        match_id,
        provider_match_id,
        provider_id,
        acquired_at,
    )
    return _DatasetFile(
        dataset_file_id=UUID(str(row[0])),
        relative_path=relative_path,
        physical_sha256=str(row[2]),
        logical_sha256=str(row[3]),
        row_count=int(row[4]),
        size_bytes=int(row[5]),
        match_id=match_id,
        source_resource_id=source_resource_id,
        match=context,
    )


def _match_context(
    cursor: Cursor[Any],
    match_id: UUID,
    provider_match_id: str,
    provider_id: UUID,
    knowledge_cutoff: datetime,
) -> MatchValidationContext:
    observations = cursor.execute(
        """
        SELECT home_team_id, away_team_id, home_score, away_score
        FROM football.match_observations
        WHERE match_id = %s AND provider_id = %s
          AND football.known_at(known_from, known_to, %s)
        ORDER BY known_from DESC
        """,
        (match_id, provider_id, knowledge_cutoff),
    ).fetchall()
    if len(observations) != 1 or observations[0][0] is None or observations[0][1] is None:
        raise DatasetValidationError(
            f"match metadata is unavailable at dataset cutoff: {provider_match_id}"
        )
    lineup: dict[UUID, set[UUID]] = defaultdict(set)
    lineup_rows = cursor.execute(
        """
        SELECT team.team_id,
               CASE WHEN player_observation.id IS NULL THEN NULL ELSE player.player_id END
        FROM football.match_team_participations AS team
        JOIN football.match_team_participation_observations AS team_observation
          ON team_observation.match_team_participation_id = team.id
         AND team_observation.provider_id = %s
         AND football.known_at(
             team_observation.known_from, team_observation.known_to, %s
         )
        LEFT JOIN football.match_player_participations AS player
          ON player.match_team_participation_id = team.id
        LEFT JOIN football.match_player_participation_observations AS player_observation
          ON player_observation.match_player_participation_id = player.id
         AND player_observation.provider_id = %s
         AND player_observation.was_in_lineup
         AND football.known_at(
             player_observation.known_from, player_observation.known_to, %s
         )
        WHERE team.match_id = %s
        ORDER BY team.team_id, player.player_id
        """,
        (provider_id, knowledge_cutoff, provider_id, knowledge_cutoff, match_id),
    ).fetchall()
    for team_id, player_id in lineup_rows:
        canonical_team_id = UUID(str(team_id))
        lineup[canonical_team_id]
        if player_id is not None:
            lineup[canonical_team_id].add(UUID(str(player_id)))
    position_rows = cursor.execute(
        """
        SELECT player.player_id, stint.sequence, stint.period_from,
               stint.clock_from, stint.period_to, stint.clock_to
        FROM football.match_team_participations AS team
        JOIN football.match_player_participations AS player
          ON player.match_team_participation_id = team.id
        JOIN football.match_player_participation_observations AS player_observation
          ON player_observation.match_player_participation_id = player.id
         AND player_observation.provider_id = %s
         AND football.known_at(
             player_observation.known_from, player_observation.known_to, %s
         )
        JOIN football.player_position_stints AS stint
          ON stint.match_player_observation_id = player_observation.id
        WHERE team.match_id = %s
        ORDER BY player.player_id, stint.sequence
        """,
        (provider_id, knowledge_cutoff, match_id),
    ).fetchall()
    positions = tuple(_position_context(row) for row in position_rows)
    observation = observations[0]
    return MatchValidationContext(
        canonical_match_id=match_id,
        provider_match_id=provider_match_id,
        home_team_id=UUID(str(observation[0])),
        away_team_id=UUID(str(observation[1])),
        home_score=int(observation[2]) if observation[2] is not None else None,
        away_score=int(observation[3]) if observation[3] is not None else None,
        lineup_players={team: frozenset(players) for team, players in lineup.items()},
        position_stints=positions,
    )


def _position_context(row: tuple[Any, ...]) -> PositionStintValidationContext:
    clock_from = row[3]
    clock_to = row[5]
    if not isinstance(clock_from, timedelta) or (
        clock_to is not None and not isinstance(clock_to, timedelta)
    ):
        raise DatasetValidationError("lineup position stint has invalid clock storage")
    return PositionStintValidationContext(
        canonical_player_id=UUID(str(row[0])),
        sequence=int(row[1]),
        period_from=int(row[2]),
        clock_from=clock_from,
        period_to=int(row[4]) if row[4] is not None else None,
        clock_to=clock_to,
    )


def _integrity_evidence(
    data_root: Path,
    file: _DatasetFile,
    rows: tuple[dict[str, Any], ...],
) -> dict[str, Any] | None:
    physical = _physical_integrity_evidence(data_root, file)
    if physical is not None:
        return physical
    actual = {"logical_sha256": logical_sha256(rows), "row_count": len(rows)}
    expected = {
        "logical_sha256": file.logical_sha256,
        "row_count": file.row_count,
    }
    if actual == expected:
        return None
    return {"relative_path": file.relative_path, "expected": expected, "actual": actual}


def _physical_integrity_evidence(
    data_root: Path,
    file: _DatasetFile,
) -> dict[str, Any] | None:
    path = data_root.joinpath(*file.relative_path.split("/"))
    expected = {
        "regular_file": True,
        "physical_sha256": file.physical_sha256,
        "size_bytes": file.size_bytes,
    }
    if path.is_symlink() or not path.is_file():
        actual: dict[str, Any] = {
            "regular_file": False,
            "physical_sha256": None,
            "size_bytes": None,
        }
    else:
        try:
            actual = {
                "regular_file": True,
                "physical_sha256": _sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
        except OSError:
            actual = {
                "regular_file": False,
                "physical_sha256": None,
                "size_bytes": None,
            }
    if actual == expected:
        return None
    return {"relative_path": file.relative_path, "expected": expected, "actual": actual}


def _run_identity(dataset: _Dataset, policy: QualityPolicy) -> str:
    payload = canonical_json_bytes(
        {
            "dataset_version_id": str(dataset.dataset_version_id),
            "dataset_manifest_sha256": dataset.manifest_sha256,
            "policy_version": policy.version,
            "policy_sha256": policy.sha256,
            "validator_version": VALIDATOR_VERSION,
        }
    )
    return hashlib.sha256(payload).hexdigest()


def _status(findings: tuple[ValidationFinding, ...]) -> str:
    severities = {finding.severity for finding in findings}
    if "FATAL" in severities:
        return "failed"
    if "QUARANTINE" in severities:
        return "quarantined"
    if "WARNING" in severities:
        return "warnings"
    return "passed"


def _register(
    cursor: Cursor[Any],
    dataset: _Dataset,
    policy: QualityPolicy,
    run_id: UUID,
    identity_hash: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    findings: tuple[ValidationFinding, ...],
) -> str:
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"validation:{identity_hash}",),
    )
    inserted = cursor.execute(
        """
        INSERT INTO football.validation_runs
            (id, dataset_version_id, source_snapshot_id, identity_hash,
             policy_version, policy_sha256, validator_version, status,
             started_at, completed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (identity_hash) DO NOTHING
        """,
        (
            run_id,
            dataset.dataset_version_id,
            dataset.source_snapshot_id,
            identity_hash,
            policy.version,
            policy.sha256,
            VALIDATOR_VERSION,
            status,
            started_at,
            completed_at,
        ),
    ).rowcount
    registered_started_at = started_at
    registered_completed_at = completed_at
    if inserted == 0:
        existing_times = cursor.execute(
            """
            SELECT started_at, completed_at FROM football.validation_runs
            WHERE identity_hash = %s
            """,
            (identity_hash,),
        ).fetchone()
        if existing_times is None or existing_times[1] < existing_times[0]:
            raise DatasetValidationError("validation run has invalid registered timestamps")
        registered_started_at = existing_times[0]
        registered_completed_at = existing_times[1]
    expected_findings = tuple(
        _register_finding(cursor, dataset, run_id, registered_completed_at, finding)
        for finding in findings
    )
    _verify_registration(
        cursor,
        dataset,
        policy,
        run_id,
        identity_hash,
        status,
        registered_started_at,
        registered_completed_at,
        expected_findings,
    )
    return "registered" if inserted == 1 else "verified_registered"


def _register_finding(
    cursor: Cursor[Any],
    dataset: _Dataset,
    run_id: UUID,
    completed_at: datetime,
    finding: ValidationFinding,
) -> tuple[Any, ...]:
    key_payload = _finding_key_payload(finding)
    finding_key = hashlib.sha256(
        canonical_json_bytes({"validation_run_id": str(run_id), **key_payload})
    ).hexdigest()
    finding_id = uuid5(_VALIDATION_NAMESPACE, f"finding:{run_id}:{finding_key}")
    values = (
        finding_id,
        run_id,
        dataset.dataset_version_id,
        dataset.source_snapshot_id,
        finding.dataset_file_id,
        finding.source_resource_id,
        finding_key,
        finding.rule_code,
        finding.severity,
        finding.action,
        finding.scope_type,
        finding.provider_entity_id,
        finding.field_path,
        finding.message,
        finding.evidence,
        completed_at,
    )
    cursor.execute(
        """
        INSERT INTO football.validation_findings
            (id, validation_run_id, dataset_version_id, source_snapshot_id,
             dataset_file_id, source_resource_id, finding_key, rule_code,
             severity, action, scope_type, provider_entity_id, field_path,
             message, evidence, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (finding_key) DO NOTHING
        """,
        (*values[:14], Jsonb(finding.evidence), completed_at),
    )
    return values


def _verify_registration(
    cursor: Cursor[Any],
    dataset: _Dataset,
    policy: QualityPolicy,
    run_id: UUID,
    identity_hash: str,
    status: str,
    started_at: datetime,
    completed_at: datetime,
    expected_findings: tuple[tuple[Any, ...], ...],
) -> None:
    run = cursor.execute(
        """
        SELECT id, dataset_version_id, source_snapshot_id, identity_hash,
               policy_version, policy_sha256, validator_version, status,
               started_at, completed_at
        FROM football.validation_runs WHERE identity_hash = %s
        """,
        (identity_hash,),
    ).fetchone()
    expected_run = (
        run_id,
        dataset.dataset_version_id,
        dataset.source_snapshot_id,
        identity_hash,
        policy.version,
        policy.sha256,
        VALIDATOR_VERSION,
        status,
        started_at,
        completed_at,
    )
    if run != expected_run:
        raise DatasetValidationError("validation run conflicts with immutable registration")
    registered = tuple(
        cursor.execute(
            """
            SELECT id, validation_run_id, dataset_version_id, source_snapshot_id,
                   dataset_file_id, source_resource_id, finding_key, rule_code,
                   severity, action, scope_type, provider_entity_id, field_path,
                   message, evidence, created_at
            FROM football.validation_findings
            WHERE validation_run_id = %s
            ORDER BY finding_key
            """,
            (run_id,),
        ).fetchall()
    )
    if registered != tuple(sorted(expected_findings, key=lambda item: item[6])):
        raise DatasetValidationError("validation findings conflict with immutable registration")


def _finding_key_payload(finding: ValidationFinding) -> dict[str, Any]:
    return {
        "rule_code": finding.rule_code,
        "severity": finding.severity,
        "action": finding.action,
        "scope_type": finding.scope_type,
        "dataset_file_id": str(finding.dataset_file_id) if finding.dataset_file_id else None,
        "source_resource_id": (
            str(finding.source_resource_id) if finding.source_resource_id else None
        ),
        "provider_entity_id": finding.provider_entity_id,
        "field_path": finding.field_path,
        "message": finding.message,
        "evidence": finding.evidence,
    }


def _require_aware_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DatasetValidationError("validation clock must return a timezone-aware datetime")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
