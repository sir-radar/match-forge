from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from football.contracts.source import canonical_json_bytes
from football.forecasting.governance import EvaluationCorpusV1
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION
from football.storage.parquet import ImmutableEventParquetStore, ParquetPublicationError

_PASS_EVENT_TYPE_ID = "30"
_PASS_EVENT_TYPE_NAME = "Pass"
_CORNER_PASS_TYPE_ID = 61
_CORNER_PASS_TYPE_NAME = "Corner"
CORNER_LABEL_VERSION = "statsbomb-pass-type-61-corner-v1"
_CLAIM_NAMESPACE = UUID("831d32a8-ae80-4997-b809-4e935f70e26c")


class CornerLabelError(RuntimeError):
    """A corner outcome label cannot be resolved from exact normalized evidence."""


@dataclass(frozen=True, slots=True)
class CornerCountsV1:
    home_corners: int
    away_corners: int
    event_ids: tuple[str, ...]

    @property
    def total_events(self) -> int:
        return self.home_corners + self.away_corners


@dataclass(frozen=True, slots=True)
class CornerLabelPublicationResult:
    dataset_version_id: UUID
    labels: int
    corner_events: int
    status: str


@dataclass(frozen=True, slots=True)
class _Source:
    lifecycle_claim_id: UUID
    match_id: UUID
    match_observation_id: UUID
    dataset_version_id: UUID
    source_snapshot_id: UUID
    source_resource_id: UUID
    dataset_file_id: UUID
    validation_run_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    known_from: datetime
    relative_path: str
    physical_sha256: str
    logical_sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class _Claim:
    id: UUID
    sha256: str
    source: _Source
    counts: CornerCountsV1
    evidence: dict[str, object]


class Sprint2CornerLabelPublisher:
    """Publish immutable match corner outcomes from validated normalized events."""

    def __init__(self, connection: Connection[Any], data_root: Path) -> None:
        self._connection = connection
        self._data_root = data_root.resolve()

    def publish(self, corpus: EvaluationCorpusV1 | None = None) -> CornerLabelPublicationResult:
        requested = corpus or EvaluationCorpusV1()
        with self._connection.transaction(), self._connection.cursor() as cursor:
            season_id = _resolve_season(cursor, requested)
            sources = _source_rows(cursor, season_id)
            dataset_version_id = _require_complete_dataset(cursor, season_id, sources)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"corner-labels:{dataset_version_id}:{CORNER_LABEL_VERSION}",),
            )
            claims = tuple(self._build_claim(source) for source in sources)
            inserted = sum(_register_claim(cursor, claim) for claim in claims)
        if inserted == len(claims):
            status = "published"
        elif inserted == 0:
            status = "verified_existing"
        else:
            raise CornerLabelError("corner label publication is partially registered")
        return CornerLabelPublicationResult(
            dataset_version_id=dataset_version_id,
            labels=len(claims),
            corner_events=sum(claim.counts.total_events for claim in claims),
            status=status,
        )

    def _build_claim(self, source: _Source) -> _Claim:
        path = self._data_root.joinpath(*source.relative_path.split("/"))
        if not path.is_file() or path.is_symlink() or _sha256_path(path) != source.physical_sha256:
            raise CornerLabelError(f"event dataset checksum mismatch: {source.relative_path}")
        try:
            rows = ImmutableEventParquetStore(self._data_root).read_rows(source.relative_path)
        except ParquetPublicationError as error:
            raise CornerLabelError(f"event dataset is invalid: {source.relative_path}") from error
        if len(rows) != source.row_count:
            raise CornerLabelError(f"event dataset row count conflicts: {source.relative_path}")
        counts = extract_statsbomb_corner_counts(
            rows, source.match_id, source.home_team_id, source.away_team_id
        )
        evidence: dict[str, object] = {
            "contract": "MatchCornerLabelEvidenceV1",
            "rule": {
                "provider_event_type_id": _PASS_EVENT_TYPE_ID,
                "provider_event_type_name": _PASS_EVENT_TYPE_NAME,
                "provider_pass_type_id": _CORNER_PASS_TYPE_ID,
                "provider_pass_type_name": _CORNER_PASS_TYPE_NAME,
            },
            "dataset_file_path": source.relative_path,
            "dataset_file_physical_sha256": source.physical_sha256,
            "dataset_file_logical_sha256": source.logical_sha256,
            "dataset_file_row_count": source.row_count,
            "home_corners": counts.home_corners,
            "away_corners": counts.away_corners,
            "corner_event_ids": list(counts.event_ids),
        }
        identity = {
            "claim_version": CORNER_LABEL_VERSION,
            "match_id": str(source.match_id),
            "lifecycle_claim_id": str(source.lifecycle_claim_id),
            "match_observation_id": str(source.match_observation_id),
            "dataset_version_id": str(source.dataset_version_id),
            "source_snapshot_id": str(source.source_snapshot_id),
            "source_resource_id": str(source.source_resource_id),
            "dataset_file_id": str(source.dataset_file_id),
            "validation_run_id": str(source.validation_run_id),
            "home_team_id": str(source.home_team_id),
            "away_team_id": str(source.away_team_id),
            "evidence": evidence,
        }
        digest = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        return _Claim(uuid5(_CLAIM_NAMESPACE, digest), digest, source, counts, evidence)


def extract_statsbomb_corner_counts(
    rows: Sequence[Mapping[str, Any]],
    match_id: UUID,
    home_team_id: UUID,
    away_team_id: UUID,
) -> CornerCountsV1:
    """Count exact StatsBomb corner-pass events for one canonical match."""
    if home_team_id == away_team_id:
        raise CornerLabelError("corner label match participants must be distinct")
    home_corners = 0
    away_corners = 0
    event_ids: list[str] = []
    seen_event_ids: set[str] = set()
    for row in rows:
        if str(row.get("canonical_match_id")) != str(match_id):
            raise CornerLabelError("corner label row belongs to a different canonical match")
        payload = _provider_payload(row)
        pass_value = payload.get("pass")
        pass_payload = pass_value if isinstance(pass_value, dict) else {}
        type_value = pass_payload.get("type")
        pass_type = type_value if isinstance(type_value, dict) else {}
        pass_type_id = pass_type.get("id")
        pass_type_name = pass_type.get("name")
        has_corner_vocabulary = (
            pass_type_id == _CORNER_PASS_TYPE_ID or pass_type_name == _CORNER_PASS_TYPE_NAME
        )
        is_corner = (
            row.get("provider_event_type_id") == _PASS_EVENT_TYPE_ID
            and row.get("provider_event_type_name") == _PASS_EVENT_TYPE_NAME
            and pass_type_id == _CORNER_PASS_TYPE_ID
            and pass_type_name == _CORNER_PASS_TYPE_NAME
        )
        if has_corner_vocabulary and not is_corner:
            raise CornerLabelError("StatsBomb corner vocabulary conflicts with exact rule")
        if not is_corner:
            continue
        event_id = str(row.get("canonical_event_id") or "")
        if not event_id or event_id in seen_event_ids:
            raise CornerLabelError("corner event identity is missing or duplicated")
        seen_event_ids.add(event_id)
        team_id = str(row.get("canonical_team_id") or "")
        if team_id == str(home_team_id):
            home_corners += 1
        elif team_id == str(away_team_id):
            away_corners += 1
        else:
            raise CornerLabelError("corner event team is not a match participant")
        event_ids.append(event_id)
    return CornerCountsV1(home_corners, away_corners, tuple(event_ids))


def _resolve_season(cursor: Cursor[Any], corpus: EvaluationCorpusV1) -> UUID:
    rows = cursor.execute(
        """
        SELECT season.id
        FROM football.season_provider_mappings AS mapping
        JOIN football.providers AS provider ON provider.id = mapping.provider_id
        JOIN football.seasons AS season ON season.id = mapping.season_id
        WHERE provider.code = %s
          AND mapping.provider_competition_id = %s
          AND mapping.provider_season_id = %s
          AND mapping.valid_to IS NULL
        ORDER BY season.id
        """,
        (
            corpus.provider_code,
            str(corpus.provider_competition_id),
            str(corpus.provider_season_id),
        ),
    ).fetchall()
    if len(rows) != 1:
        raise CornerLabelError("approved corpus does not map to one canonical season")
    return UUID(str(rows[0][0]))


def _source_rows(cursor: Cursor[Any], season_id: UUID) -> tuple[_Source, ...]:
    rows = cursor.execute(
        """
        SELECT DISTINCT ON (claim.match_id)
               claim.id, claim.match_id, claim.match_observation_id,
               claim.dataset_version_id, claim.source_snapshot_id,
               claim.source_resource_id, claim.dataset_file_id,
               claim.validation_run_id, observation.home_team_id,
               observation.away_team_id, claim.known_from, file.relative_path,
               file.physical_sha256, file.logical_sha256, file.row_count
        FROM football.match_lifecycle_claims AS claim
        JOIN football.matches AS match ON match.id = claim.match_id
        JOIN football.match_observations AS observation
          ON observation.id = claim.match_observation_id
        JOIN football.dataset_files AS file ON file.id = claim.dataset_file_id
        WHERE match.season_id = %s
          AND claim.claim_version = %s
          AND claim.lifecycle = 'completed'
        ORDER BY claim.match_id, claim.known_from DESC, claim.created_at DESC, claim.id DESC
        """,
        (season_id, LIFECYCLE_CLAIM_VERSION),
    ).fetchall()
    return tuple(
        _Source(
            lifecycle_claim_id=UUID(str(row[0])),
            match_id=UUID(str(row[1])),
            match_observation_id=UUID(str(row[2])),
            dataset_version_id=UUID(str(row[3])),
            source_snapshot_id=UUID(str(row[4])),
            source_resource_id=UUID(str(row[5])),
            dataset_file_id=UUID(str(row[6])),
            validation_run_id=UUID(str(row[7])),
            home_team_id=UUID(str(row[8])),
            away_team_id=UUID(str(row[9])),
            known_from=row[10],
            relative_path=str(row[11]),
            physical_sha256=str(row[12]),
            logical_sha256=str(row[13]),
            row_count=int(row[14]),
        )
        for row in rows
    )


def _require_complete_dataset(
    cursor: Cursor[Any], season_id: UUID, sources: tuple[_Source, ...]
) -> UUID:
    expected_row = cursor.execute(
        "SELECT count(*) FROM football.matches WHERE season_id = %s", (season_id,)
    ).fetchone()
    expected = int(expected_row[0]) if expected_row is not None else -1
    if not sources or len(sources) != expected:
        raise CornerLabelError(
            f"lifecycle evidence covers {len(sources)} of {expected} corpus matches"
        )
    dataset_ids = {source.dataset_version_id for source in sources}
    if len(dataset_ids) != 1:
        raise CornerLabelError("corner labels do not resolve to one complete event dataset")
    return dataset_ids.pop()


def _register_claim(cursor: Cursor[Any], claim: _Claim) -> int:
    source = claim.source
    inserted = cursor.execute(
        """
        INSERT INTO football.match_corner_labels
            (id, match_id, claim_version, claim_sha256, lifecycle_claim_id,
             match_observation_id, dataset_version_id, source_snapshot_id,
             source_resource_id, dataset_file_id, validation_run_id,
             home_team_id, away_team_id, home_corners, away_corners,
             provider_event_type_id, provider_event_type_name,
             provider_pass_type_id, provider_pass_type_name, known_from, evidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (claim_sha256) DO NOTHING
        """,
        (
            claim.id,
            source.match_id,
            CORNER_LABEL_VERSION,
            claim.sha256,
            source.lifecycle_claim_id,
            source.match_observation_id,
            source.dataset_version_id,
            source.source_snapshot_id,
            source.source_resource_id,
            source.dataset_file_id,
            source.validation_run_id,
            source.home_team_id,
            source.away_team_id,
            claim.counts.home_corners,
            claim.counts.away_corners,
            _PASS_EVENT_TYPE_ID,
            _PASS_EVENT_TYPE_NAME,
            _CORNER_PASS_TYPE_ID,
            _CORNER_PASS_TYPE_NAME,
            source.known_from,
            Jsonb(claim.evidence),
        ),
    ).rowcount
    row = cursor.execute(
        """
        SELECT id, match_id, lifecycle_claim_id, match_observation_id,
               dataset_version_id, source_snapshot_id, source_resource_id,
               dataset_file_id, validation_run_id, home_team_id, away_team_id,
               home_corners, away_corners, evidence
        FROM football.match_corner_labels WHERE claim_sha256 = %s
        """,
        (claim.sha256,),
    ).fetchone()
    expected = (
        claim.id,
        source.match_id,
        source.lifecycle_claim_id,
        source.match_observation_id,
        source.dataset_version_id,
        source.source_snapshot_id,
        source.source_resource_id,
        source.dataset_file_id,
        source.validation_run_id,
        source.home_team_id,
        source.away_team_id,
        claim.counts.home_corners,
        claim.counts.away_corners,
        claim.evidence,
    )
    if row != expected:
        raise CornerLabelError(f"match {source.match_id} corner label conflicts")
    return inserted


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provider_payload(row: Mapping[str, Any]) -> dict[str, object]:
    raw = row.get("provider_payload_json")
    if not isinstance(raw, str):
        raise CornerLabelError("corner row lacks provider payload JSON")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CornerLabelError("corner row has malformed provider payload") from error
    if not isinstance(payload, dict):
        raise CornerLabelError("corner row provider payload must be an object")
    return payload
