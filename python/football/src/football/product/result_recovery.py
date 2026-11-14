"""Recover missing results and discover corrections through existing ingestion owners.

Eligibility is decided per fixture and provider in
``football.product_result_recovery_state``. Fixtures that share a provider's UTC
date share one request, coordinated by a short lease on the existing
``football.product_provider_refresh_state`` row for that date. The lease only
prevents duplicate concurrent acquisition; it never carries a freshness delay, so
a checked fixture cannot suppress a newly eligible fixture on the same date, and an
operator request is never blocked by an earlier background check. Provider-enforced
deadlines and quotas remain with the provider clients (``HistoryRequestBudget`` and
the API-Football budget), which raise before any network request is made.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection, Error

from football.product.api_football import ApiFootballError, CapabilityStatus
from football.product.domain import stable_id
from football.product.external_predictions import settle_external_predictions
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.history_requalification import _rows as retained_fixture_rows
from football.product.history_requests import HistoryDeferred
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.operational_support import FixtureObservation, SyncCounts
from football.product.sync import ProductSync
from football.product.sync_support import _api_football_score_basis, _mapping
from football.providers.base import ProviderFetchError
from football.providers.fotmob import FotmobResponse
from football.providers.pitchapi import PitchApiResponse
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks

Calendar = FotmobResponse | PitchApiResponse

RECOVERY_PROVIDERS = ("fotmob", "pitchapi", "api_football")
LEASE = timedelta(minutes=15)
# Finished results are rechecked for provider corrections at these offsets from
# kickoff, then no longer: unchanged historical seasons are not downloaded again.
CORRECTION_SCHEDULE = (timedelta(days=1), timedelta(days=7), timedelta(days=28))
CORRECTION_HORIZON = CORRECTION_SCHEDULE[-1] + timedelta(days=1)
RESOLVED = frozenset({"RECOVERED", "CORRECTED", "VERIFIED_UNCHANGED"})
_EXACT_MAPPING = """m.valid_to IS NULL AND m.mapping_confidence=1
    AND (m.valid_from IS NULL OR m.valid_from<=statement_timestamp())
    AND m.mapping_method IN ('deterministic','explicit_crosswalk','manual')"""


@dataclass(frozen=True, slots=True)
class DueFixture:
    fixture_id: UUID
    provider_match_id: str
    day: date
    kickoff_at: datetime
    purpose: str
    attempts: int
    previous_outcome: str | None
    last_checked_at: datetime | None


@dataclass(frozen=True, slots=True)
class ReturnedResult:
    status: str
    home: int | None
    away: int | None
    basis: str


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    status: str
    home: int | None
    away: int | None
    basis: str
    candidate: bool

    @property
    def final(self) -> bool:
        return self.status == "FINISHED" and self.home is not None and self.away is not None


@dataclass(slots=True)
class RecoveryReport:
    counts: SyncCounts = field(default_factory=SyncCounts)
    outcomes: Counter[str] = field(default_factory=Counter)
    fixtures: dict[str, str] = field(default_factory=dict)
    coordinated: int = 0
    deferred_until: datetime | None = None
    selected_dates: int = 0

    def record(self, fixture: DueFixture, outcome: str) -> None:
        self.outcomes[outcome] += 1
        self.fixtures[str(fixture.fixture_id)] = outcome

    def to_dict(self, *, include_fixtures: bool) -> dict[str, object]:
        unresolved = sum(n for o, n in self.outcomes.items() if o not in RESOLVED)
        result: dict[str, object] = {
            "status": "COMPLETED_WITH_ERRORS" if self.counts.failed else "COMPLETED",
            **self.counts.to_dict(),
            "selected_dates": self.selected_dates,
            "outcomes": dict(sorted(self.outcomes.items())),
            "recovered": self.outcomes["RECOVERED"],
            "corrected": self.outcomes["CORRECTED"],
            "verified_unchanged": self.outcomes["VERIFIED_UNCHANGED"],
            "unresolved": unresolved,
            "coordinated": self.coordinated,
            "deferred_until": self.deferred_until.isoformat() if self.deferred_until else None,
        }
        if include_fixtures:
            result["fixtures"] = dict(sorted(self.fixtures.items()))
        return result


@dataclass(frozen=True, slots=True)
class RecoveryRequest:
    limit: int
    day: date | None = None
    fixture_id: UUID | None = None

    @property
    def manual(self) -> bool:
        return self.day is not None or self.fixture_id is not None


class ProviderDeferred(Exception):
    """The provider client refused to issue a request before a deadline."""

    def __init__(self, reason: str, until: datetime) -> None:
        super().__init__(reason)
        self.reason = reason
        self.until = until


class ProviderScopeUnsupported(Exception):
    """The provider refused the requested scope under the account's plan.

    The refusal is the provider's own statement (for example API-Football's
    "Free plans do not have access to this date"), so the scope is deferred for
    this provider only and stays eligible for every other provider.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class RecoveryRoute:
    """Provider-specific acquisition through the provider's existing ingestion owner."""

    provider: str
    connection: Connection[Any]
    acquire: Callable[[date, frozenset[str], SyncCounts], tuple[dict[str, ReturnedResult], UUID]]
    # Returns, per provider match id, why retained evidence could not be applied.
    replay: Callable[[date, frozenset[str], SyncCounts], Mapping[str, str] | None] | None = None
    # A provider plan may serve only recent dates. Retained evidence is still replayed
    # for any date; only the request is skipped, so quota is not spent on a refusal.
    requestable: Callable[[date], bool] | None = None


# --------------------------------------------------------------------------- selection


def due_fixtures(
    connection: Connection[Any], provider: str, request: RecoveryRequest
) -> list[DueFixture]:
    """Return every exactly mapped fixture whose next recovery action is due.

    Automatic runs honour each fixture's own next check. An operator's fixture or
    date request selects its fixtures regardless of MatchForge's own schedule.
    """
    rows = connection.execute(
        f"""WITH target AS (
            SELECT c.fixture_id,'RECOVERY'::text AS purpose
            FROM football.product_result_recovery_candidates c
            WHERE (%(fixture)s::uuid IS NULL OR c.fixture_id=%(fixture)s)
              AND (%(day)s::date IS NULL OR (
                  c.kickoff_at>=(%(day)s::date::timestamp AT TIME ZONE 'UTC')
                  AND c.kickoff_at<((%(day)s::date+1)::timestamp AT TIME ZONE 'UTC')))
            UNION ALL
            SELECT f.fixture_id,'CORRECTION'
            FROM football.product_fixtures f
            WHERE f.status='FINISHED' AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL
              AND (f.result_score_basis NOT IN ('UNKNOWN','REGULATION_90') OR EXISTS (
                  SELECT 1 FROM football.product_team_match_history h
                  WHERE h.fixture_id=f.fixture_id))
              AND (%(fixture)s::uuid IS NULL OR f.fixture_id=%(fixture)s)
              AND (CASE WHEN %(day)s::date IS NOT NULL THEN
                       f.kickoff_at>=(%(day)s::date::timestamp AT TIME ZONE 'UTC')
                       AND f.kickoff_at<((%(day)s::date+1)::timestamp AT TIME ZONE 'UTC')
                   WHEN %(fixture)s::uuid IS NOT NULL THEN true
                   ELSE f.kickoff_at>=statement_timestamp()-%(horizon)s
                        AND f.kickoff_at<statement_timestamp()-%(first)s END)
              AND NOT EXISTS (
                  SELECT 1 FROM football.fixture_identity_resolutions r
                  WHERE r.member_fixture_id=f.fixture_id AND r.active
                    AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                         OR r.representative_fixture_id<>f.fixture_id))
        )
        SELECT f.fixture_id,m.provider_match_id,(f.kickoff_at AT TIME ZONE 'UTC')::date,
               f.kickoff_at,t.purpose,COALESCE(s.attempts,0),s.outcome,s.last_checked_at
        FROM target t
        JOIN football.product_fixtures f ON f.fixture_id=t.fixture_id
        JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id AND {_EXACT_MAPPING}
        JOIN football.providers p ON p.id=m.provider_id AND p.code=%(provider)s
        LEFT JOIN football.product_result_recovery_state s
          ON s.fixture_id=f.fixture_id AND s.provider_code=p.code
        WHERE f.identity_status='VERIFIED'
          AND (%(manual)s OR s.fixture_id IS NULL OR s.next_check_at<=statement_timestamp()
               OR s.purpose<>t.purpose OR m.created_at>s.last_checked_at)
        ORDER BY f.kickoff_at,f.fixture_id""",
        {
            "provider": provider,
            "fixture": request.fixture_id,
            "day": request.day,
            "manual": request.manual,
            "horizon": CORRECTION_HORIZON,
            "first": CORRECTION_SCHEDULE[0],
        },
    ).fetchall()
    connection.commit()
    return [DueFixture(*row) for row in rows]


def select_dates(fixtures: Sequence[DueFixture], limit: int) -> list[tuple[date, list[DueFixture]]]:
    """Choose at most ``limit`` dates: half newest, the rest longest waiting.

    Newly eligible recent fixtures get half of every run of two or more dates.
    The rest goes to the dates that have waited longest since their last check
    (or, if never checked, since kickoff), so an old backlog keeps moving and a
    large backlog cannot starve recent results.
    """
    days: dict[date, list[DueFixture]] = {}
    for fixture in fixtures:
        days.setdefault(fixture.day, []).append(fixture)

    def waited(day: date) -> tuple[datetime, date]:
        return min(f.last_checked_at or f.kickoff_at for f in days[day]), day

    recent = sorted(days, reverse=True)[: limit // 2]
    rest = sorted((day for day in days if day not in recent), key=waited)
    return [(day, days[day]) for day in (recent + rest)[:limit]]


def explain_unselected(
    connection: Connection[Any], request: RecoveryRequest, providers: Sequence[str]
) -> str:
    """Explain why an operator's request selected no provider work."""
    if request.fixture_id is None:
        return "NO_DUE_FIXTURES_FOR_DATE" if request.day else "NO_DUE_FIXTURES"
    row = connection.execute(
        f"""SELECT f.identity_status,f.status,f.kickoff_at>statement_timestamp(),
                   EXISTS (SELECT 1 FROM football.match_provider_mappings m
                           JOIN football.providers p ON p.id=m.provider_id
                           WHERE m.match_id=f.fixture_id AND p.code=ANY(%s)
                             AND {_EXACT_MAPPING}),
                   EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
                           WHERE r.member_fixture_id=f.fixture_id AND r.active
                             AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                                  OR r.representative_fixture_id<>f.fixture_id))
            FROM football.product_fixtures f WHERE f.fixture_id=%s""",
        (list(providers), request.fixture_id),
    ).fetchone()
    connection.commit()
    if row is None:
        return "FIXTURE_NOT_FOUND"
    identity, status, future, mapped, member = row
    if member:
        return "FIXTURE_IS_DUPLICATE_MEMBER"
    if identity != "VERIFIED":
        return "IDENTITY_NOT_VERIFIED"
    if not mapped:
        return "NO_EXACT_PROVIDER_MAPPING"
    if future:
        return "KICKOFF_NOT_REACHED"
    if status != "FINISHED":
        return f"FIXTURE_STATUS_{status}"
    return "NO_ENABLED_PROVIDER_ROUTE"


# --------------------------------------------------------------------- classification


def _final_differs(returned: ReturnedResult | None, canonical: CanonicalResult) -> bool:
    return (
        returned is not None
        and returned.status == "FINISHED"
        and returned.home is not None
        and (returned.home, returned.away) != (canonical.home, canonical.away)
    )


def _classify_recovery(
    before: CanonicalResult,
    after: CanonicalResult,
    returned: ReturnedResult | None,
    fetched: bool,
) -> str:
    if (after.final and not before.final) or not after.candidate:
        return "RECOVERED"
    if after.final:
        if _final_differs(returned, after):
            return "RESULT_CONFLICT"
        if after.basis == "UNKNOWN" and (returned is None or returned.basis == "UNKNOWN"):
            return "SCORE_BASIS_UNAVAILABLE"
        return "QUALIFICATION_FAILED"
    if returned is None:
        return "NOT_RETURNED" if fetched else "NOT_YET_PUBLISHED"
    if returned.status != "FINISHED" or returned.home is None or returned.away is None:
        return "NOT_YET_PUBLISHED"
    return "IDENTITY_UNRESOLVED"


def classify(
    purpose: str,
    before: CanonicalResult,
    after: CanonicalResult,
    returned: ReturnedResult | None,
    fetched: bool,
) -> str:
    """Name the domain outcome. A successful request is never itself a recovery."""
    if purpose == "RECOVERY":
        return _classify_recovery(before, after, returned, fetched)
    if (before.status, before.home, before.away, before.basis) != (
        after.status,
        after.home,
        after.away,
        after.basis,
    ):
        return "CORRECTED"
    if returned is None:
        return "NOT_RETURNED" if fetched else "VERIFIED_UNCHANGED"
    if _final_differs(returned, after):
        return "RESULT_CONFLICT"
    return "VERIFIED_UNCHANGED"


def next_check(
    outcome: str,
    kickoff_at: datetime,
    now: datetime,
    attempts: int,
    *,
    until: datetime | None = None,
) -> datetime | None:
    """When this fixture should be checked again; ``None`` means no further check."""
    if outcome == "PROVIDER_RATE_LIMITED":
        return until or now + timedelta(hours=1)
    if outcome == "PROVIDER_UNAVAILABLE":
        if until is not None:
            return until
        return now + min(timedelta(hours=1), timedelta(minutes=5) * (1 << min(attempts - 1, 8)))
    if outcome in {"NOT_RETURNED", "NOT_YET_PUBLISHED"}:
        age = now - kickoff_at
        if age < timedelta(days=2):
            base, cap = timedelta(minutes=15), timedelta(hours=2)
        elif age < timedelta(days=14):
            base, cap = timedelta(hours=2), timedelta(hours=12)
        elif age < timedelta(days=90):
            base, cap = timedelta(hours=12), timedelta(days=1)
        else:
            base, cap = timedelta(days=2), timedelta(days=7)
        return now + min(cap, base * (1 << min(attempts - 1, 8)))
    if outcome in {"IDENTITY_UNRESOLVED", "RESULT_CONFLICT", "QUALIFICATION_FAILED"}:
        # These need a mapping, evidence or qualification change; a new exact
        # mapping reactivates the fixture immediately (see due_fixtures).
        return now + timedelta(days=7)
    return next((kickoff_at + d for d in CORRECTION_SCHEDULE if kickoff_at + d > now), None)


# ------------------------------------------------------------------------- execution


def provider_cooldown(connection: Connection[Any], provider: str) -> datetime | None:
    """The provider's own retry deadline, as recorded when it last deferred."""
    row = connection.execute(
        """SELECT max(next_check_at) FROM football.product_result_recovery_state
           WHERE provider_code=%s AND outcome='PROVIDER_RATE_LIMITED'
             AND next_check_at>statement_timestamp() AND next_check_at<'infinity'""",
        (provider,),
    ).fetchone()
    connection.commit()
    return row[0] if row is not None else None


def _canonical(connection: Connection[Any], ids: Sequence[UUID]) -> dict[UUID, CanonicalResult]:
    rows = connection.execute(
        """SELECT f.fixture_id,f.status,f.home_score,f.away_score,f.result_score_basis,
                  EXISTS (SELECT 1 FROM football.product_result_recovery_candidates c
                          WHERE c.fixture_id=f.fixture_id)
           FROM football.product_fixtures f WHERE f.fixture_id=ANY(%s)""",
        (list(ids),),
    ).fetchall()
    connection.commit()
    return {row[0]: CanonicalResult(*row[1:]) for row in rows}


def _claim_date(connection: Connection[Any], provider: str, day: date) -> datetime | None:
    row = connection.execute(
        """INSERT INTO football.product_provider_refresh_state AS state (
               provider_code,resource_name,last_attempt_at,next_attempt_at)
           VALUES (%s,%s,clock_timestamp(),clock_timestamp()+%s)
           ON CONFLICT (provider_code,resource_name) DO UPDATE
           SET last_attempt_at=EXCLUDED.last_attempt_at,next_attempt_at=EXCLUDED.next_attempt_at
           WHERE state.next_attempt_at<=clock_timestamp()
           RETURNING last_attempt_at""",
        (provider, f"result-recovery-{day.isoformat()}", LEASE),
    ).fetchone()
    connection.commit()
    return row[0] if row is not None else None


def _release_date(
    connection: Connection[Any], provider: str, day: date, claimed: datetime, error: str | None
) -> None:
    connection.execute(
        """UPDATE football.product_provider_refresh_state
           SET next_attempt_at=clock_timestamp(),
               last_success_at=CASE WHEN %(error)s::text IS NULL THEN clock_timestamp()
                                    ELSE last_success_at END,
               failed_requests=CASE WHEN %(error)s::text IS NULL THEN 0
                                    ELSE failed_requests+1 END,
               last_error=%(error)s
           WHERE provider_code=%(provider)s AND resource_name=%(name)s
             AND last_attempt_at=%(claimed)s""",
        {
            "error": error,
            "provider": provider,
            "name": f"result-recovery-{day.isoformat()}",
            "claimed": claimed,
        },
    )
    connection.commit()


def _store_state(
    connection: Connection[Any],
    provider: str,
    fixture: DueFixture,
    outcome: str,
    purpose: str,
    snapshot: UUID | None,
    *,
    until: datetime | None,
    detail: str | None,
) -> None:
    now = datetime.now(UTC)
    attempts = fixture.attempts + 1 if fixture.previous_outcome == outcome else 1
    following = next_check(outcome, fixture.kickoff_at, now, attempts, until=until)
    connection.execute(
        """INSERT INTO football.product_result_recovery_state AS s (
               fixture_id,provider_code,purpose,outcome,attempts,first_checked_at,
               last_checked_at,next_check_at,last_snapshot_id,detail)
           VALUES (%(fixture)s,%(provider)s,%(purpose)s,%(outcome)s,%(attempts)s,%(now)s,
                   %(now)s,COALESCE(%(next)s,'infinity'::timestamptz),%(snapshot)s,%(detail)s)
           ON CONFLICT (fixture_id,provider_code) DO UPDATE SET
               purpose=EXCLUDED.purpose,outcome=EXCLUDED.outcome,attempts=EXCLUDED.attempts,
               last_checked_at=EXCLUDED.last_checked_at,next_check_at=EXCLUDED.next_check_at,
               last_snapshot_id=COALESCE(EXCLUDED.last_snapshot_id,s.last_snapshot_id),
               detail=EXCLUDED.detail""",
        {
            "fixture": fixture.fixture_id,
            "provider": provider,
            "purpose": purpose,
            "outcome": outcome,
            "attempts": attempts,
            "now": now,
            "next": following,
            "snapshot": snapshot,
            "detail": detail,
        },
    )


@dataclass(slots=True)
class _Acquisition:
    returned: dict[str, ReturnedResult] = field(default_factory=dict)
    snapshot: UUID | None = None
    fetched: bool = False
    error: str | None = None
    until: datetime | None = None
    outside_window: bool = False
    replay_declined: Mapping[str, str] = field(default_factory=dict)
    # Per-fixture detail; ``error`` stays a stable aggregate key.
    reason: str | None = None


OUTSIDE_WINDOW = "OUTSIDE_PROVIDER_DATE_WINDOW"
# A past date never re-enters a recent-date window; recheck rarely, in case newly
# retained evidence or a changed plan makes it recoverable.
OUTSIDE_WINDOW_RECHECK = timedelta(days=7)


def _acquire_date(
    route: RecoveryRoute, day: date, fixtures: Sequence[DueFixture], counts: SyncCounts
) -> _Acquisition:
    """Replay retained evidence, then request the date only for fixtures still needing it."""
    result = _Acquisition()
    try:
        if route.replay is not None:
            declined = route.replay(day, frozenset(f.provider_match_id for f in fixtures), counts)
            result.replay_declined = declined or {}
        current = _canonical(route.connection, [fixture.fixture_id for fixture in fixtures])
        needed = frozenset(
            fixture.provider_match_id
            for fixture in fixtures
            if fixture.purpose == "CORRECTION"
            or (fixture.fixture_id in current and current[fixture.fixture_id].candidate)
        )
        if needed and route.requestable is not None and not route.requestable(day):
            result.outside_window = True
        elif needed:
            counts.attempted_requests += 1
            result.returned, result.snapshot = route.acquire(day, needed, counts)
            result.fetched = True
    except ProviderDeferred as deferred:
        result.error, result.until = deferred.reason, deferred.until
    except ProviderScopeUnsupported as unsupported:
        result.outside_window, result.reason = True, unsupported.reason
        counts.failure_reasons[OUTSIDE_WINDOW] = counts.failure_reasons.get(OUTSIDE_WINDOW, 0) + 1
    except (Error, ProviderFetchError, OSError, ValueError) as failure:
        result.error = str(failure).splitlines()[0] or type(failure).__name__
        # Keep the provider's own reason (for example a plan restriction) for operators.
        cause = (str(failure.__cause__).splitlines() or [""])[0] if failure.__cause__ else ""
        result.reason = f"{result.error}: {cause}"[:300] if cause else result.error
    return result


def _process_date(
    route: RecoveryRoute, day: date, fixtures: Sequence[DueFixture], report: RecoveryReport
) -> bool:
    """Process one shared provider date. Returns False when the provider deferred."""
    connection = route.connection
    claimed = _claim_date(connection, route.provider, day)
    if claimed is None:
        # Another worker holds this date; its request covers these fixtures.
        report.coordinated += len(fixtures)
        for fixture in fixtures:
            report.fixtures[str(fixture.fixture_id)] = "IN_PROGRESS"
        return True
    ids = [fixture.fixture_id for fixture in fixtures]
    before = _canonical(connection, ids)
    acquired = _acquire_date(route, day, fixtures, report.counts)
    returned, snapshot, error, until = (
        acquired.returned,
        acquired.snapshot,
        acquired.error,
        acquired.until,
    )
    if error is not None:
        connection.rollback()
        report.counts.failed += 1
        report.counts.failure_reasons[error] = report.counts.failure_reasons.get(error, 0) + 1
    after = _canonical(connection, ids)
    for fixture in fixtures:
        if fixture.fixture_id not in after:  # retired by a concurrent identity merge
            continue
        result = returned.get(fixture.provider_match_id)
        outcome = classify(
            fixture.purpose,
            before[fixture.fixture_id],
            after[fixture.fixture_id],
            result,
            acquired.fetched,
        )
        detail = _detail(result)
        recheck = until
        if error is not None and outcome not in RESOLVED:
            outcome = "PROVIDER_RATE_LIMITED" if until else "PROVIDER_UNAVAILABLE"
            detail = acquired.reason or error
        elif acquired.outside_window and outcome not in RESOLVED:
            outcome = "PROVIDER_UNAVAILABLE"
            detail = f"{OUTSIDE_WINDOW}: {acquired.reason}" if acquired.reason else OUTSIDE_WINDOW
            recheck = datetime.now(UTC) + OUTSIDE_WINDOW_RECHECK
        elif outcome not in RESOLVED and fixture.provider_match_id in acquired.replay_declined:
            declined = acquired.replay_declined[fixture.provider_match_id]
            detail = f"{declined}; {detail}" if detail else declined
        purpose = "RECOVERY" if after[fixture.fixture_id].candidate else "CORRECTION"
        _store_state(
            connection,
            route.provider,
            fixture,
            outcome,
            purpose,
            snapshot,
            until=recheck,
            detail=detail,
        )
        report.record(fixture, outcome)
    connection.commit()
    _release_date(connection, route.provider, day, claimed, error)
    if until is not None:
        report.deferred_until = until
        return False
    return True


def _detail(result: ReturnedResult | None) -> str | None:
    if result is None:
        return None
    score = "" if result.home is None else f" {result.home}-{result.away}"
    return f"provider {result.status}{score} {result.basis}"


def run_recovery(route: RecoveryRoute, request: RecoveryRequest) -> dict[str, object]:
    """Run one bounded recovery pass for a provider."""
    report = RecoveryReport()
    selected = select_dates(due_fixtures(route.connection, route.provider, request), request.limit)
    report.selected_dates = len(selected)
    cooldown = provider_cooldown(route.connection, route.provider)
    if cooldown is not None and selected:
        # A provider deadline applies to every request, including an operator's.
        report.deferred_until = cooldown
        report.counts.failed += 1
        report.counts.failure_reasons["PROVIDER_COOLDOWN"] = 1
        for _day, fixtures in selected:
            for fixture in fixtures:
                report.record(fixture, "PROVIDER_RATE_LIMITED")
        return report.to_dict(include_fixtures=request.fixture_id is not None)
    for day, fixtures in selected:
        if not _process_date(route, day, fixtures, report):
            break
    counts = report.counts
    if counts.updated or counts.history_inserted or counts.stored_observations_reconciled:
        with route.connection.transaction():
            reconcile_product_fixtures(route.connection)
    return report.to_dict(include_fixtures=request.fixture_id is not None)


# ---------------------------------------------------------------------------- routes


def _replay_retained(
    sync: OperationalProviderSync, provider_ids: Sequence[str], counts: SyncCounts
) -> dict[str, str]:
    """Reprocess the newest validated final observation before requesting the provider.

    Retained evidence is replayed through the same identity and canonical rules as
    new evidence, with its original snapshot and acquisition time. Replays are
    idempotent; the per-fixture schedule prevents repeated replays of evidence that
    stays blocked. A final score without a stated duration is never replayed as a
    regulation-time result.
    """
    sources = sync.connection.execute(
        """SELECT DISTINCT ON (o.provider_match_id)
            o.provider_match_id,o.provider_competition_id,o.provider_home_team_id,
            o.provider_away_team_id,o.provider_home_team_name,o.provider_away_team_name,
            o.kickoff_at,o.canonical_status,o.provider_status,o.home_score,o.away_score,
            o.match_minute,o.added_time,o.period,o.source_updated_at,o.observed_at,
            o.provider_competition_name,o.source_snapshot_id,o.result_score_basis
        FROM football.product_provider_fixture_observations o
        JOIN football.source_snapshots s ON s.id=o.source_snapshot_id AND s.status='validated'
        WHERE o.provider_code=%s AND o.provider_match_id=ANY(%s)
          AND s.acquired_at<=statement_timestamp() AND o.observed_at<=statement_timestamp()
          AND (o.source_updated_at IS NULL OR o.source_updated_at<=o.observed_at)
          AND o.canonical_status='FINISHED'
          AND o.result_score_basis IN ('REGULATION_90','EXTRA_TIME','PENALTY_SHOOTOUT')
          AND o.home_score IS NOT NULL AND o.away_score IS NOT NULL
          AND o.provider_home_team_id IS NOT NULL AND o.provider_away_team_id IS NOT NULL
          AND o.provider_home_team_name IS NOT NULL AND o.provider_away_team_name IS NOT NULL
        ORDER BY o.provider_match_id,o.source_updated_at DESC NULLS LAST,o.observed_at DESC,
                 o.observation_id DESC""",
        (sync.provider_code, list(provider_ids)),
    ).fetchall()
    sync.connection.commit()
    declined: dict[str, str] = {}
    for source in sources:
        try:
            with sync.connection.transaction():
                applied = sync.reconcile_retained_observation(source) is not None
            counts.stored_observations_reconciled += int(applied)
            if not applied:
                declined[str(source[0])] = _explain_declined_replay(sync, source)
        except (Error, ValueError) as error:
            # Blocked evidence stays retained; the fixture's outcome and schedule
            # record the block, and the provider request below still runs.
            reason = "RETAINED_REPLAY_BLOCKED: " + (str(error).splitlines() or [""])[0]
            declined[str(source[0])] = reason
        else:
            if applied:
                continue
        key = declined[str(source[0])].split(" ", 1)[0]
        counts.failure_reasons[key] = counts.failure_reasons.get(key, 0) + 1
    return declined


def _explain_declined_replay(sync: OperationalProviderSync, source: tuple[Any, ...]) -> str:
    """Name why retained final evidence did not resolve to its mapped fixture.

    The identity rules stay unchanged; this only records which rule declined, so a
    rescheduled match or an unadmitted team is visible and reaches identity review.
    """
    mapped = sync.connection.execute(
        f"""SELECT f.kickoff_at FROM football.match_provider_mappings m
            JOIN football.providers p ON p.id=m.provider_id AND p.code=%s
            JOIN football.product_fixtures f ON f.fixture_id=m.match_id
            WHERE m.provider_match_id=%s AND {_EXACT_MAPPING}""",
        (sync.provider_code, str(source[0])),
    ).fetchall()
    sync.connection.commit()
    observed = source[6]
    if len(mapped) == 1 and abs(mapped[0][0] - observed) > sync.kickoff_tolerance:
        return (
            f"PROVIDER_KICKOFF_MOVED {mapped[0][0].astimezone(UTC):%Y-%m-%dT%H:%MZ}"
            f" -> {observed.astimezone(UTC):%Y-%m-%dT%H:%MZ}; identity review required"
        )
    if not sync._verified_provider_entities(sync._retained_fixture(source)):
        sync.connection.commit()
        return "PROVIDER_ENTITIES_UNTRUSTED: team or competition mapping not admitted"
    sync.connection.commit()
    return "IDENTITY_UNRESOLVED: retained evidence did not resolve to one verified fixture"


def operational_route(
    sync: OperationalProviderSync,
    fetch: Callable[[date], Calendar],
    normalize: Callable[[Any], Sequence[FixtureObservation]],
) -> RecoveryRoute:
    """FotMob or PitchAPI through the operational observation owner."""

    def acquire(
        day: date, requested: frozenset[str], counts: SyncCounts
    ) -> tuple[dict[str, ReturnedResult], UUID]:
        try:
            sync.pacer.wait()
            response = fetch(day)
        except HistoryDeferred as deferred:
            raise ProviderDeferred(str(deferred), deferred.until) from deferred
        counts.successful_requests += 1
        snapshot = sync._record_response(f"fixtures-{day.isoformat()}", response)
        sync.connection.commit()
        rows = tuple(row for row in normalize(response) if row.provider_match_id in requested)
        counts.fetched += len(rows)
        sync._ingest_observations(rows, snapshot, counts, create_missing=False)
        sync.connection.commit()
        return {
            row.provider_match_id: ReturnedResult(
                row.status, row.home_score, row.away_score, row.result_score_basis
            )
            for row in rows
        }, snapshot

    def replay(_day: date, ids: frozenset[str], counts: SyncCounts) -> dict[str, str]:
        return _replay_retained(sync, sorted(ids), counts)

    return RecoveryRoute(sync.provider_code, sync.connection, acquire, replay)


def recover_provider_results(
    sync: OperationalProviderSync,
    fetch: Callable[[date], Calendar],
    normalize: Callable[[Any], Sequence[FixtureObservation]],
    *,
    limit: int,
    day: date | None = None,
    fixture_id: UUID | None = None,
) -> dict[str, object]:
    """Recover FotMob or PitchAPI results for due exact mappings."""
    return run_recovery(
        operational_route(sync, fetch, normalize), RecoveryRequest(limit, day, fixture_id)
    )


def _api_football_terminal_rows(
    sync: ProductSync,
    rows: Sequence[Mapping[str, Any]],
    provider_ids: frozenset[str],
    observed_at: datetime,
) -> list[Mapping[str, Any]]:
    """Select exact mapped final scores. Never create identity from a recovery request."""
    eligible = []
    for row in rows:
        fixture = _mapping(row, "fixture")
        if str(fixture.get("id")) not in provider_ids:
            continue
        if _mapping(fixture, "status").get("short") not in {"FT", "AET", "PEN"}:
            continue
        goals = _mapping(row, "goals")
        if goals.get("home") is None or goals.get("away") is None:
            continue
        league = _mapping(row, "league")
        teams = _mapping(row, "teams")
        proof = sync.connection.execute(
            f"""SELECT f.fixture_id,f.competition_id,match.season_id
               FROM football.product_fixtures f
               JOIN football.matches match ON match.id=f.fixture_id
               JOIN football.match_provider_mappings m ON m.match_id=f.fixture_id
               JOIN football.providers p ON p.id=m.provider_id AND p.code='api_football'
               JOIN football.competition_provider_mappings cm ON cm.provider_id=p.id
                 AND cm.competition_id=f.competition_id AND cm.provider_competition_id=%s
                 AND cm.valid_to IS NULL AND football.product_mapping_trusted(
                     'competition', cm.id, cm.competition_id)
               JOIN football.team_provider_mappings h ON h.provider_id=p.id
                 AND h.team_id=f.home_team_id AND h.provider_team_id=%s
                 AND h.valid_to IS NULL
                 AND football.product_mapping_trusted('team', h.id, h.team_id)
               JOIN football.team_provider_mappings a ON a.provider_id=p.id
                 AND a.team_id=f.away_team_id AND a.provider_team_id=%s
                 AND a.valid_to IS NULL
                 AND football.product_mapping_trusted('team', a.id, a.team_id)
               WHERE m.provider_match_id=%s AND {_EXACT_MAPPING}
                 AND f.identity_status='VERIFIED' AND f.kickoff_at=%s::timestamptz
                 AND f.updated_at <= %s
                 AND (f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED',
                                   'INTERRUPTED','POSTPONED')
                      OR (f.status='FINISHED' AND (
                          (f.home_score=%s AND f.away_score=%s)
                          OR (%s='FT' AND f.result_score_basis='REGULATION_90' AND EXISTS (
                              SELECT 1 FROM football.product_team_match_history h
                              JOIN football.source_snapshots s ON s.id=h.source_snapshot_id
                              WHERE h.fixture_id=f.fixture_id
                                AND h.source_provider_code='api_football'
                                AND (h.home_goals,h.away_goals)=(f.home_score,f.away_score)
                                AND s.acquired_at<%s
                          ))
                      )))""",
            (
                str(league.get("id")),
                str(_mapping(teams, "home").get("id")),
                str(_mapping(teams, "away").get("id")),
                str(fixture["id"]),
                fixture.get("date"),
                observed_at,
                goals["home"],
                goals["away"],
                _mapping(fixture, "status")["short"],
                observed_at,
            ),
        ).fetchall()
        if len(proof) == 1 and proof[0][2] == stable_id(
            "season", proof[0][1], int(league["season"])
        ):
            eligible.append(row)
    return eligible


def _api_football_returned(rows: Sequence[Mapping[str, Any]]) -> dict[str, ReturnedResult]:
    returned = {}
    for row in rows:
        fixture = _mapping(row, "fixture")
        short = str(_mapping(fixture, "status").get("short"))
        goals = _mapping(row, "goals")
        returned[str(fixture.get("id"))] = ReturnedResult(
            "FINISHED" if short in {"FT", "AET", "PEN"} else short,
            goals.get("home"),
            goals.get("away"),
            _api_football_score_basis(short),
        )
    return returned


def _replay_api_football(
    sync: ProductSync, day: date, requested: frozenset[str], counts: SyncCounts
) -> None:
    """Re-offer retained, checksum-verified responses for this date before a request.

    The same identity proof and result owners run with each snapshot's original
    acquisition time; a stored row newer than the snapshot is never overwritten.
    """
    snapshots = sync.connection.execute(
        """SELECT * FROM (
             SELECT s.id,s.acquired_at,s.manifest_path,s.manifest_sha256
             FROM football.source_snapshots s
             JOIN football.providers p ON p.id=s.provider_id AND p.code='api_football'
             WHERE s.source_identity=%s AND s.status='validated'
               AND s.acquired_at<=statement_timestamp()
             ORDER BY s.acquired_at DESC,s.id DESC LIMIT 3) newest
           ORDER BY acquired_at,id""",
        (f"fixtures-{day.isoformat()}",),
    ).fetchall()
    sync.connection.commit()
    for snapshot, acquired_at, path, sha256 in snapshots:
        try:
            rows = retained_fixture_rows(sync.data_root, path, sha256)
            with sync.connection.transaction():
                acquire_locks(sync.connection, (IDENTITY_ADMISSION_LOCK,))
                eligible = _api_football_terminal_rows(sync, rows, requested, acquired_at)
                stored = sync._store_fixtures(eligible, snapshot, acquired_at)
                counts.stored_observations_reconciled += len(stored)
                counts.history_inserted += sync._qualify_finished_history(
                    stored, snapshot, acquired_at
                )
        except (Error, OSError, ValueError) as error:
            reason = "RETAINED_REPLAY_BLOCKED: " + (str(error).splitlines() or [""])[0]
            counts.failure_reasons[reason] = counts.failure_reasons.get(reason, 0) + 1


def api_football_route(
    sync: ProductSync, refresh: OperationalProviderSync, window_days: int | None = None
) -> RecoveryRoute:
    """API-Football through the MVP fixture owner and its request budget.

    ``window_days`` bounds requests to UTC dates no older than that many days before
    today; ``None`` requests any date.
    """

    def requestable(day: date) -> bool:
        assert window_days is not None
        return day >= datetime.now(UTC).date() - timedelta(days=window_days)

    def acquire(
        day: date, requested: frozenset[str], counts: SyncCounts
    ) -> tuple[dict[str, ReturnedResult], UUID]:
        try:
            refresh.pacer.wait()
            response = sync.client.fixtures_for_date(day)
        except ApiFootballError as error:
            if error.capability_status is CapabilityStatus.PLAN_RESTRICTION:
                raise ProviderScopeUnsupported(str(error)[:300]) from error
            if error.retry_after:
                raise ProviderDeferred("PROVIDER_COOLDOWN", error.retry_after) from error
            raise ProviderFetchError("PROVIDER_REQUEST_FAILED") from error
        counts.successful_requests += 1
        counts.fetched += len(response.rows)
        snapshot = sync._record_response(f"fixtures-{day.isoformat()}", response)
        original = sync.connection.execute(
            "SELECT acquired_at FROM football.source_snapshots WHERE id=%s", (snapshot,)
        ).fetchone()
        assert original is not None
        sync.connection.commit()
        with sync.connection.transaction():
            acquire_locks(sync.connection, (IDENTITY_ADMISSION_LOCK,))
            eligible = _api_football_terminal_rows(sync, response.rows, requested, original[0])
            stored = sync._store_fixtures(eligible, snapshot, original[0])
            counts.matched += len(stored)
            counts.updated += len(stored)
            counts.history_inserted += sync._qualify_finished_history(stored, snapshot, original[0])
        requested_rows = [
            row for row in response.rows if str(_mapping(row, "fixture").get("id")) in requested
        ]
        return _api_football_returned(requested_rows), snapshot

    def replay(day: date, requested: frozenset[str], counts: SyncCounts) -> None:
        _replay_api_football(sync, day, requested, counts)

    return RecoveryRoute(
        "api_football",
        sync.connection,
        acquire,
        replay,
        requestable if window_days is not None else None,
    )


def recover_api_football_results(
    sync: ProductSync,
    refresh: OperationalProviderSync,
    *,
    limit: int,
    day: date | None,
    fixture_id: UUID | None,
    window_days: int | None = None,
) -> dict[str, object]:
    return run_recovery(
        api_football_route(sync, refresh, window_days), RecoveryRequest(limit, day, fixture_id)
    )


# --------------------------------------------------------------------------- summary


def recovery_coverage(connection: Connection[Any]) -> dict[str, object]:
    """Current recovery population and each fixture's disposition."""
    row = connection.execute(
        f"""WITH c AS MATERIALIZED (
              SELECT c.*,EXISTS (
                  SELECT 1 FROM football.match_provider_mappings m
                  JOIN football.providers p ON p.id=m.provider_id
                  WHERE m.match_id=c.fixture_id AND p.code=ANY(%(providers)s)
                    AND {_EXACT_MAPPING}) AS routed,
                  NOT EXISTS (
                  SELECT 1 FROM football.product_result_recovery_state s
                  WHERE s.fixture_id=c.fixture_id) AS never_checked,
                  NOT EXISTS (
                  SELECT 1 FROM football.product_result_recovery_state s
                  WHERE s.fixture_id=c.fixture_id
                    AND s.next_check_at>statement_timestamp()) AS runnable
              FROM football.product_result_recovery_candidates c)
           SELECT count(*),
                  count(*) FILTER (WHERE status<>'FINISHED'),
                  count(*) FILTER (WHERE identity_status<>'VERIFIED'),
                  count(*) FILTER (WHERE identity_status='VERIFIED' AND NOT routed),
                  count(*) FILTER (WHERE identity_status='VERIFIED' AND routed),
                  count(*) FILTER (WHERE identity_status='VERIFIED' AND routed AND never_checked),
                  count(*) FILTER (WHERE identity_status='VERIFIED' AND routed AND runnable),
                  extract(epoch FROM statement_timestamp()-min(kickoff_at) FILTER (
                      WHERE identity_status='VERIFIED' AND routed AND runnable))::bigint,
                  COALESCE((SELECT jsonb_object_agg(recovery_reason,n) FROM (
                      SELECT recovery_reason,count(*) n FROM c GROUP BY 1) r),'{{}}'::jsonb)
           FROM c""",
        {"providers": list(RECOVERY_PROVIDERS)},
    ).fetchone()
    blockers = connection.execute(
        """SELECT s.outcome,count(*) FROM football.product_result_recovery_state s
           JOIN football.product_result_recovery_candidates c ON c.fixture_id=s.fixture_id
           GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    participation = connection.execute(
        f"""SELECT p.code,
                   count(DISTINCT c.fixture_id) FILTER (WHERE c.identity_status='VERIFIED'),
                   count(DISTINCT c.fixture_id) FILTER (WHERE c.identity_status<>'VERIFIED')
            FROM football.product_result_recovery_candidates c
            JOIN football.match_provider_mappings m ON m.match_id=c.fixture_id AND {_EXACT_MAPPING}
            JOIN football.providers p ON p.id=m.provider_id
            GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    outcomes = connection.execute(
        """SELECT s.provider_code,s.outcome,count(*)
           FROM football.product_result_recovery_state s GROUP BY 1,2"""
    ).fetchall()
    connection.commit()
    assert row is not None
    providers: dict[str, dict[str, object]] = {
        code: {
            "verified_candidates": verified,
            "identity_pending_candidates": pending,
            "recovery_route": code in RECOVERY_PROVIDERS,
            "outcomes": {},
        }
        for code, verified, pending in participation
    }
    for code, outcome, count in outcomes:
        entry = providers.setdefault(
            code,
            {
                "verified_candidates": 0,
                "identity_pending_candidates": 0,
                "recovery_route": True,
                "outcomes": {},
            },
        )
        outcome_counts = entry["outcomes"]
        assert isinstance(outcome_counts, dict)
        outcome_counts[outcome] = count
    return {
        "provider_participation": providers,
        "candidates": row[0],
        "overdue": row[1],
        "identity_pending": row[2],
        "no_operational_route": row[3],
        "routed": row[4],
        "never_checked": row[5],
        "runnable": row[6],
        "oldest_runnable_age_seconds": row[7],
        "by_reason": row[8],
        "dispositions": dict(blockers),
    }


def finish_result_recovery(connection: Connection[Any]) -> dict[str, object]:
    """Use the existing settlement queue and report current recovery dispositions."""
    settled = settle_external_predictions(connection, datetime.now(UTC))
    return {**recovery_coverage(connection), "settled_external_predictions": settled}


def _request_outcome(
    connection: Connection[Any],
    request: RecoveryRequest,
    providers: Sequence[str],
    fixture_outcomes: Mapping[str, str],
    selected: int,
) -> str | None:
    """The best provider outcome for an operator's fixture, or why nothing ran."""
    if request.fixture_id is not None:
        resolved = sorted(o for o in fixture_outcomes.values() if o in RESOLVED)
        if resolved:
            return resolved[0]
        if fixture_outcomes:
            return ",".join(sorted(set(fixture_outcomes.values())))
        return explain_unselected(connection, request, providers)
    if request.day is not None and not selected:
        return explain_unselected(connection, request, providers)
    return None


def summarize_recovery(
    connection: Connection[Any],
    request: RecoveryRequest,
    providers: Mapping[str, object],
    errors: Mapping[str, str],
) -> dict[str, object]:
    """Combine provider passes into one run summary with an explicit request outcome.

    Counts are domain outcomes, not fetched resources. An operator's fixture request
    that ends unresolved reports ``COMPLETED_UNRESOLVED`` rather than success.
    """
    totals: Counter[str] = Counter()
    fixture_outcomes: dict[str, str] = {}
    selected = 0
    deferred: list[str] = []
    for name, result in providers.items():
        if not isinstance(result, Mapping):
            continue
        if result.get("deferred_until"):
            deferred.append(str(result["deferred_until"]))
        for key in ("recovered", "corrected", "verified_unchanged", "unresolved", "coordinated"):
            totals[key] += int(result.get(key) or 0)
        selected += int(result.get("selected_dates") or 0)
        for fixture, outcome in dict(result.get("fixtures") or {}).items():
            if fixture == str(request.fixture_id):
                fixture_outcomes[name] = str(outcome)
    request_outcome = _request_outcome(
        connection, request, list(providers), fixture_outcomes, selected
    )
    status = "COMPLETED_WITH_ERRORS" if errors else "COMPLETED"
    if status == "COMPLETED" and request_outcome is not None and request_outcome not in RESOLVED:
        status = "COMPLETED_UNRESOLVED"
    return {
        "status": status,
        "request_outcome": request_outcome,
        "request_outcomes_by_provider": dict(sorted(fixture_outcomes.items())),
        "deferred_until": max(deferred, key=datetime.fromisoformat) if deferred else None,
        **{
            key: totals[key]
            for key in ("recovered", "corrected", "verified_unchanged", "unresolved", "coordinated")
        },
        "providers": dict(providers),
        "errors": dict(errors),
        **finish_result_recovery(connection),
    }
