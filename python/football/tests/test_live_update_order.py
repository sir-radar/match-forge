from dataclasses import replace
from datetime import UTC, datetime, timedelta

from football.product.live_resources import LiveUpdate, live_update_order

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def update():
    return LiveUpdate(
        provider="fotmob",
        status="LIVE",
        home_score=1,
        away_score=0,
        minute=20,
        added_time=None,
        source_updated_at=None,
        first_known_at=NOW,
    )


def test_later_http_does_not_order_changed_score_at_the_same_football_clock():
    current = update()
    incoming = replace(current, home_score=0, first_known_at=NOW + timedelta(minutes=1))
    assert live_update_order(current, incoming) == "CONFLICT"
    assert live_update_order(current, replace(incoming, minute=10)) == "STALE"
    assert live_update_order(current, replace(incoming, minute=21)) == "NEWER"


def test_duplicate_known_state_does_not_gain_new_football_time():
    current = update()
    assert (
        live_update_order(current, replace(current, first_known_at=NOW + timedelta(hours=1)))
        == "SAME"
    )


def test_base_minutes_and_added_time_are_not_summed_across_halves():
    current = replace(update(), minute=45, added_time=8)
    assert live_update_order(current, replace(current, minute=46, added_time=None)) == "NEWER"
    assert live_update_order(current, replace(current, added_time=7)) == "STALE"
    assert (
        live_update_order(current, replace(current, added_time=None, home_score=2)) == "UNORDERED"
    )


def test_same_provider_update_clock_can_prove_a_correction_and_blocks_older_replays():
    current = replace(update(), source_updated_at=NOW - timedelta(minutes=1))
    correction = replace(current, minute=19, source_updated_at=NOW, home_score=0)
    assert live_update_order(current, correction) == "NEWER"
    replay = replace(
        current, minute=30, source_updated_at=None, first_known_at=NOW - timedelta(minutes=2)
    )
    assert live_update_order(current, replay) == "STALE"
    equal_clock = replace(current, home_score=0)
    assert live_update_order(current, equal_clock) == "CONFLICT"


def test_completion_is_a_football_milestone_but_unknown_interruption_is_not_ordered():
    current = update()
    assert live_update_order(current, replace(current, status="FINISHED", minute=None)) == "NEWER"
    assert (
        live_update_order(current, replace(current, status="SUSPENDED", minute=None)) == "UNORDERED"
    )


def test_different_provider_timestamps_do_not_arbitrate_equal_clock_score_disagreement():
    current = replace(update(), source_updated_at=NOW - timedelta(seconds=30))
    other = replace(current, provider="pitchapi", source_updated_at=NOW, home_score=0)
    assert live_update_order(current, other) == "CONFLICT"


def test_future_source_timestamp_cannot_prove_a_correction():
    current = update()
    incoming = replace(current, source_updated_at=NOW + timedelta(days=1), home_score=0)
    assert live_update_order(current, incoming) == "CONFLICT"
