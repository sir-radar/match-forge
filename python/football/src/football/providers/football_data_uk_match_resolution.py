from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from football.ingestion import ResolutionDecisionV1

FootballDataUkMatchResolutionStatusV1 = Literal["RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"]


class FootballDataUkMatchResolutionError(ValueError):
    """A Football-Data match lacks a safe canonical identity resolution."""


@dataclass(frozen=True, slots=True)
class FootballDataUkMatchResolutionContextV1:
    provider_match_ref: str
    canonical_competition_id: str
    canonical_season_id: str
    canonical_home_team_id: str
    canonical_away_team_id: str
    provider_match_date: date
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        identifiers = (
            self.provider_match_ref,
            self.canonical_competition_id,
            self.canonical_season_id,
            self.canonical_home_team_id,
            self.canonical_away_team_id,
        )
        if any(not identifier for identifier in identifiers):
            raise FootballDataUkMatchResolutionError("match resolution identifiers are required")
        if self.canonical_home_team_id == self.canonical_away_team_id:
            raise FootballDataUkMatchResolutionError("match teams must be distinct")
        if not self.evidence_refs or any(not ref for ref in self.evidence_refs):
            raise FootballDataUkMatchResolutionError("match resolution evidence is required")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise FootballDataUkMatchResolutionError("match resolution evidence must be unique")


@dataclass(frozen=True, slots=True)
class FootballDataUkCanonicalMatchCandidateV1:
    canonical_match_id: str
    provider_match_date: date

    def __post_init__(self) -> None:
        if not self.canonical_match_id:
            raise FootballDataUkMatchResolutionError("canonical match identifier is required")


@dataclass(frozen=True, slots=True)
class FootballDataUkMatchResolutionV1:
    status: FootballDataUkMatchResolutionStatusV1
    candidate_canonical_match_ids: tuple[str, ...]
    selected_canonical_match_id: str | None
    decision: ResolutionDecisionV1 | None
    reason: str


def resolve_football_data_uk_match(
    context: FootballDataUkMatchResolutionContextV1,
    candidates: tuple[FootballDataUkCanonicalMatchCandidateV1, ...],
    *,
    decision_id: str,
    created_at: datetime,
) -> FootballDataUkMatchResolutionV1:
    """Resolve exact reviewed context; provider result and statistics are not identity."""

    if not decision_id:
        raise FootballDataUkMatchResolutionError("match resolution decision identity is required")
    candidate_ids = tuple(candidate.canonical_match_id for candidate in candidates)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise FootballDataUkMatchResolutionError("canonical match candidates must be unique")
    if not candidates:
        return FootballDataUkMatchResolutionV1(
            status="QUARANTINED",
            candidate_canonical_match_ids=(),
            selected_canonical_match_id=None,
            decision=None,
            reason="no context-qualified canonical match candidate",
        )
    if len(candidates) == 1 and candidates[0].provider_match_date == context.provider_match_date:
        candidate = candidates[0]
        decision = ResolutionDecisionV1(
            decision_id=decision_id,
            subject_type="match",
            provider_id="football_data_uk",
            provider_entity_id=context.provider_match_ref,
            evidence_refs=context.evidence_refs,
            candidate_canonical_ids=candidate_ids,
            rule_version="FootballDataUkPhase1BMatchResolutionV1",
            confidence=1.0,
            status="AUTO_ACCEPTED",
            selected_canonical_id=candidate.canonical_match_id,
            actor="phase1b-football-data-match-resolution",
            reason="one candidate matches reviewed competition, season, ordered teams, and date",
            created_at=created_at,
        )
        return FootballDataUkMatchResolutionV1(
            status="RESOLVED",
            candidate_canonical_match_ids=candidate_ids,
            selected_canonical_match_id=candidate.canonical_match_id,
            decision=decision,
            reason="one context-qualified candidate corroborates provider match date",
        )
    if len(candidates) == 1:
        return FootballDataUkMatchResolutionV1(
            status="QUARANTINED",
            candidate_canonical_match_ids=candidate_ids,
            selected_canonical_match_id=None,
            decision=None,
            reason="one context-qualified candidate conflicts with provider match date",
        )
    decision = ResolutionDecisionV1(
        decision_id=decision_id,
        subject_type="match",
        provider_id="football_data_uk",
        provider_entity_id=context.provider_match_ref,
        evidence_refs=context.evidence_refs,
        candidate_canonical_ids=candidate_ids,
        rule_version="FootballDataUkPhase1BMatchResolutionV1",
        confidence=0.0,
        status="REVIEW_REQUIRED",
        selected_canonical_id=None,
        actor="phase1b-football-data-match-resolution",
        reason="multiple context-qualified canonical matches require review",
        created_at=created_at,
    )
    return FootballDataUkMatchResolutionV1(
        status="REVIEW_REQUIRED",
        candidate_canonical_match_ids=candidate_ids,
        selected_canonical_match_id=None,
        decision=decision,
        reason="multiple context-qualified candidates",
    )
