from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from functools import cache
from importlib import metadata, resources
from io import BytesIO
from typing import Any
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from psycopg import Connection, Cursor
from psycopg.types.json import Jsonb

from football.contracts.source import canonical_json_bytes
from football.forecasting.governance import EvaluationCorpusV1
from football.forecasting.lifecycle import LIFECYCLE_CLAIM_VERSION

KICKOFF_CLAIM_VERSION = "statsbomb-england-local-kickoff-v1"
KICKOFF_TIMEZONE = "Europe/London"
TZDATA_VERSION = "2026.3"
_CLAIM_NAMESPACE = UUID("0a63cfd7-84cd-4d22-82c0-9b61c267d149")
_APPROVED_DOMESTIC_POLICIES = frozenset(
    (
        (KICKOFF_CLAIM_VERSION, "England", KICKOFF_TIMEZONE),
        ("statsbomb-spain-local-kickoff-v1", "Spain", "Europe/Madrid"),
        ("statsbomb-italy-local-kickoff-v1", "Italy", "Europe/Rome"),
    )
)


class KickoffClaimError(RuntimeError):
    """A UTC kickoff cannot be resolved from exact local-time and timezone evidence."""


@dataclass(frozen=True, slots=True)
class ApprovedKickoffPolicy:
    claim_version: str
    country_name: str
    timezone_name: str


@dataclass(frozen=True, slots=True)
class KickoffClaimPublicationResult:
    claims: int
    chronological_batches: int
    status: str


@dataclass(frozen=True, slots=True)
class _Corpus:
    competition_id: UUID
    season_id: UUID
    provider_id: UUID


@dataclass(frozen=True, slots=True)
class _SourceClaim:
    lifecycle_claim_id: UUID
    match_id: UUID
    match_observation_id: UUID
    provider_match_id: str
    match_date: date
    kick_off_local: time
    lifecycle_known_from: datetime


@dataclass(frozen=True, slots=True)
class _CompetitionFact:
    observation_id: UUID
    name: str
    country_name: str
    is_international: bool | None


@dataclass(frozen=True, slots=True)
class _KickoffClaim:
    claim_id: UUID
    claim_sha256: str
    source: _SourceClaim
    competition_observation_id: UUID
    kickoff_at: datetime
    evidence: dict[str, object]


class Sprint2KickoffClaimPublisher:
    """Publish immutable UTC kickoff claims without altering timezone-naive provider facts."""

    def __init__(
        self,
        connection: Connection[Any],
        *,
        clock: Callable[[], datetime] | None = None,
        claim_version: str = KICKOFF_CLAIM_VERSION,
        country_name: str = "England",
        timezone_name: str = KICKOFF_TIMEZONE,
    ) -> None:
        self._connection = connection
        self._clock = clock or (lambda: datetime.now(UTC))
        self._claim_version = claim_version
        self._country_name = country_name
        self._timezone_name = timezone_name
        if (claim_version, country_name, timezone_name) not in _APPROVED_DOMESTIC_POLICIES:
            raise KickoffClaimError("kickoff policy is not approved")

    def publish(self, corpus: EvaluationCorpusV1 | None = None) -> KickoffClaimPublicationResult:
        requested = corpus or EvaluationCorpusV1()
        return self._publish(
            lambda cursor: (
                _resolve_corpus(cursor, requested),
                (self._claim_version, self._country_name, self._timezone_name),
                None,
                None,
            )
        )

    def publish_for_dataset(
        self, dataset_version_id: UUID, source_snapshot_id: UUID
    ) -> KickoffClaimPublicationResult:
        return self._publish(
            lambda cursor: _resolve_explicit_scope(cursor, dataset_version_id, source_snapshot_id)
        )

    def _publish(
        self,
        resolver: Callable[
            [Cursor[Any]], tuple[_Corpus, tuple[str, str, str], UUID | None, UUID | None]
        ],
    ) -> KickoffClaimPublicationResult:
        known_from = self._clock()
        _aware(known_from, "kickoff claim clock")
        with self._connection.transaction(), self._connection.cursor() as cursor:
            resolved, policy, dataset_version_id, source_snapshot_id = resolver(cursor)
            claim_version, country_name, timezone_name = policy
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (f"kickoff-claims:{resolved.season_id}:{claim_version}:{TZDATA_VERSION}",),
            )
            sources = _source_claims(cursor, resolved, dataset_version_id, source_snapshot_id)
            claims = tuple(
                _build_claim(
                    cursor,
                    resolved,
                    source,
                    known_from,
                    claim_version,
                    country_name,
                    timezone_name,
                )
                for source in sources
            )
            inserted = sum(
                _register_claim(
                    cursor,
                    resolved,
                    claim,
                    known_from,
                    claim_version,
                    timezone_name,
                )
                for claim in claims
            )
        if inserted == len(claims):
            status = "published"
        elif inserted == 0:
            status = "verified_existing"
        else:
            raise KickoffClaimError("kickoff claim publication is partially registered")
        return KickoffClaimPublicationResult(
            claims=len(claims),
            chronological_batches=len({claim.kickoff_at for claim in claims}),
            status=status,
        )


def resolve_local_kickoff(
    match_date: date, kick_off_local: time, *, timezone_name: str = KICKOFF_TIMEZONE
) -> datetime:
    if kick_off_local.tzinfo is not None:
        raise KickoffClaimError("local kickoff evidence must not include a timezone")
    zone, _tzif_sha256 = _timezone_contract(timezone_name)
    local = datetime.combine(match_date, kick_off_local)
    candidates: set[datetime] = set()
    for fold in (0, 1):
        candidate = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == local:
            candidates.add(candidate)
    if len(candidates) != 1:
        raise KickoffClaimError(
            f"local kickoff {match_date.isoformat()} {kick_off_local.isoformat()} "
            "is not one unambiguous local instant"
        )
    return candidates.pop()


@cache
def _timezone_contract(timezone_name: str = KICKOFF_TIMEZONE) -> tuple[ZoneInfo, str]:
    installed = metadata.version("tzdata")
    if installed != TZDATA_VERSION:
        raise KickoffClaimError(
            f"tzdata version {installed} does not match required {TZDATA_VERSION}"
        )
    parts = timezone_name.split("/")
    if not timezone_name or any(not part or part in {".", ".."} for part in parts):
        raise KickoffClaimError("timezone policy is invalid")
    resource = resources.files("tzdata.zoneinfo").joinpath(*parts)
    payload = resource.read_bytes()
    return ZoneInfo.from_file(BytesIO(payload), key=timezone_name), hashlib.sha256(
        payload
    ).hexdigest()


def _resolve_corpus(cursor: Cursor[Any], corpus: EvaluationCorpusV1) -> _Corpus:
    rows = cursor.execute(
        """
        SELECT season.competition_id, season.id, provider.id
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
        raise KickoffClaimError("approved corpus does not map to one canonical season")
    return _Corpus(UUID(str(rows[0][0])), UUID(str(rows[0][1])), UUID(str(rows[0][2])))


def _resolve_explicit_scope(
    cursor: Cursor[Any], dataset_version_id: UUID, source_snapshot_id: UUID
) -> tuple[_Corpus, tuple[str, str, str], UUID, UUID]:
    dataset = cursor.execute(
        """
        SELECT dataset.source_snapshot_id, snapshot.provider_id, provider.code,
               dataset.dataset_name, dataset.layer, dataset.status
        FROM football.dataset_versions AS dataset
        JOIN football.source_snapshots AS snapshot ON snapshot.id = dataset.source_snapshot_id
        JOIN football.providers AS provider ON provider.id = snapshot.provider_id
        WHERE dataset.id = %s
        """,
        (dataset_version_id,),
    ).fetchone()
    if dataset is None:
        raise KickoffClaimError("explicit kickoff dataset is unknown")
    snapshot = cursor.execute(
        "SELECT id FROM football.source_snapshots WHERE id = %s",
        (source_snapshot_id,),
    ).fetchone()
    if snapshot is None:
        raise KickoffClaimError("explicit kickoff source snapshot is unknown")
    if UUID(str(dataset[0])) != source_snapshot_id:
        raise KickoffClaimError("explicit kickoff dataset/source snapshot mismatch")
    if tuple(dataset[3:]) != ("events", "normalized", "published"):
        raise KickoffClaimError("explicit kickoff dataset is not published normalized events")
    if dataset[2] != "statsbomb_open_data":
        raise KickoffClaimError("kickoff claims require a StatsBomb dataset")
    rows = cursor.execute(
        """
        SELECT DISTINCT match.competition_id, match.season_id
        FROM football.match_lifecycle_claims AS claim
        JOIN football.matches AS match ON match.id = claim.match_id
        WHERE claim.dataset_version_id = %s
          AND claim.source_snapshot_id = %s
          AND claim.claim_version = %s
          AND claim.lifecycle = 'completed'
        ORDER BY match.season_id
        """,
        (dataset_version_id, source_snapshot_id, LIFECYCLE_CLAIM_VERSION),
    ).fetchall()
    if len(rows) != 1:
        raise KickoffClaimError("explicit kickoff scope does not resolve to one canonical season")
    resolved = _Corpus(
        competition_id=UUID(str(rows[0][0])),
        season_id=UUID(str(rows[0][1])),
        provider_id=UUID(str(dataset[1])),
    )
    sources = _source_claims(cursor, resolved, dataset_version_id, source_snapshot_id)
    if not sources:
        raise KickoffClaimError("explicit kickoff scope lacks completed lifecycle claims")
    policy = _approved_policy(cursor, resolved, sources[0].lifecycle_known_from)
    return resolved, policy, dataset_version_id, source_snapshot_id


def _approved_policy(
    cursor: Cursor[Any], corpus: _Corpus, knowledge_cutoff: datetime
) -> tuple[str, str, str]:
    rows = cursor.execute(
        """
        SELECT country_name, is_international
        FROM football.competition_observations
        WHERE competition_id = %s
          AND provider_id = %s
          AND football.known_at(known_from, known_to, %s)
        ORDER BY known_from DESC, id DESC
        """,
        (corpus.competition_id, corpus.provider_id, knowledge_cutoff),
    ).fetchall()
    if len(rows) != 1 or rows[0][1] is True:
        raise KickoffClaimError("explicit kickoff scope lacks one domestic competition fact")
    country_name = str(rows[0][0]) if rows[0][0] is not None else ""
    policy = approved_domestic_kickoff_policy(country_name)
    return policy.claim_version, policy.country_name, policy.timezone_name


def approved_domestic_kickoff_policy(country_name: str) -> ApprovedKickoffPolicy:
    policies = tuple(policy for policy in _APPROVED_DOMESTIC_POLICIES if policy[1] == country_name)
    if len(policies) != 1:
        raise KickoffClaimError("kickoff scope lacks one approved domestic policy")
    return ApprovedKickoffPolicy(*policies[0])


def _source_claims(
    cursor: Cursor[Any],
    corpus: _Corpus,
    dataset_version_id: UUID | None = None,
    source_snapshot_id: UUID | None = None,
) -> tuple[_SourceClaim, ...]:
    rows = cursor.execute(
        """
        SELECT DISTINCT ON (claim.match_id)
               claim.id, claim.match_id, claim.match_observation_id,
               observation.provider_match_id, observation.match_date,
               observation.kick_off_local, claim.known_from
        FROM football.match_lifecycle_claims AS claim
        JOIN football.matches AS match ON match.id = claim.match_id
        JOIN football.match_observations AS observation
          ON observation.id = claim.match_observation_id
        WHERE match.competition_id = %s
          AND match.season_id = %s
          AND claim.claim_version = %s
          AND claim.lifecycle = 'completed'
          AND (%s::uuid IS NULL OR claim.dataset_version_id = %s)
          AND (%s::uuid IS NULL OR claim.source_snapshot_id = %s)
        ORDER BY claim.match_id, claim.known_from DESC, claim.created_at DESC, claim.id DESC
        """,
        (
            corpus.competition_id,
            corpus.season_id,
            LIFECYCLE_CLAIM_VERSION,
            dataset_version_id,
            dataset_version_id,
            source_snapshot_id,
            source_snapshot_id,
        ),
    ).fetchall()
    expected_row = cursor.execute(
        "SELECT count(*) FROM football.matches WHERE season_id = %s",
        (corpus.season_id,),
    ).fetchone()
    expected = int(expected_row[0]) if expected_row is not None else -1
    if not rows or len(rows) != expected:
        raise KickoffClaimError(
            f"lifecycle evidence covers {len(rows)} of {expected} corpus matches"
        )
    claims: list[_SourceClaim] = []
    for row in rows:
        if row[4] is None or row[5] is None:
            raise KickoffClaimError(f"match {row[3]} lacks local kickoff evidence")
        claims.append(
            _SourceClaim(
                lifecycle_claim_id=UUID(str(row[0])),
                match_id=UUID(str(row[1])),
                match_observation_id=UUID(str(row[2])),
                provider_match_id=str(row[3]),
                match_date=row[4],
                kick_off_local=row[5],
                lifecycle_known_from=row[6],
            )
        )
    return tuple(claims)


def _competition_fact(
    cursor: Cursor[Any], corpus: _Corpus, knowledge_cutoff: datetime, country_name: str
) -> _CompetitionFact:
    rows = cursor.execute(
        """
        SELECT id, name, country_name, is_international
        FROM football.competition_observations
        WHERE competition_id = %s
          AND provider_id = %s
          AND football.known_at(known_from, known_to, %s)
        ORDER BY known_from DESC, id DESC
        """,
        (corpus.competition_id, corpus.provider_id, knowledge_cutoff),
    ).fetchall()
    if len(rows) != 1:
        raise KickoffClaimError("kickoff policy lacks one competition fact at cutoff")
    fact = _CompetitionFact(
        observation_id=UUID(str(rows[0][0])),
        name=str(rows[0][1]),
        country_name=str(rows[0][2]) if rows[0][2] is not None else "",
        is_international=rows[0][3],
    )
    if fact.country_name != country_name or fact.is_international is True:
        raise KickoffClaimError(
            f"kickoff policy only supports domestic {country_name} competition facts"
        )
    return fact


def _build_claim(
    cursor: Cursor[Any],
    corpus: _Corpus,
    source: _SourceClaim,
    known_from: datetime,
    claim_version: str,
    country_name: str,
    timezone_name: str,
) -> _KickoffClaim:
    if known_from < source.lifecycle_known_from:
        raise KickoffClaimError("kickoff claim predates lifecycle evidence")
    competition = _competition_fact(cursor, corpus, source.lifecycle_known_from, country_name)
    kickoff_at = resolve_local_kickoff(
        source.match_date, source.kick_off_local, timezone_name=timezone_name
    )
    _zone, tzif_sha256 = _timezone_contract(timezone_name)
    evidence: dict[str, object] = {
        "contract": "MatchKickoffClaimEvidenceV1",
        "provider_match_id": source.provider_match_id,
        "competition_name": competition.name,
        "competition_country_name": competition.country_name,
        "competition_is_international": competition.is_international,
        "local_match_date": source.match_date.isoformat(),
        "local_kickoff_time": source.kick_off_local.isoformat(),
        "timezone_name": timezone_name,
        "tzdata_version": TZDATA_VERSION,
        "tzif_sha256": tzif_sha256,
        "kickoff_at": kickoff_at.isoformat().replace("+00:00", "Z"),
    }
    identity = {
        "claim_version": claim_version,
        "match_id": str(source.match_id),
        "lifecycle_claim_id": str(source.lifecycle_claim_id),
        "match_observation_id": str(source.match_observation_id),
        "competition_observation_id": str(competition.observation_id),
        "evidence": evidence,
    }
    claim_sha256 = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return _KickoffClaim(
        claim_id=uuid5(_CLAIM_NAMESPACE, claim_sha256),
        claim_sha256=claim_sha256,
        source=source,
        competition_observation_id=competition.observation_id,
        kickoff_at=kickoff_at,
        evidence=evidence,
    )


def _register_claim(
    cursor: Cursor[Any],
    corpus: _Corpus,
    claim: _KickoffClaim,
    known_from: datetime,
    claim_version: str,
    timezone_name: str,
) -> int:
    _zone, tzif_sha256 = _timezone_contract(timezone_name)
    source = claim.source
    inserted = cursor.execute(
        """
        INSERT INTO football.match_kickoff_claims
            (id, match_id, competition_id, season_id, claim_version, claim_sha256,
             lifecycle_claim_id, match_observation_id, competition_observation_id,
             local_match_date, local_kickoff_time, timezone_name, tzdata_version,
             tzif_sha256, kickoff_at, known_from, evidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s)
        ON CONFLICT (claim_sha256) DO NOTHING
        """,
        (
            claim.claim_id,
            source.match_id,
            corpus.competition_id,
            corpus.season_id,
            claim_version,
            claim.claim_sha256,
            source.lifecycle_claim_id,
            source.match_observation_id,
            claim.competition_observation_id,
            source.match_date,
            source.kick_off_local,
            timezone_name,
            TZDATA_VERSION,
            tzif_sha256,
            claim.kickoff_at,
            known_from,
            Jsonb(claim.evidence),
        ),
    ).rowcount
    row = cursor.execute(
        """
        SELECT id, match_id, lifecycle_claim_id, match_observation_id,
               competition_observation_id, kickoff_at, evidence
        FROM football.match_kickoff_claims WHERE claim_sha256 = %s
        """,
        (claim.claim_sha256,),
    ).fetchone()
    expected = (
        claim.claim_id,
        source.match_id,
        source.lifecycle_claim_id,
        source.match_observation_id,
        claim.competition_observation_id,
        claim.kickoff_at,
        claim.evidence,
    )
    if row != expected:
        raise KickoffClaimError(f"match {source.match_id} kickoff claim conflicts")
    return inserted


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise KickoffClaimError(f"{field_name} must include a timezone")
