from datetime import UTC, datetime, timedelta
from uuid import UUID

from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ResearchObservationV2,
    ResearchRowV2,
    RollingFeaturesV2,
)

from scripts.analyze_h2h_incremental_signal_design import analyze_h2h_coverage

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
