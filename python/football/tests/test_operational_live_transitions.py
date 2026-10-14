from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from football.product.operational_provider_sync import (
    _detail_priority,
    _newer_calendar_row,
    _valid_transition,
)
from football.providers.pitchapi import PitchApiFixture


def fixture(status: str, *, observed_offset: int = 60) -> PitchApiFixture:
    kickoff = datetime(2026, 10, 11, 15, tzinfo=UTC)
    return PitchApiFixture(
        provider_match_id=f"m_{status[:6]:0<6}",
        provider_competition_id="l_123456",
        provider_home_team_id="t_home01",
        provider_away_team_id="t_away01",
        home_team_name="Home",
        away_team_name="Away",
        kickoff_at=kickoff,
        status=status,
        provider_status=status,
        home_score=0,
        away_score=0,
        minute=None,
        added_time=None,
        period=None,
        source_updated_at=None,
        observed_at=kickoff + timedelta(minutes=observed_offset),
    )


def test_valid_transitions_allow_second_half_and_resume_but_block_terminal_rollback() -> None:
    assert _valid_transition("LIVE", "HALF_TIME")
    assert _valid_transition("HALF_TIME", "LIVE")
    assert _valid_transition("INTERRUPTED", "LIVE")
    assert _valid_transition("SUSPENDED", "LIVE")
    assert _valid_transition("LIVE", "FINISHED")
    assert not _valid_transition("FINISHED", "LIVE")
    assert not _valid_transition("LIVE", "SCHEDULED")


def test_detail_priority_puts_active_mapped_before_bulk_history() -> None:
    mapped = uuid4()
    ordered = sorted(
        [
            (fixture("FINISHED"), mapped),
            (fixture("LIVE"), None),
            (fixture("LIVE"), mapped),
            (fixture("HALF_TIME"), mapped),
            (fixture("SCHEDULED"), mapped),
        ],
        key=lambda item: _detail_priority(*item),
    )
    assert [item[0].status for item in ordered] == [
        "LIVE",
        "LIVE",
        "HALF_TIME",
        "FINISHED",
        "SCHEDULED",
    ]
    assert ordered[0][1] == mapped


def test_duplicate_calendar_rows_require_proven_newer_source_time() -> None:
    from dataclasses import replace

    row = fixture("LIVE")
    assert _newer_calendar_row(row, {})
    assert not _newer_calendar_row(row, {row.provider_match_id: (row, uuid4())})
    current = replace(row, source_updated_at=row.observed_at - timedelta(minutes=1))
    known = {row.provider_match_id: (current, uuid4())}
    assert not _newer_calendar_row(replace(row, source_updated_at=current.source_updated_at), known)
    assert _newer_calendar_row(replace(row, source_updated_at=row.observed_at), known)
