from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from football.product.result_recovery import (
    CanonicalResult,
    DueFixture,
    RecoveryReport,
    ReturnedResult,
    classify,
    next_check,
    select_dates,
)

NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)
SCHEDULED = CanonicalResult("SCHEDULED", None, None, "UNKNOWN", True)
FINAL = CanonicalResult("FINISHED", 2, 1, "REGULATION_90", False)


@pytest.mark.parametrize(
    ("before", "after", "returned", "fetched", "outcome"),
    [
        (SCHEDULED, FINAL, ReturnedResult("FINISHED", 2, 1, "REGULATION_90"), True, "RECOVERED"),
        # Extra time and shootouts are recovered results, not regulation-time history.
        (
            SCHEDULED,
            CanonicalResult("FINISHED", 1, 1, "PENALTY_SHOOTOUT", False),
            ReturnedResult("FINISHED", 1, 1, "PENALTY_SHOOTOUT"),
            True,
            "RECOVERED",
        ),
        # Retained evidence resolved it before any request.
        (SCHEDULED, FINAL, None, False, "RECOVERED"),
        # A successful request that did not contain the fixture.
        (SCHEDULED, SCHEDULED, None, True, "NOT_RETURNED"),
        (SCHEDULED, SCHEDULED, ReturnedResult("LIVE", 1, 0, "UNKNOWN"), True, "NOT_YET_PUBLISHED"),
        (
            SCHEDULED,
            SCHEDULED,
            ReturnedResult("POSTPONED", None, None, "UNKNOWN"),
            True,
            "NOT_YET_PUBLISHED",
        ),
        # The provider has a final score that identity checks did not accept.
        (
            SCHEDULED,
            SCHEDULED,
            ReturnedResult("FINISHED", 2, 1, "REGULATION_90"),
            True,
            "IDENTITY_UNRESOLVED",
        ),
    ],
)
def test_recovery_outcomes_distinguish_acquisition_from_recovery(
    before: CanonicalResult,
    after: CanonicalResult,
    returned: ReturnedResult | None,
    fetched: bool,
    outcome: str,
) -> None:
    assert classify("RECOVERY", before, after, returned, fetched) == outcome


def test_score_without_duration_is_not_guessed_or_reported_as_recovered() -> None:
    unknown = CanonicalResult("FINISHED", 2, 1, "UNKNOWN", True)
    assert (
        classify("RECOVERY", unknown, unknown, ReturnedResult("FINISHED", 2, 1, "UNKNOWN"), True)
        == "SCORE_BASIS_UNAVAILABLE"
    )
    assert (
        classify("RECOVERY", unknown, unknown, ReturnedResult("FINISHED", 3, 1, "UNKNOWN"), True)
        == "RESULT_CONFLICT"
    )
    unqualified = CanonicalResult("FINISHED", 2, 1, "REGULATION_90", True)
    assert classify("RECOVERY", unqualified, unqualified, None, True) == "QUALIFICATION_FAILED"


def test_correction_outcomes() -> None:
    corrected = CanonicalResult("FINISHED", 2, 2, "REGULATION_90", False)
    same = ReturnedResult("FINISHED", 2, 1, "REGULATION_90")
    assert classify("CORRECTION", FINAL, corrected, same, True) == "CORRECTED"
    assert classify("CORRECTION", FINAL, FINAL, same, True) == "VERIFIED_UNCHANGED"
    assert classify("CORRECTION", FINAL, FINAL, None, True) == "NOT_RETURNED"
    # A differing provider score the source-ordering rules rejected stays visible.
    differs = ReturnedResult("FINISHED", 0, 0, "REGULATION_90")
    assert classify("CORRECTION", FINAL, FINAL, differs, True) == "RESULT_CONFLICT"
    annulled = CanonicalResult("CANCELLED", None, None, "UNKNOWN", False)
    assert classify("CORRECTION", FINAL, annulled, None, True) == "CORRECTED"


def test_backoff_is_short_for_recent_results_and_never_abandons_old_ones() -> None:
    recent = NOW - timedelta(hours=5)
    assert next_check("NOT_RETURNED", recent, NOW, 1) == NOW + timedelta(minutes=15)
    assert next_check("NOT_RETURNED", recent, NOW, 10) == NOW + timedelta(hours=2)
    old = NOW - timedelta(days=400)
    assert next_check("NOT_YET_PUBLISHED", old, NOW, 1) == NOW + timedelta(days=2)
    assert next_check("NOT_YET_PUBLISHED", old, NOW, 50) == NOW + timedelta(days=7)
    assert next_check("PROVIDER_UNAVAILABLE", old, NOW, 1) == NOW + timedelta(minutes=5)
    assert next_check("PROVIDER_UNAVAILABLE", old, NOW, 9) == NOW + timedelta(hours=1)
    until = NOW + timedelta(hours=3)
    assert next_check("PROVIDER_RATE_LIMITED", old, NOW, 1, until=until) == until
    assert next_check("RESULT_CONFLICT", old, NOW, 1) == NOW + timedelta(days=7)


def test_correction_checks_follow_a_finite_schedule() -> None:
    kickoff = NOW - timedelta(hours=30)
    assert next_check("RECOVERED", kickoff, NOW, 1) == kickoff + timedelta(days=7)
    assert next_check("VERIFIED_UNCHANGED", kickoff, kickoff + timedelta(days=8), 1) == (
        kickoff + timedelta(days=28)
    )
    assert next_check("VERIFIED_UNCHANGED", kickoff, kickoff + timedelta(days=29), 1) is None
    assert next_check("SCORE_BASIS_UNAVAILABLE", NOW - timedelta(days=90), NOW, 1) is None


def _due(day: date, checked: datetime | None) -> DueFixture:
    kickoff = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=15)
    return DueFixture(uuid4(), str(uuid4()), day, kickoff, "RECOVERY", 0, None, checked)


def test_date_selection_reserves_recent_capacity_and_moves_the_backlog() -> None:
    backlog = [_due(date(2024, 1, 1) + timedelta(days=n), None) for n in range(40)]
    recent = _due(date(2026, 11, 13), NOW - timedelta(minutes=1))
    selected = [day for day, _ in select_dates([*backlog, recent], 4)]
    # Half the capacity goes to the newest dates, half to the longest-waiting ones.
    assert selected == [recent.day, date(2024, 2, 9), date(2024, 1, 1), date(2024, 1, 2)]

    # Repeated runs eventually reach every backlog date: no starvation.
    checked: dict[date, datetime] = {}
    clock = NOW
    seen: set[date] = set()
    for _ in range(40):
        clock += timedelta(minutes=10)
        fixtures = [replace_checked(f, checked.get(f.day)) for f in backlog] + [recent]
        for day, _ in select_dates(fixtures, 4):
            checked[day] = clock
            seen.add(day)
    assert {f.day for f in backlog} <= seen


def replace_checked(fixture: DueFixture, checked: datetime | None) -> DueFixture:
    return DueFixture(
        fixture.fixture_id,
        fixture.provider_match_id,
        fixture.day,
        fixture.kickoff_at,
        fixture.purpose,
        fixture.attempts,
        fixture.previous_outcome,
        checked,
    )


def test_report_counts_domain_outcomes_not_fetched_resources() -> None:
    report = RecoveryReport()
    report.counts.successful_requests = 3
    report.counts.fetched = 120
    fixture = _due(date(2026, 11, 1), None)
    report.record(fixture, "NOT_RETURNED")
    summary = report.to_dict(include_fixtures=True)
    assert summary["recovered"] == 0 and summary["unresolved"] == 1
    assert summary["status"] == "COMPLETED"
    assert summary["fixtures"] == {str(fixture.fixture_id): "NOT_RETURNED"}
