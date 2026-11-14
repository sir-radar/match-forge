"""EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1: external-only fixture association.

The policy links an external pick to one existing MatchForge fixture when the
source's teams, competition and date leave exactly one credible fixture. It is
outcome-blind: it reads teams, competition and kickoff, never status or scores.

A contextual match is evidence for external settlement only. It never creates
provider mappings, team identities, duplicate resolutions or canonical history.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from football.product.external_match_context import (
    CompetitionContext,
    CompetitionRelation,
    NameForm,
    NameRule,
    competition_context,
    competition_relation,
    match_name,
    name_form,
)

POLICY_VERSION = "EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1"

Classification = Literal["VERIFIED", "CONTEXTUAL_MATCH", "NEEDS_REVIEW", "UNMATCHED"]
DateRelation = Literal[
    "EXACT_KICKOFF",
    "SAME_DAY",
    "MIDNIGHT_ADJACENT",
    "ADJACENT_DAY",
    "RESCHEDULED",
    "KICKOFF_MISMATCH",
]

# Day boundaries each source publishes in. R2Bet pages show UTC+01:00 kickoffs;
# the other pages carry no timezone, so both UTC and the collector's day count.
SOURCE_TIMEZONES: dict[str, tuple[str, ...]] = {"r2bet": ("Africa/Lagos",)}
DEFAULT_TIMEZONES = ("UTC", "Africa/Lagos")
# A kickoff this close to the source day's boundary may print on the other day.
MIDNIGHT_WINDOW = timedelta(hours=3)
# Candidate fixtures are loaded this many days either side of the prediction date.
SEARCH_DAYS = 2
# One-sided candidates kept on an UNMATCHED decision for review.
NEAR_CANDIDATES = 5
ACCEPTED_DATES = frozenset({"EXACT_KICKOFF", "SAME_DAY", "MIDNIGHT_ADJACENT"})
UNRESOLVED_RESOLUTIONS = frozenset(
    {"AMBIGUOUS_QUARANTINED", "IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED"}
)


@dataclass(frozen=True, slots=True)
class SourcePrediction:
    """The retained source facts the policy may use."""

    source_code: str
    prediction_date: date
    competition: str
    home_team: str
    away_team: str
    source_kickoff_at: datetime | None = None
    conflicting_evidence: bool = False


@dataclass(frozen=True, slots=True)
class CandidateFixture:
    """A catalogue fixture near the prediction date; no status or score fields."""

    fixture_id: UUID
    kickoff_at: datetime
    home_names: tuple[str, ...]
    away_names: tuple[str, ...]
    competition_name: str
    competition_country: str
    competition_type: str
    division: int | None
    identity_status: str
    effective_fixture_id: UUID
    resolution_status: str | None = None
    earlier_kickoffs: tuple[datetime, ...] = ()


@dataclass(frozen=True, slots=True)
class Assessment:
    fixture: CandidateFixture
    home: NameRule | None
    away: NameRule | None
    reversed: bool
    competition: CompetitionRelation
    date: DateRelation | None

    @property
    def paired(self) -> bool:
        return self.home is not None and self.away is not None and self.date is not None

    @property
    def strong(self) -> bool:
        return (
            self.paired
            and not self.reversed
            and self.date in ACCEPTED_DATES
            and self.competition != "CONFLICT"
        )

    @property
    def unresolved(self) -> bool:
        return (
            self.fixture.resolution_status in UNRESOLVED_RESOLUTIONS
            or self.fixture.identity_status == "QUARANTINED"
        )

    def evidence(self) -> dict[str, Any]:
        fixture = self.fixture
        return {
            "fixture_id": str(fixture.fixture_id),
            "effective_fixture_id": str(fixture.effective_fixture_id),
            "kickoff_at": fixture.kickoff_at.isoformat(),
            "home_team": fixture.home_names[0],
            "away_team": fixture.away_names[0],
            "competition": fixture.competition_name,
            "competition_country": fixture.competition_country,
            "identity_status": fixture.identity_status,
            "resolution_status": fixture.resolution_status,
            "home_rule": self.home,
            "away_rule": self.away,
            "orientation": "REVERSED" if self.reversed else "HOME_AWAY",
            "competition_relation": self.competition,
            "date_relation": self.date,
        }


@dataclass(frozen=True, slots=True)
class Decision:
    classification: Classification
    reason: str
    fixture_id: UUID | None = None
    candidates: tuple[Assessment, ...] = field(default=())

    def evidence(self, source: SourcePrediction) -> dict[str, Any]:
        chosen = next(
            (
                item
                for item in self.candidates
                if item.fixture.effective_fixture_id == self.fixture_id
            ),
            None,
        )
        return {
            "policy_version": POLICY_VERSION,
            "classification": self.classification,
            "reason": self.reason,
            "fixture_id": str(self.fixture_id) if self.fixture_id else None,
            "date_relation": chosen.date if chosen else None,
            "source": {
                "source_code": source.source_code,
                "prediction_date": source.prediction_date.isoformat(),
                "competition": source.competition,
                "home_team": source.home_team,
                "away_team": source.away_team,
                "source_kickoff_at": source.source_kickoff_at.isoformat()
                if source.source_kickoff_at
                else None,
                "timezones": list(source_timezones(source.source_code)),
            },
            "candidates": [item.evidence() for item in self.candidates],
        }


def source_timezones(source_code: str) -> tuple[str, ...]:
    return SOURCE_TIMEZONES.get(source_code, DEFAULT_TIMEZONES)


def search_window(prediction_date: date) -> tuple[date, date]:
    return prediction_date - timedelta(days=SEARCH_DAYS), prediction_date + timedelta(
        days=SEARCH_DAYS + 1
    )


def decide(
    source: SourcePrediction,
    fixtures: Sequence[CandidateFixture],
    countries: frozenset[str],
) -> Decision:
    """Classify one prediction against the fixtures in its search window."""
    home, away = name_form(source.home_team), name_form(source.away_team)
    if not home.core or not away.core:
        return Decision("UNMATCHED", "SOURCE_CONTEXT_MISSING")
    context = competition_context(source.competition, countries)
    assessments = [
        _assess(source, home, away, context, fixture)
        for fixture in fixtures
        if _mentions(home, fixture) or _mentions(away, fixture)
    ]
    paired = _ranked(item for item in assessments if item.paired)
    if paired:
        return _classify_paired(source, context.known, paired)
    if not fixtures:
        return Decision("UNMATCHED", "NO_FIXTURES_FOR_DATE")
    # One-sided fixtures on nearby days are kept so a reviewer can see what was close.
    near = _ranked(item for item in assessments if item.date and (item.home or item.away))
    if any(_plausible_opponent_miss(item) for item in near):
        return Decision("NEEDS_REVIEW", "OPPONENT_UNCONFIRMED", candidates=near[:NEAR_CANDIDATES])
    if near:
        return Decision("UNMATCHED", "ONE_TEAM_ONLY", candidates=near[:NEAR_CANDIDATES])
    return Decision("UNMATCHED", "NO_CORRESPONDING_FIXTURE")


def _plausible_opponent_miss(item: Assessment) -> bool:
    """One team exact on the source day: credible enough for review, never automatic."""
    return (
        "EXACT" in (item.home, item.away)
        and item.date == "SAME_DAY"
        and not item.reversed
        and item.competition != "CONFLICT"
    )


def _classify_paired(
    source: SourcePrediction, competition_known: bool, paired: tuple[Assessment, ...]
) -> Decision:
    chosen, reason = _single_fixture(paired)
    if chosen is None:
        return Decision("NEEDS_REVIEW", reason, candidates=paired)
    review = _review_reason(source, competition_known, chosen)
    if review:
        return Decision("NEEDS_REVIEW", review, candidates=paired)
    return Decision("CONTEXTUAL_MATCH", reason, chosen.fixture.effective_fixture_id, paired)


def _single_fixture(paired: tuple[Assessment, ...]) -> tuple[Assessment | None, str]:
    """The one fixture the paired candidates describe, or the reason there is none."""
    strong = [item for item in paired if item.strong]
    if not strong:
        return None, _blocker(paired[0])
    if len({item.fixture.effective_fixture_id for item in paired}) == 1:
        if any(item.unresolved for item in paired):
            return None, "CANONICAL_IDENTITY_UNRESOLVED"
        return strong[0], "UNIQUE_" + str(strong[0].date)
    twin = _verified_twin(paired)
    return (twin, "UNIQUE_VERIFIED_TWIN") if twin else (None, "MULTIPLE_CANDIDATES")


def _verified_twin(paired: tuple[Assessment, ...]) -> Assessment | None:
    """One VERIFIED record whose rivals are PROVISIONAL copies at the identical kickoff.

    Unresolved twins stay unresolved canonically; only the external association
    uses the VERIFIED record. Two VERIFIED records, a moved kickoff or any weaker
    rival still needs review.
    """
    if any(not item.strong for item in paired) or len({i.fixture.kickoff_at for i in paired}) > 1:
        return None
    verified = [
        item
        for item in paired
        if item.fixture.identity_status == "VERIFIED" and not item.unresolved
    ]
    targets = {item.fixture.effective_fixture_id for item in verified}
    rivals = [item for item in paired if item.fixture.effective_fixture_id not in targets]
    if len(targets) != 1 or any(item.fixture.identity_status != "PROVISIONAL" for item in rivals):
        return None
    return verified[0]


def _review_reason(
    source: SourcePrediction, competition_known: bool, chosen: Assessment
) -> str | None:
    if source.conflicting_evidence:
        return "SOURCE_EVIDENCE_CONFLICT"
    weak_name = "VARIANT" in (chosen.home, chosen.away)
    if not competition_known and (weak_name or chosen.date == "MIDNIGHT_ADJACENT"):
        return "WEAK_CORROBORATION"
    return None


def _blocker(item: Assessment) -> str:
    if item.date == "KICKOFF_MISMATCH":
        return "KICKOFF_MISMATCH"
    if item.date == "RESCHEDULED":
        return "RESCHEDULED_KICKOFF"
    if item.date == "ADJACENT_DAY":
        return "DATE_OFFSET"
    if item.reversed:
        return "HOME_AWAY_REVERSED"
    return "COMPETITION_MISMATCH"


def _ranked(items: Iterable[Assessment]) -> tuple[Assessment, ...]:
    """Strongest first, then a stable fixture order; never a nearest-match pick."""
    return tuple(
        sorted(
            items,
            key=lambda item: (
                not item.strong,
                item.reversed,
                item.date not in ACCEPTED_DATES,
                item.competition == "CONFLICT",
                item.fixture.kickoff_at,
                str(item.fixture.fixture_id),
            ),
        )
    )


def _assess(
    source: SourcePrediction,
    home: NameForm,
    away: NameForm,
    context: CompetitionContext,
    fixture: CandidateFixture,
) -> Assessment:
    straight = (_best(home, fixture.home_names), _best(away, fixture.away_names))
    swapped = (_best(home, fixture.away_names), _best(away, fixture.home_names))
    reversed_only = None in straight and None not in swapped
    rules = swapped if reversed_only else straight
    return Assessment(
        fixture=fixture,
        home=rules[0],
        away=rules[1],
        reversed=reversed_only,
        competition=competition_relation(
            context,
            name=fixture.competition_name,
            country=fixture.competition_country,
            competition_type=fixture.competition_type,
            division=fixture.division,
        ),
        date=date_relation(source, fixture),
    )


def _mentions(source: NameForm, fixture: CandidateFixture) -> bool:
    """Cheap first-word screen; match_name requires the first words to correspond."""
    word, abbreviated = source.core[0]
    leading = source.canonical.split(" ", 1)[0]
    return any(
        key in (word, leading)
        or (abbreviated and key.startswith(word))
        or (key_abbreviated and word.startswith(key))
        for key, key_abbreviated in _leading_words(fixture.home_names + fixture.away_names)
    )


@lru_cache(maxsize=262144)
def _leading_words(names: tuple[str, ...]) -> frozenset[tuple[str, bool]]:
    forms = [name_form(name) for name in names]
    return frozenset(
        {form.core[0] for form in forms if form.core}
        | {(form.canonical.split(" ", 1)[0], False) for form in forms if form.canonical}
    )


def _best(source: NameForm, names: tuple[str, ...]) -> NameRule | None:
    rules = {match_name(source, name_form(name)) for name in names}
    return "EXACT" if "EXACT" in rules else "VARIANT" if "VARIANT" in rules else None


def date_relation(source: SourcePrediction, fixture: CandidateFixture) -> DateRelation | None:
    """How the fixture's kickoff relates to the day the source published the pick."""
    if source.source_kickoff_at is not None:
        if source.source_kickoff_at == fixture.kickoff_at:
            return "EXACT_KICKOFF"
        if _day_offset(source, fixture.kickoff_at) == 0:
            return "KICKOFF_MISMATCH"
    offset = _day_offset(source, fixture.kickoff_at)
    if offset == 0:
        return "SAME_DAY"
    if abs(offset) == 1:
        return "MIDNIGHT_ADJACENT" if _near_boundary(source, fixture.kickoff_at) else "ADJACENT_DAY"
    if any(_day_offset(source, kickoff) == 0 for kickoff in fixture.earlier_kickoffs):
        return "RESCHEDULED"
    return None


def _day_offset(source: SourcePrediction, kickoff: datetime) -> int:
    offsets = [
        (kickoff.astimezone(ZoneInfo(zone)).date() - source.prediction_date).days
        for zone in source_timezones(source.source_code)
    ]
    return min(offsets, key=abs)


def _near_boundary(source: SourcePrediction, kickoff: datetime) -> bool:
    """True when the kickoff is within MIDNIGHT_WINDOW of the source day's edge."""
    for zone in source_timezones(source.source_code):
        local = kickoff.astimezone(ZoneInfo(zone))
        day_start = datetime.combine(source.prediction_date, datetime.min.time(), local.tzinfo)
        day_end = day_start + timedelta(days=1)
        if day_start - MIDNIGHT_WINDOW <= local < day_end + MIDNIGHT_WINDOW:
            return True
    return False
