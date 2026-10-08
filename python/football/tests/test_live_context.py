from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from football.context.live import (
    AvailabilityObservation,
    AvailabilityState,
    AvailabilityType,
    CoachObservation,
    LineupMode,
    LineupObservation,
    LineupPlayer,
    LineupRole,
    PredictionConfidence,
    SelectionReason,
    calculate_lineup_accuracy,
    predict_lineup,
)
from football.forecasting.revisions import requires_forecast_revision

TEAM = UUID(int=1)
COACH = UUID(int=2)
KICKOFF = datetime(2026, 10, 7, 18, tzinfo=UTC)
CUTOFF = KICKOFF - timedelta(hours=1)


def _player(number: int, position: str, role: LineupRole = LineupRole.STARTER) -> LineupPlayer:
    return LineupPlayer(UUID(int=number), str(number), role, position, position, str(number))


def _lineup(
    number: int,
    days_ago: int,
    starters: tuple[LineupPlayer, ...],
    bench: tuple[LineupPlayer, ...] = (),
    *,
    coach_id: UUID | None = COACH,
    known_at: datetime | None = None,
) -> LineupObservation:
    kickoff = KICKOFF - timedelta(days=days_ago)
    return LineupObservation(
        UUID(int=number),
        UUID(int=number + 1000),
        TEAM,
        kickoff,
        LineupMode.CONFIRMED,
        "4-3-3",
        coach_id,
        None,
        kickoff - timedelta(minutes=30),
        known_at or kickoff - timedelta(minutes=30),
        "api_football",
        UUID(int=number + 2000),
        f"{number:064x}",
        starters + bench,
    )


def _availability(
    player: LineupPlayer,
    state: AvailabilityState,
    *,
    observed_at: datetime = CUTOFF,
) -> AvailabilityObservation:
    return AvailabilityObservation(
        UUID(int=player.canonical_player_id.int + 3000),
        UUID(int=999),
        TEAM,
        player.canonical_player_id,
        player.provider_player_id,
        AvailabilityType.INJURY,
        state,
        None,
        observed_at,
        observed_at,
        "api_football",
        UUID(int=player.canonical_player_id.int + 4000),
        f"{player.canonical_player_id.int:064x}",
    )


def _base_players() -> tuple[LineupPlayer, ...]:
    return (
        _player(10, "GK"),
        _player(11, "CB"),
        _player(12, "CB"),
        _player(13, "LB"),
        _player(14, "RB"),
        _player(15, "DM"),
        _player(16, "CM"),
        _player(17, "AM"),
        _player(18, "LW"),
        _player(19, "RW"),
        _player(20, "ST"),
    )


def _coach() -> CoachObservation:
    return CoachObservation(COACH, TEAM, KICKOFF - timedelta(days=100), CUTOFF)


def test_repeat_prior_xi_when_fresh_feed_reports_no_issue() -> None:
    starters = _base_players()
    history = tuple(_lineup(index + 1, index + 1, starters) for index in range(5))
    availability = tuple(
        _availability(player, AvailabilityState.ASSUMED_AVAILABLE_NO_REPORTED_ISSUE)
        for player in starters
    )

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, availability, (_coach(),))

    assert tuple(item.player_id for item in result.starters) == tuple(
        player.canonical_player_id for player in starters
    )
    assert all(
        item.selection_reason is SelectionReason.REPEATED_PREVIOUS_STARTER
        for item in result.starters
    )
    assert result.confidence is PredictionConfidence.HIGH


def test_injured_starter_uses_most_used_exact_position_alternative() -> None:
    starters = _base_players()
    injured = starters[1]
    preferred = _player(30, "CB", LineupRole.BENCH)
    other = _player(31, "CB", LineupRole.BENCH)
    history = (
        _lineup(1, 1, starters, (preferred, other)),
        _lineup(2, 2, starters, (preferred, other)),
        _lineup(
            3,
            3,
            tuple(
                replace(preferred, role=LineupRole.STARTER) if item == injured else item
                for item in starters
            ),
            (other,),
        ),
        _lineup(
            4,
            4,
            tuple(
                replace(preferred, role=LineupRole.STARTER) if item == injured else item
                for item in starters
            ),
            (other,),
        ),
    )
    availability = tuple(
        _availability(
            player,
            AvailabilityState.UNAVAILABLE_INJURY
            if player == injured
            else AvailabilityState.ASSUMED_AVAILABLE_NO_REPORTED_ISSUE,
        )
        for player in starters
    )

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, availability, (_coach(),))
    replacement = next(
        item for item in result.starters if item.replaced_player_id == injured.canonical_player_id
    )

    assert replacement.player_id == preferred.canonical_player_id
    assert replacement.selection_reason is SelectionReason.MOST_USED_EXACT_POSITION_ALTERNATIVE
    assert replacement.historical_start_count == 2


def test_broad_fallback_only_when_exact_candidate_absent_and_never_reused() -> None:
    starters = _base_players()
    missing = (starters[1], starters[2])
    defender = _player(30, "LB", LineupRole.BENCH)
    history = (_lineup(1, 1, starters, (defender,)), _lineup(2, 2, starters, (defender,)))
    availability = tuple(
        _availability(
            player,
            AvailabilityState.UNAVAILABLE_SUSPENSION
            if player in missing
            else AvailabilityState.ASSUMED_AVAILABLE_NO_REPORTED_ISSUE,
        )
        for player in starters
    )

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, availability, (_coach(),))

    replacements = [item for item in result.starters if item.replaced_player_id is not None]
    assert len(replacements) == 1
    assert replacements[0].player_id == defender.canonical_player_id
    assert replacements[0].selection_reason is SelectionReason.MOST_USED_POSITION_GROUP_ALTERNATIVE
    assert len(result.unresolved_slots) == 1
    assert result.confidence is PredictionConfidence.LOW


def test_injured_bench_player_does_not_change_xi_and_gk_only_uses_gk() -> None:
    starters = _base_players()
    bench_cb = _player(30, "CB", LineupRole.BENCH)
    bench_gk = _player(31, "GK", LineupRole.BENCH)
    history = (_lineup(1, 1, starters, (bench_cb, bench_gk)),)
    availability = (
        _availability(bench_cb, AvailabilityState.UNAVAILABLE_INJURY),
        _availability(starters[0], AvailabilityState.UNAVAILABLE_INJURY),
    )

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, availability, (_coach(),))

    assert bench_cb.canonical_player_id not in {item.player_id for item in result.starters}
    gk = next(item for item in result.starters if item.normalized_position == "GK")
    assert gk.player_id == bench_gk.canonical_player_id


def test_unknown_or_stale_availability_is_not_healthy_and_lowers_confidence() -> None:
    starters = _base_players()
    stale = tuple(
        _availability(
            player,
            AvailabilityState.ASSUMED_AVAILABLE_NO_REPORTED_ISSUE,
            observed_at=CUTOFF - timedelta(hours=4, seconds=1),
        )
        for player in starters
    )
    history = tuple(_lineup(index + 1, index + 1, starters) for index in range(5))

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, stale, ())

    assert all(
        item.selection_reason is SelectionReason.AVAILABILITY_UNVERIFIED_REPEAT
        for item in result.starters
    )
    assert result.confidence is PredictionConfidence.LOW
    assert result.coach_context == "UNKNOWN"


def test_future_same_kickoff_and_late_known_lineups_are_excluded() -> None:
    older = _base_players()
    future = tuple(
        _player(number + 100, player.normalized_position) for number, player in enumerate(older)
    )
    history = (
        _lineup(1, 2, older),
        _lineup(2, 0, future),
        _lineup(3, 1, future, known_at=CUTOFF + timedelta(seconds=1)),
    )

    result = predict_lineup(TEAM, KICKOFF, CUTOFF, history, (), (_coach(),))

    assert {item.player_id for item in result.starters} == {
        player.canonical_player_id for player in older
    }


def test_confirmed_lineup_accuracy_does_not_mutate_prediction() -> None:
    starters = _base_players()
    predicted = predict_lineup(
        TEAM,
        KICKOFF,
        CUTOFF,
        (_lineup(1, 1, starters),),
        (),
        (_coach(),),
    )
    confirmed_players = starters[:-1] + (_player(99, "ST"),)
    confirmed = _lineup(20, 0, confirmed_players, known_at=CUTOFF)

    accuracy = calculate_lineup_accuracy(predicted, confirmed)

    assert accuracy.correct_starting_players == 10
    assert accuracy.xi_precision == accuracy.xi_recall == 10 / 11
    assert accuracy.formation_match
    assert len(predicted.starters) == 11


def test_context_only_change_does_not_create_forecast_revision() -> None:
    assert not requires_forecast_revision("a" * 64, "a" * 64)
    assert requires_forecast_revision("a" * 64, "b" * 64)


def test_live_context_migration_is_append_only_and_forecast_revisions_are_semantic() -> None:
    migration = Path(
        "infrastructure/migrations/202610070200_live_context_revisions.sql"
    ).read_text()

    assert "product_availability_observations" in migration
    assert "product_lineup_observations" in migration
    assert "live context observations and snapshots are immutable" in migration
    assert "product_forecasts_predictive_revision_idx" in migration
    assert "predictive_input_snapshot_sha256" in migration
    assert "context_snapshot_sha256" in migration
    disable = "DISABLE TRIGGER product_forecasts_immutable"
    backfill = "UPDATE football.product_forecasts"
    enable = "ENABLE TRIGGER product_forecasts_immutable"
    assert migration.index(disable) < migration.index(backfill) < migration.index(enable)
