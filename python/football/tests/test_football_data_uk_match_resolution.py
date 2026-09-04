from __future__ import annotations

from datetime import UTC, date, datetime

from football.providers.football_data_uk_match_resolution import (
    FootballDataUkCanonicalMatchCandidateV1,
    FootballDataUkMatchResolutionContextV1,
    resolve_football_data_uk_match,
)


def test_match_resolution_auto_accepts_one_context_and_date_matched_candidate() -> None:
    result = resolve_football_data_uk_match(
        _context(),
        (
            FootballDataUkCanonicalMatchCandidateV1(
                canonical_match_id="canonical-match-1",
                provider_match_date=date(2016, 1, 3),
            ),
        ),
        decision_id="match-resolution-1",
        created_at=datetime(2026, 9, 4, 14, 30, tzinfo=UTC),
    )

    assert result.status == "RESOLVED"
    assert result.selected_canonical_match_id == "canonical-match-1"
    assert result.decision is not None
    assert result.decision.status == "AUTO_ACCEPTED"
    assert result.decision.subject_type == "match"


def test_match_resolution_quarantines_date_conflict_without_using_score() -> None:
    result = resolve_football_data_uk_match(
        _context(),
        (
            FootballDataUkCanonicalMatchCandidateV1(
                canonical_match_id="canonical-match-1",
                provider_match_date=date(2016, 1, 4),
            ),
        ),
        decision_id="match-resolution-date-conflict",
        created_at=datetime(2026, 9, 4, 14, 30, tzinfo=UTC),
    )

    assert result.status == "QUARANTINED"
    assert result.selected_canonical_match_id is None
    assert result.decision is None


def test_match_resolution_requires_review_for_multiple_context_qualified_candidates() -> None:
    result = resolve_football_data_uk_match(
        _context(),
        (
            FootballDataUkCanonicalMatchCandidateV1(
                canonical_match_id="canonical-match-1",
                provider_match_date=date(2016, 1, 3),
            ),
            FootballDataUkCanonicalMatchCandidateV1(
                canonical_match_id="canonical-match-2",
                provider_match_date=date(2016, 1, 3),
            ),
        ),
        decision_id="match-resolution-ambiguous",
        created_at=datetime(2026, 9, 4, 14, 30, tzinfo=UTC),
    )

    assert result.status == "REVIEW_REQUIRED"
    assert result.selected_canonical_match_id is None
    assert result.decision is not None
    assert result.decision.status == "REVIEW_REQUIRED"


def _context() -> FootballDataUkMatchResolutionContextV1:
    return FootballDataUkMatchResolutionContextV1(
        provider_match_ref="football_data_uk/source/record/1",
        canonical_competition_id="canonical-epl",
        canonical_season_id="canonical-epl-2015-16",
        canonical_home_team_id="canonical-team-a",
        canonical_away_team_id="canonical-team-b",
        provider_match_date=date(2016, 1, 3),
        evidence_refs=("source-row/1", "team-decision/a", "team-decision/b"),
    )
