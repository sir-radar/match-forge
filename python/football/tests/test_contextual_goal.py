from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from football.context.contextual_features import (
    QualifiedVenue,
    TeamMatch,
    availability_lineup_features,
    manager_features,
    rest_congestion_features,
    travel_features,
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
    PredictedLineupV1,
    PredictedStarter,
    PredictionConfidence,
    SelectionReason,
)
from football.forecasting.context_evaluation import (
    CoverageReport,
    DevelopmentPartition,
    LineupValidationCase,
    chronological_partitions,
    coverage_gate,
    validate_lineup_predictor,
)
from football.forecasting.contextual_goal import (
    ContextTrainingRow,
    ContextualGoalAdjustmentV1,
    FamilyDisposition,
    FeatureFamily,
    build_contextual_artifact,
    fit_contextual_adjustment,
)
from football.forecasting.model_contracts import ForecastInputSnapshot

KICKOFF = datetime(2026, 10, 8, 18, tzinfo=UTC)
HOME = UUID(int=1)
AWAY = UUID(int=2)
COACH = UUID(int=3)


def _player(number: int, position: str = "CM") -> LineupPlayer:
    return LineupPlayer(
        UUID(int=number), str(number), LineupRole.STARTER, position, position, str(number)
    )


def _lineup(
    identifier: int,
    team: UUID,
    kickoff: datetime,
    known_at: datetime,
    players: tuple[LineupPlayer, ...],
    *,
    coach: UUID | None = COACH,
) -> LineupObservation:
    return LineupObservation(
        UUID(int=identifier),
        UUID(int=900),
        team,
        kickoff,
        LineupMode.CONFIRMED,
        "4-3-3",
        coach,
        None,
        known_at,
        known_at,
        "provider",
        UUID(int=identifier + 1000),
        f"{identifier:064x}",
        players,
    )


def _availability(player: LineupPlayer, known_at: datetime) -> AvailabilityObservation:
    return AvailabilityObservation(
        UUID(int=player.canonical_player_id.int + 2000),
        UUID(int=900),
        HOME,
        player.canonical_player_id,
        player.provider_player_id,
        AvailabilityType.INJURY,
        AvailabilityState.UNAVAILABLE_INJURY,
        "injury",
        known_at,
        known_at,
        "provider",
        UUID(int=player.canonical_player_id.int + 3000),
        f"{player.canonical_player_id.int:064x}",
    )


def test_rejected_family_is_exactly_neutral_and_absent_from_artifact() -> None:
    artifact = build_contextual_artifact(
        baseline_model="transferable-rolling-goals-poisson-v1",
        family_results={FeatureFamily.REST_CONGESTION: FamilyDisposition.DEVELOPMENT_REJECTED},
        fitted=(),
        training_cutoff=KICKOFF,
        dataset_sha256="a" * 64,
        configuration_sha256="b" * 64,
        source_commit="c" * 40,
    )
    model = ContextualGoalAdjustmentV1(artifact)

    assert artifact.included_families == ()
    assert artifact.coefficients == ()
    assert model.adjust(1.5, 1.2, {"home_days_since_last_match": 2.0}) == (1.5, 1.2)


def test_artifact_rejects_coefficients_from_unauthorized_family() -> None:
    with pytest.raises(ValueError, match="authorized features"):
        build_contextual_artifact(
            baseline_model="transferable-rolling-goals-poisson-v1",
            family_results={FeatureFamily.TRAVEL: FamilyDisposition.DEVELOPMENT_REJECTED},
            fitted=(("home_travel_distance_km", 0.2, 0.0, 0.0, 1.0),),
            training_cutoff=KICKOFF,
            dataset_sha256="a" * 64,
            configuration_sha256="b" * 64,
            source_commit="c" * 40,
        )


def test_missing_context_keeps_baseline_fixture_and_neutral_adjustment() -> None:
    artifact = build_contextual_artifact(
        baseline_model="transferable-rolling-goals-poisson-v1",
        family_results={FeatureFamily.REST_CONGESTION: FamilyDisposition.DEVELOPMENT_ACCEPTED},
        fitted=(("home_days_since_last_match", 0.3, 0.0, 5.0, 2.0),),
        training_cutoff=KICKOFF,
        dataset_sha256="a" * 64,
        configuration_sha256="b" * 64,
        source_commit="c" * 40,
    )

    assert ContextualGoalAdjustmentV1(artifact).adjust(1.4, 1.1, {}) == (1.4, 1.1)


def test_confirmed_lineup_after_cutoff_cannot_leak_backward() -> None:
    previous = tuple(_player(index, "CM") for index in range(10, 21))
    confirmed = tuple(_player(index, "CM") for index in range(30, 41))
    history = (
        _lineup(1, HOME, KICKOFF - timedelta(days=7), KICKOFF - timedelta(days=7), previous),
        _lineup(2, HOME, KICKOFF, KICKOFF - timedelta(minutes=45), confirmed),
    )

    early = availability_lineup_features(
        HOME, KICKOFF, KICKOFF - timedelta(hours=1), history, (), ()
    )
    late = availability_lineup_features(
        HOME, KICKOFF, KICKOFF - timedelta(minutes=15), history, (), ()
    )

    assert early["lineup_mode"] == "PREDICTED_REPEAT_XI"
    assert early["confirmed_xi_continuity"] is None
    assert late["lineup_mode"] == "CONFIRMED"
    assert late["confirmed_xi_continuity"] == 0.0


def test_availability_known_before_cutoff_affects_features_but_later_report_does_not() -> None:
    previous = tuple(_player(index) for index in range(10, 21))
    history = (
        _lineup(1, HOME, KICKOFF - timedelta(days=7), KICKOFF - timedelta(days=7), previous),
    )
    before = _availability(previous[0], KICKOFF - timedelta(hours=2))
    after = _availability(previous[1], KICKOFF - timedelta(minutes=10))

    features = availability_lineup_features(
        HOME,
        KICKOFF,
        KICKOFF - timedelta(hours=1),
        history,
        (before, after),
        (
            CoachObservation(
                COACH, HOME, KICKOFF - timedelta(days=100), KICKOFF - timedelta(days=100)
            ),
        ),
    )

    assert features["injured_previous_starters_count"] == 1.0
    assert features["unavailable_previous_starters_count"] == 1.0


def test_manager_history_isolated_to_current_coach() -> None:
    old_coach = UUID(int=4)
    coaches = (
        CoachObservation(
            old_coach, HOME, KICKOFF - timedelta(days=100), KICKOFF - timedelta(days=100)
        ),
        CoachObservation(COACH, HOME, KICKOFF - timedelta(days=20), KICKOFF - timedelta(days=20)),
    )
    matches = (
        TeamMatch(
            UUID(int=1), HOME, KICKOFF - timedelta(days=30), KICKOFF - timedelta(days=29), old_coach
        ),
        TeamMatch(
            UUID(int=2), HOME, KICKOFF - timedelta(days=10), KICKOFF - timedelta(days=9), COACH
        ),
    )

    result = manager_features(HOME, KICKOFF, KICKOFF - timedelta(hours=1), matches, coaches)

    assert result["matches_under_coach"] == 1.0
    assert result["coach_changed_recently"] == 1.0


def test_coach_change_isolates_preferred_lineup_history() -> None:
    old_coach = UUID(int=4)
    old_players = tuple(_player(index) for index in range(10, 21))
    new_players = tuple(_player(index) for index in range(30, 41))
    history = tuple(
        _lineup(
            index,
            HOME,
            KICKOFF - timedelta(days=index + 5),
            KICKOFF - timedelta(days=index + 5),
            old_players,
            coach=old_coach,
        )
        for index in range(2, 7)
    ) + (_lineup(20, HOME, KICKOFF - timedelta(days=2), KICKOFF - timedelta(days=2), new_players),)
    coaches = (
        CoachObservation(
            old_coach, HOME, KICKOFF - timedelta(days=100), KICKOFF - timedelta(days=100)
        ),
        CoachObservation(COACH, HOME, KICKOFF - timedelta(days=10), KICKOFF - timedelta(days=10)),
    )

    result = availability_lineup_features(
        HOME,
        KICKOFF,
        KICKOFF - timedelta(hours=1),
        history,
        (_availability(old_players[0], KICKOFF - timedelta(hours=2)),),
        coaches,
    )

    assert result["unavailable_preferred_starters_count"] == 0.0


def test_rest_uses_only_prior_completed_fixtures() -> None:
    matches = (
        TeamMatch(UUID(int=1), HOME, KICKOFF - timedelta(days=2), KICKOFF - timedelta(days=1)),
        TeamMatch(UUID(int=2), HOME, KICKOFF - timedelta(days=1), KICKOFF + timedelta(hours=1)),
        TeamMatch(UUID(int=3), HOME, KICKOFF + timedelta(days=1), KICKOFF - timedelta(days=1)),
    )

    result = rest_congestion_features(HOME, KICKOFF, KICKOFF, matches)

    assert result["days_since_last_match"] == 2.0
    assert result["matches_last_3_days"] == 1.0


def test_travel_requires_qualified_coordinates() -> None:
    with pytest.raises(ValueError, match="qualified venue coordinates"):
        travel_features(None, QualifiedVenue(0.0, 0.0, "UTC", True), neutral_venue=False)

    result = travel_features(
        QualifiedVenue(51.5074, -0.1278, "Europe/London", True),
        QualifiedVenue(48.8566, 2.3522, "Europe/Paris", True),
        neutral_venue=False,
    )
    assert result["travel_distance_km"] == pytest.approx(343.6, abs=1.0)


def test_coefficients_are_deterministic_from_frozen_training_rows() -> None:
    rows = tuple(
        ContextTrainingRow(
            fixture_id=UUID(int=index),
            kickoff_at=KICKOFF + timedelta(days=index),
            competition="A",
            baseline_home_rate=1.3,
            baseline_away_rate=1.1,
            home_goals=index % 3,
            away_goals=(index + 1) % 2,
            values={"home_days_since_last_match": float(index % 6 + 1)},
        )
        for index in range(1, 25)
    )

    first = fit_contextual_adjustment(rows, FeatureFamily.REST_CONGESTION, l2=1.0)
    second = fit_contextual_adjustment(tuple(reversed(rows)), FeatureFamily.REST_CONGESTION, l2=1.0)

    assert first == second


def test_chronological_split_keeps_same_kickoff_batch_together() -> None:
    rows = tuple((UUID(int=index), KICKOFF + timedelta(days=index // 2)) for index in range(10))

    result = chronological_partitions(rows)

    assert result[UUID(int=6)] is result[UUID(int=7)]
    assert set(result.values()) == {
        DevelopmentPartition.TRAIN,
        DevelopmentPartition.VALIDATION,
        DevelopmentPartition.DEVELOPMENT_HOLDOUT,
    }


def test_lineup_predictor_report_requires_both_improvements() -> None:
    prior = tuple(UUID(int=index) for index in range(10, 21))
    replacement = UUID(int=30)
    predicted = PredictedLineupV1(
        HOME,
        KICKOFF,
        KICKOFF - timedelta(hours=1),
        "4-3-3",
        COACH,
        "KNOWN",
        5,
        PredictionConfidence.HIGH,
        tuple(
            PredictedStarter(
                replacement if index == 10 else UUID(int=index),
                str(index),
                "CM",
                "CM",
                str(index),
                AvailabilityState.ASSUMED_AVAILABLE_NO_REPORTED_ISSUE,
                (
                    SelectionReason.MOST_USED_EXACT_POSITION_ALTERNATIVE
                    if index == 10
                    else SelectionReason.REPEATED_PREVIOUS_STARTER
                ),
                UUID(int=10) if index == 10 else None,
                AvailabilityState.UNAVAILABLE_INJURY if index == 10 else None,
            )
            for index in range(10, 21)
        ),
        (),
        UUID(int=1),
    )
    confirmed_players = (_player(30),) + tuple(_player(index) for index in range(11, 21))
    confirmed = _lineup(
        2,
        HOME,
        KICKOFF,
        KICKOFF - timedelta(minutes=30),
        confirmed_players,
    )

    report = validate_lineup_predictor(
        (
            LineupValidationCase(
                UUID(int=900),
                predicted,
                prior,
                confirmed,
                {UUID(int=10): AvailabilityState.UNAVAILABLE_INJURY},
            ),
        )
    )

    assert report.mean_correct_starters == 11.0
    assert report.naive_mean_correct_starters == 10.0
    assert report.replacement_player_accuracy == 1.0
    assert report.injured_starter_removal_accuracy == 1.0
    assert report.admitted


def test_manager_and_travel_coverage_gates_are_frozen() -> None:
    coverage = CoverageReport(500, 349, 151, 500)

    assert (
        coverage_gate(FeatureFamily.MANAGER, coverage, competition_domains=3)
        is FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE
    )
    assert (
        coverage_gate(FeatureFamily.TRAVEL, coverage, competition_domains=3)
        is FamilyDisposition.INSUFFICIENT_QUALIFIED_COVERAGE
    )


def test_only_active_predictive_context_changes_snapshot_identity(
    base_snapshot: ForecastInputSnapshot,
) -> None:
    context: dict[str, object] = {"home_days_since_last_match": 3.0}
    inactive = replace(base_snapshot, rest_context=context)
    changed_inactive = replace(inactive, rest_context={"home_days_since_last_match": 2.0})
    active = replace(
        inactive,
        predictive_context_families=(FeatureFamily.REST_CONGESTION.value,),
    )
    changed_active = replace(active, rest_context={"home_days_since_last_match": 2.0})

    assert (
        inactive.predictive_input_snapshot_sha256
        == changed_inactive.predictive_input_snapshot_sha256
    )
    assert (
        active.predictive_input_snapshot_sha256 != changed_active.predictive_input_snapshot_sha256
    )


@pytest.fixture
def base_snapshot() -> ForecastInputSnapshot:
    from football.forecasting.model_contracts import (
        CompetitionContext,
        FormWindow,
        RatingContext,
        RestContext,
    )

    form = FormWindow(0, None, None, None, None, None, None, None, None, None, 0, None)
    return ForecastInputSnapshot(
        UUID(int=10),
        UUID(int=11),
        CompetitionContext.LEAGUE,
        "2026/27",
        KICKOFF,
        HOME,
        AWAY,
        KICKOFF - timedelta(hours=1),
        KICKOFF - timedelta(hours=1),
        "STRICT_POINT_IN_TIME",
        (),
        form,
        form,
        form,
        form,
        form,
        form,
        form,
        form,
        RatingContext(1500.0, 1500.0, 0.0, 0.5),
        RestContext(None, 0, 0),
        RestContext(None, 0, 0),
        (),
    )
