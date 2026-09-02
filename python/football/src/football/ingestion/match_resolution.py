from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.contracts.source import PROVIDER_PATTERN

MatchResolutionStatusV1 = Literal["AUTO_ACCEPTED", "REVIEW_REQUIRED", "QUARANTINED"]


class MatchResolutionError(ValueError):
    """A provider match cannot be resolved under the explicit context contract."""


@dataclass(frozen=True, slots=True)
class MatchResolutionContextV1:
    provider_id: str
    provider_match_id: str
    competition_id: str
    season_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime

    def __post_init__(self) -> None:
        if not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise MatchResolutionError("provider_id must use lowercase snake_case")
        if any(
            not value
            for value in (
                self.provider_match_id,
                self.competition_id,
                self.season_id,
                self.home_team_id,
                self.away_team_id,
            )
        ):
            raise MatchResolutionError("match resolution identifiers are required")
        if self.home_team_id == self.away_team_id:
            raise MatchResolutionError("match teams must be distinct")
        if self.kickoff_at.tzinfo is None:
            raise MatchResolutionError("match kickoff must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MatchResolutionResultV1:
    status: MatchResolutionStatusV1
    candidate_canonical_ids: tuple[str, ...]
    selected_canonical_id: str | None
    reason: str


def resolve_match_candidates(
    context: MatchResolutionContextV1,
    candidate_canonical_ids: tuple[str, ...],
) -> MatchResolutionResultV1:
    """Accept only one context-qualified candidate; quarantine ambiguity."""

    del context
    if len(candidate_canonical_ids) != len(set(candidate_canonical_ids)):
        raise MatchResolutionError("match resolution candidates must be unique")
    if not candidate_canonical_ids:
        return MatchResolutionResultV1(
            status="QUARANTINED",
            candidate_canonical_ids=(),
            selected_canonical_id=None,
            reason="no context-qualified match candidate",
        )
    if len(candidate_canonical_ids) > 1:
        return MatchResolutionResultV1(
            status="REVIEW_REQUIRED",
            candidate_canonical_ids=candidate_canonical_ids,
            selected_canonical_id=None,
            reason="multiple context-qualified match candidates",
        )
    return MatchResolutionResultV1(
        status="AUTO_ACCEPTED",
        candidate_canonical_ids=candidate_canonical_ids,
        selected_canonical_id=candidate_canonical_ids[0],
        reason="one context-qualified match candidate",
    )
