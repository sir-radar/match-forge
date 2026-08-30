from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from football.contracts.source import canonical_json_bytes
from football.forecasting.governance import EvaluationCorpusV1

LIFECYCLE_CLAIM_VERSION = "statsbomb-terminal-event-score-v1"
_VALIDATOR_VERSION = "statsbomb-dataset-validator-v3"
_TERMINAL_EVENT_TYPE = "Half End"
_TERMINAL_PERIOD = 2
_TERMINAL_EVENT_COUNT = 2
_CLAIM_NAMESPACE = UUID("3c01dcae-b54d-4a62-ac7c-f6f6a838ad49")
_DATASET_PATH = re.compile(
    r"^normalized/events/schema=v1/dataset=([0-9a-f-]{36})/"
    r"competition_id=([0-9a-f-]{36})/season_id=([0-9a-f-]{36})/"
    r"match_id=([0-9a-f-]{36})/events\.parquet$"
)


class LifecycleClaimError(RuntimeError):
    """A terminal match claim cannot be resolved from exact validated lineage."""


@dataclass(frozen=True, slots=True)
class LifecycleClaimPublicationResult:
    dataset_version_id: UUID
    validation_run_id: UUID
    claims: int
    status: str


@dataclass(frozen=True, slots=True)
class _ResolvedEvidence:
    season_id: UUID
    competition_id: UUID
    provider_id: UUID
    dataset_version_id: UUID
    source_snapshot_id: UUID
    dataset_acquired_at: datetime
    validation_run_id: UUID
    validation_status: str
    validation_completed_at: datetime


@dataclass(frozen=True, slots=True)
class _Claim:
    claim_id: UUID
    claim_sha256: str
    match_id: UUID
    match_observation_id: UUID
    dataset_file_id: UUID
    source_resource_id: UUID
    terminal_event_count: int
    max_period: int
    evidence: dict[str, object]


class Sprint2LifecycleClaimPublisher:
    """Publish immutable completion claims from score-reconciled terminal event streams."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def publish(self, corpus: EvaluationCorpusV1 | None = None) -> LifecycleClaimPublicationResult:
        requested = corpus or EvaluationCorpusV1()
        with self._connection.transaction(), self._connection.cursor() as cursor:
            resolved = _resolve_evidence(cursor, requested)
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"lifecycle-claims:{resolved.dataset_version_id}",),
            )
            claims = _build_claims(cursor, resolved)
            inserted = sum(_register_claim(cursor, resolved, claim) for claim in claims)
        if inserted == len(claims):
            status = "published"
        elif inserted == 0:
            status = "verified_existing"
        else:
            raise LifecycleClaimError("lifecycle claim publication is partially registered")
        return LifecycleClaimPublicationResult(
            dataset_version_id=resolved.dataset_version_id,
            validation_run_id=resolved.validation_run_id,
            claims=len(claims),
            status=status,
        )


def _resolve_evidence(cursor: Cursor[Any], corpus: EvaluationCorpusV1) -> _ResolvedEvidence:
    rows = cursor.execute(
        """
        SELECT season.id, season.competition_id, provider.id, dataset.id,
               dataset.source_snapshot_id, snapshot.acquired_at, validation.id,
               validation.status, validation.completed_at
        FROM football.season_provider_mappings AS mapping
        JOIN football.providers AS provider ON provider.id = mapping.provider_id
        JOIN football.seasons AS season ON season.id = mapping.season_id
        JOIN football.dataset_versions AS dataset
          ON dataset.dataset_name = 'events'
         AND dataset.layer = 'normalized'
         AND dataset.status = 'published'
        JOIN football.source_snapshots AS snapshot
          ON snapshot.id = dataset.source_snapshot_id
         AND snapshot.provider_id = provider.id
        JOIN football.validation_runs AS validation
          ON validation.dataset_version_id = dataset.id
         AND validation.source_snapshot_id = dataset.source_snapshot_id
         AND validation.validator_version = %s
         AND validation.status IN ('passed', 'warnings')
        WHERE provider.code = %s
          AND mapping.provider_competition_id = %s
          AND mapping.provider_season_id = %s
          AND mapping.valid_to IS NULL
          AND EXISTS (
              SELECT 1
              FROM football.event_observations AS event
              JOIN football.matches AS match ON match.id = event.match_id
              WHERE event.source_snapshot_id = dataset.source_snapshot_id
                AND match.season_id = season.id
          )
        ORDER BY snapshot.acquired_at DESC, dataset.published_at DESC,
                 validation.completed_at DESC, dataset.id DESC
        LIMIT 2
        """,
        (
            _VALIDATOR_VERSION,
            corpus.provider_code,
            str(corpus.provider_competition_id),
            str(corpus.provider_season_id),
        ),
    ).fetchall()
    if not rows:
        raise LifecycleClaimError("approved corpus lacks passed or warning validator v3 evidence")
    first = rows[0]
    return _ResolvedEvidence(
        season_id=UUID(str(first[0])),
        competition_id=UUID(str(first[1])),
        provider_id=UUID(str(first[2])),
        dataset_version_id=UUID(str(first[3])),
        source_snapshot_id=UUID(str(first[4])),
        dataset_acquired_at=first[5],
        validation_run_id=UUID(str(first[6])),
        validation_status=str(first[7]),
        validation_completed_at=first[8],
    )


def _build_claims(cursor: Cursor[Any], resolved: _ResolvedEvidence) -> tuple[_Claim, ...]:
    files = cursor.execute(
        """
        SELECT id, relative_path
        FROM football.dataset_files
        WHERE dataset_version_id = %s
        ORDER BY relative_path
        """,
        (resolved.dataset_version_id,),
    ).fetchall()
    claims = tuple(_claim_from_file(cursor, resolved, row) for row in files)
    expected_row = cursor.execute(
        "SELECT count(*) FROM football.matches WHERE season_id = %s",
        (resolved.season_id,),
    ).fetchone()
    expected = int(expected_row[0]) if expected_row is not None else -1
    if not claims or len(claims) != expected:
        raise LifecycleClaimError(
            f"validated event files cover {len(claims)} of {expected} corpus matches"
        )
    if len({claim.match_id for claim in claims}) != len(claims):
        raise LifecycleClaimError("validated event files contain duplicate matches")
    return claims


def _claim_from_file(
    cursor: Cursor[Any], resolved: _ResolvedEvidence, file_row: tuple[Any, ...]
) -> _Claim:
    dataset_file_id = UUID(str(file_row[0]))
    relative_path = str(file_row[1])
    match = _DATASET_PATH.fullmatch(relative_path)
    if match is None or UUID(match.group(1)) != resolved.dataset_version_id:
        raise LifecycleClaimError(f"dataset file has invalid claim path: {relative_path}")
    if (
        UUID(match.group(2)) != resolved.competition_id
        or UUID(match.group(3)) != resolved.season_id
    ):
        raise LifecycleClaimError(f"dataset file is outside approved corpus: {relative_path}")
    match_id = UUID(match.group(4))
    observation = _match_observation(cursor, resolved, match_id)
    source_resource_id, terminal_count, max_period = _terminal_evidence(cursor, resolved, match_id)
    if terminal_count != _TERMINAL_EVENT_COUNT or max_period != _TERMINAL_PERIOD:
        raise LifecycleClaimError(
            f"match {observation[1]} lacks exact regulation terminal evidence"
        )
    evidence = {
        "contract": "MatchLifecycleClaimEvidenceV1",
        "provider_match_id": str(observation[1]),
        "provider_status": observation[4],
        "home_score": int(observation[2]),
        "away_score": int(observation[3]),
        "terminal_event_type": _TERMINAL_EVENT_TYPE,
        "terminal_period": _TERMINAL_PERIOD,
        "terminal_event_count": terminal_count,
        "max_period": max_period,
        "validation_status": resolved.validation_status,
        "validator_version": _VALIDATOR_VERSION,
        "dataset_file_path": relative_path,
    }
    identity = {
        "claim_version": LIFECYCLE_CLAIM_VERSION,
        "lifecycle": "completed",
        "match_id": str(match_id),
        "match_observation_id": str(observation[0]),
        "dataset_version_id": str(resolved.dataset_version_id),
        "source_snapshot_id": str(resolved.source_snapshot_id),
        "source_resource_id": str(source_resource_id),
        "dataset_file_id": str(dataset_file_id),
        "validation_run_id": str(resolved.validation_run_id),
        "evidence": evidence,
    }
    claim_sha256 = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return _Claim(
        claim_id=uuid5(_CLAIM_NAMESPACE, claim_sha256),
        claim_sha256=claim_sha256,
        match_id=match_id,
        match_observation_id=UUID(str(observation[0])),
        dataset_file_id=dataset_file_id,
        source_resource_id=source_resource_id,
        terminal_event_count=terminal_count,
        max_period=max_period,
        evidence=evidence,
    )


def _match_observation(
    cursor: Cursor[Any], resolved: _ResolvedEvidence, match_id: UUID
) -> tuple[Any, ...]:
    rows = cursor.execute(
        """
        SELECT observation.id, observation.provider_match_id,
               observation.home_score, observation.away_score,
               observation.provider_status
        FROM football.match_observations AS observation
        JOIN football.matches AS match ON match.id = observation.match_id
        WHERE observation.match_id = %s
          AND observation.provider_id = %s
          AND match.season_id = %s
          AND football.known_at(
              observation.known_from, observation.known_to, %s
          )
        ORDER BY observation.known_from DESC
        """,
        (match_id, resolved.provider_id, resolved.season_id, resolved.dataset_acquired_at),
    ).fetchall()
    if len(rows) != 1 or rows[0][2] is None or rows[0][3] is None:
        raise LifecycleClaimError(f"match {match_id} lacks one scored observation at cutoff")
    return tuple(rows[0])


def _terminal_evidence(
    cursor: Cursor[Any], resolved: _ResolvedEvidence, match_id: UUID
) -> tuple[UUID, int, int]:
    rows = cursor.execute(
        """
        SELECT source_resource_id,
               count(*) FILTER (
                   WHERE provider_event_type = %s AND period = %s
               ),
               max(period)
        FROM football.event_observations
        WHERE source_snapshot_id = %s AND provider_id = %s AND match_id = %s
        GROUP BY source_resource_id
        """,
        (
            _TERMINAL_EVENT_TYPE,
            _TERMINAL_PERIOD,
            resolved.source_snapshot_id,
            resolved.provider_id,
            match_id,
        ),
    ).fetchall()
    if len(rows) != 1 or rows[0][2] is None:
        raise LifecycleClaimError(f"match {match_id} lacks exact event resource lineage")
    return UUID(str(rows[0][0])), int(rows[0][1]), int(rows[0][2])


def _register_claim(cursor: Cursor[Any], resolved: _ResolvedEvidence, claim: _Claim) -> int:
    inserted = cursor.execute(
        """
        INSERT INTO football.match_lifecycle_claims
            (id, match_id, lifecycle, claim_version, claim_sha256,
             match_observation_id, dataset_version_id, source_snapshot_id,
             source_resource_id, dataset_file_id, validation_run_id, known_from,
             terminal_period, terminal_event_count, max_period, evidence)
        VALUES (%s, %s, 'completed', %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s)
        ON CONFLICT (claim_sha256) DO NOTHING
        """,
        (
            claim.claim_id,
            claim.match_id,
            LIFECYCLE_CLAIM_VERSION,
            claim.claim_sha256,
            claim.match_observation_id,
            resolved.dataset_version_id,
            resolved.source_snapshot_id,
            claim.source_resource_id,
            claim.dataset_file_id,
            resolved.validation_run_id,
            resolved.validation_completed_at,
            _TERMINAL_PERIOD,
            claim.terminal_event_count,
            claim.max_period,
            Jsonb(claim.evidence),
        ),
    ).rowcount
    registered = cursor.execute(
        """
        SELECT id, match_id, match_observation_id, dataset_version_id,
               source_snapshot_id, source_resource_id, dataset_file_id,
               validation_run_id, terminal_event_count, max_period, evidence
        FROM football.match_lifecycle_claims
        WHERE claim_sha256 = %s
        """,
        (claim.claim_sha256,),
    ).fetchone()
    expected = (
        claim.claim_id,
        claim.match_id,
        claim.match_observation_id,
        resolved.dataset_version_id,
        resolved.source_snapshot_id,
        claim.source_resource_id,
        claim.dataset_file_id,
        resolved.validation_run_id,
        claim.terminal_event_count,
        claim.max_period,
        claim.evidence,
    )
    if registered != expected:
        raise LifecycleClaimError(f"match {claim.match_id} lifecycle claim conflicts")
    return inserted
