from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.context.historical_corpus import (
    AvailabilityEvidenceTier,
    ConfirmedLineupLabelV1,
    HistoricalAvailabilityEvidence,
    HistoricalContextInputs,
    HistoricalTargetV1,
    PointInTimeReconstructionStatus,
    TargetCandidate,
    VenueCoordinateSource,
    VenueIdentityV1,
    build_phase_a_snapshot,
    filter_context_targets,
    qualify_availability_evidence,
    score_phase_b_lineup_label,
)
from football.context.live import (
    AvailabilityObservation,
    AvailabilityState,
    AvailabilityType,
    CoachObservation,
    LineupMode,
    LineupObservation,
    LineupPlayer,
    LineupRole,
)

KICKOFF = datetime(2025, 5, 1, 18, tzinfo=UTC)
HOME = UUID(int=1)
AWAY = UUID(int=2)
FIXTURE = UUID(int=3)
COACH = UUID(int=4)


def _players(offset: int = 0) -> tuple[LineupPlayer, ...]:
    return tuple(
        LineupPlayer(
            UUID(int=offset + number),
            str(offset + number),
            LineupRole.STARTER,
            "GK" if number == 10 else "CB",
            "GK" if number == 10 else "CB",
            str(number - 9),
        )
        for number in range(10, 21)
    )


def _lineup(
    fixture_id: UUID,
    team_id: UUID,
    kickoff: datetime,
    *,
    players: tuple[LineupPlayer, ...] | None = None,
    coach_id: UUID | None = COACH,
) -> LineupObservation:
    return LineupObservation(
        UUID(int=fixture_id.int + team_id.int + 100),
        fixture_id,
        team_id,
        kickoff,
        LineupMode.CONFIRMED,
        "4-3-3",
        coach_id,
        str(coach_id) if coach_id else None,
        kickoff - timedelta(minutes=30),
        kickoff - timedelta(minutes=30),
        "api_football",
        UUID(int=fixture_id.int + 200),
        f"{fixture_id.int:064x}",
        players or _players(),
    )


def _target() -> HistoricalTargetV1:
    return HistoricalTargetV1(
        FIXTURE,
        KICKOFF,
        KICKOFF - timedelta(microseconds=1),
        "Premier League",
        "2024/2025",
        HOME,
        AWAY,
        ("source:fixture",),
    )


def test_availability_evidence_tiers_do_not_upgrade_hindsight() -> None:
    assert (
        qualify_availability_evidence(
            observed_at=KICKOFF - timedelta(hours=2),
            known_at=KICKOFF - timedelta(hours=1),
            target_kickoff=KICKOFF,
            retrospective=False,
        )
        is AvailabilityEvidenceTier.TIER_A_POINT_IN_TIME
    )
    assert (
        qualify_availability_evidence(
            observed_at=KICKOFF - timedelta(days=2),
            known_at=KICKOFF + timedelta(days=30),
            target_kickoff=KICKOFF,
            retrospective=True,
        )
        is AvailabilityEvidenceTier.TIER_B_RETROSPECTIVE
    )
    assert (
        qualify_availability_evidence(
            observed_at=KICKOFF + timedelta(seconds=1),
            known_at=KICKOFF + timedelta(seconds=1),
            target_kickoff=KICKOFF,
            retrospective=False,
        )
        is AvailabilityEvidenceTier.UNAVAILABLE
    )


def test_phase_a_excludes_target_future_and_same_kickoff_information() -> None:
    previous = _lineup(UUID(int=10), HOME, KICKOFF - timedelta(days=7))
    target_label = _lineup(FIXTURE, HOME, KICKOFF, players=_players(100))
    future = _lineup(UUID(int=11), HOME, KICKOFF + timedelta(days=1), players=_players(200))
    future_injury = AvailabilityObservation(
        UUID(int=300),
        FIXTURE,
        HOME,
        previous.players[1].canonical_player_id,
        previous.players[1].provider_player_id,
        AvailabilityType.INJURY,
        AvailabilityState.UNAVAILABLE_INJURY,
        "future",
        KICKOFF + timedelta(seconds=1),
        KICKOFF + timedelta(seconds=1),
        "api_football",
        UUID(int=301),
        "a" * 64,
    )
    inputs = HistoricalContextInputs(
        lineup_history=(previous, target_label, future),
        availability_history=(
            HistoricalAvailabilityEvidence(
                future_injury, AvailabilityEvidenceTier.TIER_A_POINT_IN_TIME
            ),
        ),
        coach_history=(
            CoachObservation(
                COACH,
                HOME,
                KICKOFF - timedelta(days=30),
                KICKOFF - timedelta(days=30),
            ),
            CoachObservation(
                UUID(int=99),
                HOME,
                KICKOFF + timedelta(seconds=1),
                KICKOFF + timedelta(seconds=1),
            ),
        ),
        team_matches=(),
    )

    snapshot = build_phase_a_snapshot(_target(), inputs)

    assert snapshot.status is PointInTimeReconstructionStatus.POINT_IN_TIME_VERIFIED
    assert snapshot.predicted_home_lineup is not None
    assert {row.player_id for row in snapshot.predicted_home_lineup.starters} == {
        row.canonical_player_id for row in previous.players
    }
    assert snapshot.predicted_home_lineup.coach_id == COACH
    assert "confirmed_lineup" not in snapshot.to_payload()
    assert "home_score" not in snapshot.to_payload()


def test_phase_b_requires_a_frozen_matching_label() -> None:
    previous = _lineup(UUID(int=10), HOME, KICKOFF - timedelta(days=7))
    inputs = HistoricalContextInputs(
        lineup_history=(previous,),
        availability_history=(),
        coach_history=(
            CoachObservation(
                COACH,
                HOME,
                KICKOFF - timedelta(days=30),
                KICKOFF - timedelta(days=30),
            ),
        ),
        team_matches=(),
    )
    snapshot = build_phase_a_snapshot(_target(), inputs)
    label = ConfirmedLineupLabelV1(
        FIXTURE,
        _lineup(FIXTURE, HOME, KICKOFF),
        _lineup(FIXTURE, AWAY, KICKOFF),
        ("source:label",),
    )

    result = score_phase_b_lineup_label(snapshot, label)

    assert result.home is not None
    assert result.home.correct_starting_players == 11
    with pytest.raises(ValueError, match="fixture"):
        score_phase_b_lineup_label(snapshot, replace(label, fixture_id=UUID(int=999)))


def test_coach_change_resets_lineup_preference_window() -> None:
    old_coach = UUID(int=40)
    new_coach = UUID(int=41)
    old_players = _players(100)
    new_players = _players(200)
    old_lineup = _lineup(
        UUID(int=42),
        HOME,
        KICKOFF - timedelta(days=8),
        players=old_players,
        coach_id=old_coach,
    )
    new_lineup = _lineup(
        UUID(int=43),
        HOME,
        KICKOFF - timedelta(days=2),
        players=new_players,
        coach_id=new_coach,
    )
    snapshot = build_phase_a_snapshot(
        _target(),
        HistoricalContextInputs(
            (old_lineup, new_lineup),
            (),
            (
                CoachObservation(
                    old_coach,
                    HOME,
                    KICKOFF - timedelta(days=100),
                    KICKOFF - timedelta(days=100),
                ),
                CoachObservation(
                    new_coach,
                    HOME,
                    KICKOFF - timedelta(days=3),
                    KICKOFF - timedelta(days=3),
                ),
            ),
            (),
        ),
    )

    assert snapshot.predicted_home_lineup is not None
    assert snapshot.predicted_home_lineup.preference_sample_size == 1
    assert {row.player_id for row in snapshot.predicted_home_lineup.starters} == {
        row.canonical_player_id for row in new_players
    }


def test_rest_history_is_prior_only_and_same_kickoff_is_excluded() -> None:
    from football.context.contextual_features import TeamMatch

    history = (
        TeamMatch(UUID(int=20), HOME, KICKOFF - timedelta(days=2), KICKOFF - timedelta(days=2)),
        TeamMatch(UUID(int=21), HOME, KICKOFF, KICKOFF - timedelta(days=1)),
        TeamMatch(UUID(int=22), HOME, KICKOFF + timedelta(days=1), KICKOFF - timedelta(days=1)),
    )
    snapshot = build_phase_a_snapshot(
        _target(),
        HistoricalContextInputs((), (), (), history),
    )

    assert snapshot.rest_context["home"]["days_since_last_match"] == 2.0
    assert snapshot.rest_context["home"]["matches_last_3_days"] == 1.0


def test_firewall_filters_targets_only_and_deduplicates_real_fixture() -> None:
    spent = UUID(int=30)
    admitted = UUID(int=31)
    duplicate = UUID(int=32)
    history_id = UUID(int=33)
    result = filter_context_targets(
        (
            TargetCandidate(spent, "spent-real"),
            TargetCandidate(admitted, "same-real"),
            TargetCandidate(duplicate, "same-real"),
        ),
        frozenset({spent}),
        historical_fixture_ids=(spent, history_id),
    )

    assert tuple(row.fixture_id for row in result.targets) == (admitted,)
    assert result.forbidden_target_count == 1
    assert result.duplicate_real_fixture_count == 1
    assert result.historical_fixture_ids == (spent, history_id)
    assert result.forbidden_overlap == 0


def test_venue_coordinates_require_an_approved_unambiguous_source() -> None:
    verified = VenueIdentityV1(
        "venue-1",
        (("api_football", "42"),),
        "Example Ground",
        "Example",
        "England",
        51.5,
        -0.1,
        VenueCoordinateSource.PROVIDER_STRUCTURED,
        "VERIFIED",
        "Europe/London",
    )
    ambiguous = replace(verified, venue_id="venue-2", ambiguous=True)
    missing = replace(verified, venue_id="venue-3", latitude=None, longitude=None)

    assert verified.qualified
    assert not ambiguous.qualified
    assert not missing.qualified
    assert verified.as_qualified_venue().qualified
    with pytest.raises(ValueError, match="qualified"):
        ambiguous.as_qualified_venue()
