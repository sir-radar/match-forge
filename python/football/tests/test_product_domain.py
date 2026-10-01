from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.product.domain import (
    Agreement,
    FinishedMatch,
    LeagueRating,
    agreement_for_selection,
    external_selection_correct,
    fixture_identity,
    forecast_from_history,
    league_rating,
    map_external_market,
    normalize_team_name,
)


def test_provider_team_name_normalization_uses_only_deterministic_aliases() -> None:
    assert normalize_team_name("Man United FC") == normalize_team_name("Man Utd")
    assert normalize_team_name("Inter Milan") == normalize_team_name("Internazionale")
    assert normalize_team_name("PSG") == normalize_team_name("Paris Saint-Germain")


ARTIFACT = Path("docs/evaluation/pitchapi-v3-models/pitchapi-v3-reference-artifact.json")
HOME = UUID("00000000-0000-0000-0000-000000000001")
AWAY = UUID("00000000-0000-0000-0000-000000000002")
OPPONENT = UUID("00000000-0000-0000-0000-000000000003")
COMPETITION = UUID("00000000-0000-0000-0000-000000000004")


def test_fixture_identity_is_provider_neutral_and_stable() -> None:
    kickoff = datetime(2026, 9, 29, 18, tzinfo=UTC)
    first = fixture_identity(COMPETITION, "2026", kickoff, HOME, AWAY)
    second = fixture_identity(COMPETITION, " 2026 ", kickoff, HOME, AWAY)
    assert first == second


def test_team_name_normalization_handles_common_aliases() -> None:
    assert normalize_team_name("Manchester Utd FC") == "manchester united"
    assert normalize_team_name("Manchester United") == "manchester united"


def test_forecast_requires_ten_prior_matches_per_team() -> None:
    target = datetime(2026, 9, 29, 18, tzinfo=UTC)
    assert (
        forecast_from_history(
            artifact_path=ARTIFACT,
            target_kickoff=target,
            home_team_id=HOME,
            away_team_id=AWAY,
            history=_history(target, 9),
        )
        is None
    )


def test_forecast_uses_only_pre_kickoff_history_and_returns_coherent_probabilities() -> None:
    target = datetime(2026, 9, 29, 18, tzinfo=UTC)
    history = _history(target, 10)
    history.append(
        FinishedMatch(
            fixture_id=UUID(int=999),
            kickoff_at=target,
            home_team_id=HOME,
            away_team_id=AWAY,
            home_goals=99,
            away_goals=0,
        )
    )
    forecast = forecast_from_history(
        artifact_path=ARTIFACT,
        target_kickoff=target,
        home_team_id=HOME,
        away_team_id=AWAY,
        history=history,
    )
    assert forecast is not None
    assert (
        forecast.home_probability + forecast.draw_probability + forecast.away_probability
        == pytest.approx(1.0)
    )
    assert forecast.expected_home_goals < 10
    assert forecast.score_matrix


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", ("RESULT_1X2", "HOME_WIN")),
        ("X2", ("DOUBLE_CHANCE", "DRAW_OR_AWAY")),
        ("GG", ("BTTS", "BTTS_YES")),
        ("Over 2.5", ("TOTAL_GOALS", "TOTAL_OVER_2_5")),
    ],
)
def test_external_market_mapping(raw: str, expected: tuple[str, str]) -> None:
    assert map_external_market(raw) == expected


def test_agreement_is_independent_of_source_count() -> None:
    probabilities = {"home": 0.57, "draw": 0.24, "away": 0.19}
    assert agreement_for_selection("RESULT_1X2", "HOME_WIN", probabilities) == Agreement.AGREES
    assert agreement_for_selection("RESULT_1X2", "DRAW", probabilities) == Agreement.DISAGREES
    assert (
        agreement_for_selection("UNKNOWN", "UNKNOWN", probabilities) == Agreement.UNABLE_TO_EVALUATE
    )


@pytest.mark.parametrize(
    ("market", "selection", "score", "expected"),
    [
        ("RESULT_1X2", "HOME_WIN", (2, 1), True),
        ("RESULT_1X2", "DRAW", (2, 1), False),
        ("DOUBLE_CHANCE", "DRAW_OR_AWAY", (1, 1), True),
        ("BTTS", "BTTS_YES", (3, 0), False),
        ("TOTAL_GOALS", "TOTAL_OVER_2_5", (2, 1), True),
        ("TOTAL_GOALS", "TOTAL_UNDER_2_5", (1, 1), True),
        ("UNKNOWN", "UNKNOWN", (1, 1), None),
    ],
)
def test_external_selection_settlement(
    market: str,
    selection: str,
    score: tuple[int, int],
    expected: bool | None,
) -> None:
    assert external_selection_correct(market, selection, *score) is expected


def test_league_rating_thresholds() -> None:
    common = dict(
        brier=0.55,
        log_loss=0.95,
        baseline_brier=0.60,
        baseline_log_loss=1.01,
        recent_brier=0.54,
        recent_log_loss=0.94,
        recent_baseline_brier=0.61,
        recent_baseline_log_loss=1.02,
    )
    assert league_rating(total_forecasts=49, **common) == LeagueRating.UNRATED
    assert league_rating(total_forecasts=50, **common) == LeagueRating.GOOD
    assert league_rating(total_forecasts=100, **common) == LeagueRating.STRONG


def _history(target: datetime, count: int) -> list[FinishedMatch]:
    rows: list[FinishedMatch] = []
    for index in range(count):
        kickoff = target - timedelta(days=count - index)
        rows.extend(
            (
                FinishedMatch(UUID(int=index * 2 + 10), kickoff, HOME, OPPONENT, 2, 1),
                FinishedMatch(UUID(int=index * 2 + 11), kickoff, AWAY, OPPONENT, 1, 1),
            )
        )
    return rows
