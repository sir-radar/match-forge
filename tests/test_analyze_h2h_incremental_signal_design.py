from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ResearchObservationV2,
    ResearchRowV2,
    RollingFeaturesV2,
)

from scripts.analyze_h2h_incremental_signal_design import (
    analyze_frozen_h2h_coverage,
    analyze_h2h_coverage,
)

HOME = UUID("00000000-0000-0000-0000-000000000001")
AWAY = UUID("00000000-0000-0000-0000-000000000002")
KICKOFF = datetime(2026, 1, 10, 15, tzinfo=UTC)


def _observation(index: int, kickoff: datetime, *, reverse: bool = False) -> ResearchObservationV2:
    return ResearchObservationV2(
        match_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
        scope_key="scope",
        competition="competition",
        kickoff_at=kickoff,
        home_team_id=AWAY if reverse else HOME,
        away_team_id=HOME if reverse else AWAY,
        home_goals=1,
        away_goals=0,
        home_npxg=1.1,
        away_npxg=0.7,
    )


def _target() -> ResearchRowV2:
    return ResearchRowV2(
        match_id=UUID("00000000-0000-0000-0000-000000000099"),
        scope_key="scope",
        competition="competition",
        kickoff_at=KICKOFF,
        home_team_id=HOME,
        away_team_id=AWAY,
        features=RollingFeaturesV2(*(1.0 for _ in range(8))),
        home_goals=0,
        away_goals=0,
    )


def test_h2h_coverage_excludes_same_kickoff_and_future_matches() -> None:
    evidence = analyze_h2h_coverage(
        (
            _observation(1, KICKOFF - timedelta(days=120), reverse=True),
            _observation(2, KICKOFF - timedelta(days=30)),
            _observation(3, KICKOFF),
            _observation(4, KICKOFF + timedelta(days=10)),
        ),
        (_target(),),
    )

    assert evidence["prior_meeting_count_distribution"] == {"2": 1}
    assert evidence["coverage"]["at_least_2"] == {"count": 1, "fraction": 1.0}
    assert evidence["usable_npxg_coverage"]["at_least_2"]["count"] == 1
    assert evidence["latest_prior_meeting_age_days"]["quantiles"]["median"] == 30.0
    assert evidence["latest_prior_orientation"] == {"same": 1}


def test_frozen_h2h_coverage_applies_lookback_meeting_cap_and_era_weight() -> None:
    prior = tuple(
        ResearchObservationV2(
            match_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
            scope_key="prior_scope",
            competition="competition",
            kickoff_at=KICKOFF - timedelta(days=days),
            home_team_id=HOME if index % 2 else AWAY,
            away_team_id=AWAY if index % 2 else HOME,
            home_goals=1,
            away_goals=0,
            home_npxg=1.0,
            away_npxg=0.5,
        )
        for index, days in enumerate((30, 120, 210, 300, 390, 480, 800), start=10)
    )

    evidence = analyze_frozen_h2h_coverage(
        (*prior, _observation(98, KICKOFF)),
        (_target(),),
        {"scope": "prior_scope"},
    )

    assert evidence["coverage"]["at_least_5"] == {"count": 1, "fraction": 1.0}
    assert evidence["prior_meeting_count_distribution"] == {"5": 1}
    assert evidence["orientation"] == {"same": 2, "reversed": 3}
    assert evidence["latest_prior_meeting_age_days"]["quantiles"]["median"] == 30.0
    assert 0.0 < evidence["effective_weight"]["quantiles"]["median"] <= 1.5


def test_frozen_h2h_coverage_accepts_bounded_second_prior_season() -> None:
    first = replace(_observation(20, KICKOFF - timedelta(days=300)), scope_key="prior_scope")
    second = replace(
        _observation(21, KICKOFF - timedelta(days=600)), scope_key="second_prior_scope"
    )

    evidence = analyze_frozen_h2h_coverage(
        (first, second),
        (_target(),),
        {"scope": ("prior_scope", "second_prior_scope")},
    )

    assert evidence["coverage"]["at_least_2"] == {"count": 1, "fraction": 1.0}
