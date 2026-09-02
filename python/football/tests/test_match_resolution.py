from __future__ import annotations

from datetime import UTC, datetime

import pytest
from football.ingestion import (
    MatchResolutionContextV1,
    MatchResolutionError,
    resolve_match_candidates,
)


def test_match_resolution_accepts_one_context_qualified_candidate() -> None:
    result = resolve_match_candidates(_context(), ("canonical-match-1",))

    assert result.status == "AUTO_ACCEPTED"
    assert result.selected_canonical_id == "canonical-match-1"


def test_match_resolution_reviews_ambiguity_and_quarantines_absence() -> None:
    context = _context()
    ambiguous = resolve_match_candidates(context, ("match-1", "match-2"))
    absent = resolve_match_candidates(context, ())

    assert ambiguous.status == "REVIEW_REQUIRED"
    assert ambiguous.selected_canonical_id is None
    assert absent.status == "QUARANTINED"


def test_match_resolution_rejects_duplicate_candidates_or_invalid_context() -> None:
    with pytest.raises(MatchResolutionError, match="candidates must be unique"):
        resolve_match_candidates(_context(), ("match-1", "match-1"))
    with pytest.raises(MatchResolutionError, match="teams must be distinct"):
        _context(away_team_id="home")


def _context(*, away_team_id: str = "away") -> MatchResolutionContextV1:
    return MatchResolutionContextV1(
        provider_id="totalcorner_api",
        provider_match_id="provider-match-1",
        competition_id="competition-1",
        season_id="season-1",
        home_team_id="home",
        away_team_id=away_team_id,
        kickoff_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
