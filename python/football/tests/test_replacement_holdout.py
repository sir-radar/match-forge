from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from football.forecasting.replacement_holdout import (
    CHAMPION_MODEL_ID,
    COMPETITION_PRIOR_MODEL_ID,
    ChampionEligibility,
    ChampionEligibilityInput,
    ChampionIneligibilityReason,
    CompetitionPriorMatch,
    CompetitionPriorPoissonV1,
    ReferenceMode,
    ReferenceStackV1,
    champion_eligibility,
)

from scripts.prepare_full_coverage_v2_replacement_holdout import ROOT, _global_firewall

KICKOFF = datetime(2026, 8, 10, 15, tzinfo=UTC)
COMPETITION = UUID("11111111-1111-1111-1111-111111111111")


def _eligibility(home: int = 10, away: int = 10) -> ChampionEligibilityInput:
    return ChampionEligibilityInput(
        fixture_identity_resolved=True,
        home_identity_resolved=True,
        away_identity_resolved=True,
        competition_context_available=True,
        required_features_available=True,
        home_prior_match_count=home,
        away_prior_match_count=away,
    )


@pytest.mark.parametrize("count", (5, 9))
def test_champion_requires_ten_prior_matches(count: int) -> None:
    result = champion_eligibility(_eligibility(home=count))
    assert result.status is ChampionEligibility.INELIGIBLE
    assert result.reason is ChampionIneligibilityReason.HOME_INSUFFICIENT_HISTORY


def test_ten_prior_matches_still_requires_other_champion_preconditions() -> None:
    result = champion_eligibility(replace(_eligibility(), competition_context_available=False))
    assert result.status is ChampionEligibility.INELIGIBLE
    assert result.reason is ChampionIneligibilityReason.COMPETITION_CONTEXT_UNAVAILABLE


def test_both_low_history_has_specific_reason() -> None:
    result = champion_eligibility(_eligibility(home=9, away=5))
    assert result.reason is ChampionIneligibilityReason.BOTH_INSUFFICIENT_HISTORY


def test_eligibility_input_contains_no_outcome_fields() -> None:
    assert not {"home_goals", "away_goals", "result"} & set(
        ChampionEligibilityInput.__dataclass_fields__
    )


def test_reference_stack_routes_by_precomputed_eligibility() -> None:
    stack = ReferenceStackV1()
    eligible = stack.select(champion_eligibility(_eligibility()))
    ineligible = stack.select(champion_eligibility(_eligibility(home=9)))
    assert (eligible.model_id, eligible.mode) == (CHAMPION_MODEL_ID, ReferenceMode.CHAMPION)
    assert (ineligible.model_id, ineligible.mode) == (
        COMPETITION_PRIOR_MODEL_ID,
        ReferenceMode.COMPETITION_PRIOR,
    )


def test_competition_prior_uses_strictly_prior_competition_matches_only() -> None:
    history = (
        CompetitionPriorMatch(COMPETITION, KICKOFF - timedelta(days=2), 2, 1),
        CompetitionPriorMatch(COMPETITION, KICKOFF, 99, 99),
        CompetitionPriorMatch(UUID(int=2), KICKOFF - timedelta(days=3), 20, 20),
    )
    rates = CompetitionPriorPoissonV1(1.5, 1.1).rates(
        competition_id=COMPETITION, kickoff_at=KICKOFF, history=history
    )
    expected_weight = 1 / 21
    assert rates.prior_match_count == 1
    assert rates.lambda_home == pytest.approx(expected_weight * 2 + (1 - expected_weight) * 1.5)
    assert rates.lambda_away == pytest.approx(expected_weight * 1 + (1 - expected_weight) * 1.1)


def test_zero_competition_history_uses_frozen_global_prior() -> None:
    model = CompetitionPriorPoissonV1(1.6, 1.2)
    rates = model.rates(competition_id=COMPETITION, kickoff_at=KICKOFF, history=())
    assert (rates.lambda_home, rates.lambda_away, rates.prior_match_count) == (1.6, 1.2, 0)


def test_competition_prior_distribution_is_valid_and_team_neutral() -> None:
    model = CompetitionPriorPoissonV1(1.6, 1.2)
    first = model.distribution(competition_id=COMPETITION, kickoff_at=KICKOFF, history=())
    second = model.distribution(competition_id=COMPETITION, kickoff_at=KICKOFF, history=())
    assert first == second
    assert sum(sum(row) for row in first) == pytest.approx(1.0)
    assert all(value >= 0 for row in first for value in row)


def test_previous_full_corpus_and_spent_holdout_are_forbidden() -> None:
    corpus_path = Path(ROOT) / "docs/evaluation/full-coverage-v2-fresh-development-corpus-v1.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    targets = corpus["targets"]
    firewall = _global_firewall(Path(ROOT), targets)
    forbidden = set(cast(list[str], firewall["unique_forbidden_target_ids"]))
    full = {row["fixture_id"] for row in targets}
    holdout = {row["fixture_id"] for row in targets if row["split"] == "DEVELOPMENT_HOLDOUT"}
    assert len(full) == 1572
    assert len(holdout) == 315
    assert full <= forbidden
    assert holdout <= forbidden
