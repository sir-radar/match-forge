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
    external_settlement_state,
    fixture_identity,
    forecast_from_history,
    league_rating,
    map_external_market,
    normalize_team_name,
)


def test_identity_name_normalization_preserves_letters_with_diacritics() -> None:
    assert normalize_team_name("Série C") == normalize_team_name("Serie C")
    assert normalize_team_name("Ferroviária FC") == "ferroviaria"


@pytest.mark.parametrize(
    ("provider_name", "canonical_name"),
    [
        ("Ulsan HD FC", "Ulsan Hyundai FC"),
        ("Gyeongju H & N", "Gyeongju HNP"),
        ("FC Mokpo", "Mokpo City"),
        ("CD Suchitepéquez", "Suchitepéquez"),
        ("Deportivo Mixco", "Mixco"),
    ],
)
def test_reviewed_club_aliases_are_deterministic(provider_name: str, canonical_name: str) -> None:
    assert normalize_team_name(provider_name) == normalize_team_name(canonical_name)


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
        ("Over 1.5", ("TOTAL_GOALS", "TOTAL_OVER_1_5")),
        ("Over 2.5", ("TOTAL_GOALS", "TOTAL_OVER_2_5")),
        ("Under 3.5", ("TOTAL_GOALS", "TOTAL_UNDER_3_5")),
    ],
)
def test_external_market_mapping(raw: str, expected: tuple[str, str]) -> None:
    assert map_external_market(raw) == expected


def test_agreement_is_independent_of_source_count() -> None:
    probabilities = {
        "home": 0.57,
        "draw": 0.24,
        "away": 0.19,
        "total_over_1_5": 0.72,
        "total_under_3_5": 0.68,
    }
    assert agreement_for_selection("RESULT_1X2", "HOME_WIN", probabilities) == Agreement.AGREES
    assert agreement_for_selection("RESULT_1X2", "DRAW", probabilities) == Agreement.DISAGREES
    assert (
        agreement_for_selection("TOTAL_GOALS", "TOTAL_OVER_1_5", probabilities) == Agreement.AGREES
    )
    assert (
        agreement_for_selection("TOTAL_GOALS", "TOTAL_UNDER_3_5", probabilities) == Agreement.AGREES
    )
    assert (
        agreement_for_selection("RESULT_1X2", "Draw No Bet", probabilities)
        == Agreement.UNABLE_TO_EVALUATE
    )
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
        ("TOTAL_GOALS", "TOTAL_OVER_1_5", (1, 1), True),
        ("TOTAL_GOALS", "TOTAL_OVER_2_5", (2, 1), True),
        ("TOTAL_GOALS", "TOTAL_UNDER_2_5", (1, 1), True),
        ("TOTAL_GOALS", "TOTAL_UNDER_3_5", (2, 1), True),
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


@pytest.mark.parametrize(
    ("status", "score", "score_basis", "expected"),
    [
        ("LIVE", (1, 0), "UNKNOWN", "PENDING"),
        ("POSTPONED", (None, None), "UNKNOWN", "PENDING"),
        ("CANCELLED", (None, None), "UNKNOWN", "VOID"),
        ("ABANDONED", (2, 1), "UNKNOWN", "VOID"),
        ("AWARDED", (3, 0), "UNKNOWN", "VOID"),
        ("FINISHED", (2, 1), "REGULATION_90", "WON"),
        ("FINISHED", (0, 1), "REGULATION_90", "LOST"),
        ("FINISHED", (2, 1), "EXTRA_TIME", "PENDING"),
        ("FINISHED", (4, 3), "PENALTY_SHOOTOUT", "PENDING"),
        ("FINISHED", (2, 1), "UNKNOWN", "PENDING"),
    ],
)
def test_external_settlement_requires_final_regulation_score(
    status: str,
    score: tuple[int | None, int | None],
    score_basis: str,
    expected: str,
) -> None:
    assert (
        external_settlement_state("RESULT_1X2", "HOME_WIN", status, *score, score_basis) == expected
    )


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
