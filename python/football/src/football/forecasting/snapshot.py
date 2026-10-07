from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from football.forecasting.elo import EloConfig, EloMatch, TeamEloModel
from football.forecasting.model_contracts import (
    CompetitionContext,
    ForecastInputSnapshot,
    FormWindow,
    H2HContext,
    HistoricalMatch,
    RatingContext,
    RestContext,
)

_H2H_HALF_LIFE_DAYS = 730.0
LOGGER = logging.getLogger(__name__)


def build_forecast_snapshot(
    *,
    fixture_id: UUID,
    competition_id: UUID,
    competition_context: CompetitionContext,
    season_label: str,
    kickoff_at: datetime,
    home_team_id: UUID,
    away_team_id: UUID,
    football_cutoff: datetime,
    knowledge_cutoff: datetime,
    knowledge_mode: str,
    history: Iterable[HistoricalMatch],
    source_references: tuple[str, ...] = (),
    availability_status: str = "UNKNOWN",
) -> ForecastInputSnapshot:
    for name, value in (
        ("kickoff_at", kickoff_at),
        ("football_cutoff", football_cutoff),
        ("knowledge_cutoff", knowledge_cutoff),
    ):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must include a timezone")
    if football_cutoff > kickoff_at:
        raise ValueError("football_cutoff must not follow kickoff")
    if home_team_id == away_team_id:
        raise ValueError("forecast teams must differ")
    qualified = tuple(
        sorted(
            (
                match
                for match in history
                if match.kickoff_at < football_cutoff and match.known_at <= knowledge_cutoff
            ),
            key=lambda match: (match.kickoff_at, str(match.fixture_id)),
        )
    )
    elo_model = TeamEloModel(EloConfig(model_version="snapshot-elo-v1"))
    elo_matches = tuple(
        EloMatch(
            match_id=match.fixture_id,
            competition_id=match.competition_id,
            kickoff_at=match.kickoff_at,
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            home_score=match.home_goals,
            away_score=match.away_goals,
        )
        for match in qualified
    )
    run = elo_model.rate(elo_matches)
    home_rating = elo_model.rating_before(run, home_team_id, football_cutoff)
    away_rating = elo_model.rating_before(run, away_team_id, football_cutoff)
    expected_home = _expected_home(home_rating, away_rating, 100.0)
    opponent_adjustments = _opponent_adjustments(run)
    home_rows = _team_rows(qualified, home_team_id, opponent_adjustments)
    away_rows = _team_rows(qualified, away_team_id, opponent_adjustments)
    home_league = tuple(
        row for row in home_rows if row.match.competition_context is CompetitionContext.LEAGUE
    )
    away_league = tuple(
        row for row in away_rows if row.match.competition_context is CompetitionContext.LEAGUE
    )
    missingness: list[str] = []
    if not any(row.xg_for is not None for row in home_rows[-10:]):
        missingness.append("HOME_XG_UNAVAILABLE")
    if not any(row.xg_for is not None for row in away_rows[-10:]):
        missingness.append("AWAY_XG_UNAVAILABLE")
    if availability_status == "UNKNOWN":
        missingness.append("AVAILABILITY_UNKNOWN")
    snapshot = ForecastInputSnapshot(
        fixture_id=fixture_id,
        competition_id=competition_id,
        competition_context=competition_context,
        season_label=season_label,
        kickoff_at=kickoff_at,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        football_cutoff=football_cutoff,
        knowledge_cutoff=knowledge_cutoff,
        knowledge_mode=knowledge_mode,
        qualified_history=qualified,
        home_form_5=_form(home_rows[-5:]),
        home_form_10=_form(home_rows[-10:]),
        away_form_5=_form(away_rows[-5:]),
        away_form_10=_form(away_rows[-10:]),
        home_home_form_10=_form(tuple(row for row in home_rows if row.is_home)[-10:]),
        away_away_form_10=_form(tuple(row for row in away_rows if not row.is_home)[-10:]),
        home_league_form_10=_form(home_league[-10:]),
        away_league_form_10=_form(away_league[-10:]),
        rating=RatingContext(
            home_rating=home_rating,
            away_rating=away_rating,
            rating_difference=home_rating - away_rating,
            rating_expected_home=expected_home,
        ),
        home_rest=_rest(home_rows, football_cutoff),
        away_rest=_rest(away_rows, football_cutoff),
        h2h=_h2h(qualified, home_team_id, away_team_id, football_cutoff),
        availability_status=availability_status,
        source_references=source_references,
        missingness=tuple(missingness),
    )
    LOGGER.info(
        "forecast snapshot built",
        extra={
            "fixture_id": str(fixture_id),
            "snapshot_sha256": snapshot.sha256,
            "qualified_matches": len(qualified),
        },
    )
    return snapshot


class _TeamRow:
    __slots__ = (
        "match",
        "is_home",
        "goals_for",
        "goals_against",
        "xg_for",
        "xg_against",
        "points",
        "opponent_adjusted_points",
    )

    def __init__(
        self,
        match: HistoricalMatch,
        team_id: UUID,
        opponent_adjusted_points: float,
    ) -> None:
        self.match = match
        self.is_home = match.home_team_id == team_id
        self.goals_for = match.home_goals if self.is_home else match.away_goals
        self.goals_against = match.away_goals if self.is_home else match.home_goals
        self.xg_for = match.home_xg if self.is_home else match.away_xg
        self.xg_against = match.away_xg if self.is_home else match.home_xg
        self.points = (
            3 if self.goals_for > self.goals_against else int(self.goals_for == self.goals_against)
        )
        self.opponent_adjusted_points = opponent_adjusted_points


def _team_rows(
    history: Sequence[HistoricalMatch],
    team_id: UUID,
    adjustments: dict[tuple[UUID, UUID], float],
) -> tuple[_TeamRow, ...]:
    return tuple(
        _TeamRow(match, team_id, adjustments[(match.fixture_id, team_id)])
        for match in history
        if team_id in (match.home_team_id, match.away_team_id)
    )


def _form(rows: Sequence[_TeamRow]) -> FormWindow:
    count = len(rows)
    if count == 0:
        return FormWindow(0, None, None, None, None, None, None, None, None, None, 0, None)
    goals_for = sum(row.goals_for for row in rows) / count
    goals_against = sum(row.goals_against for row in rows) / count
    xg_rows = tuple(row for row in rows if row.xg_for is not None and row.xg_against is not None)
    xg_for = sum(cast(float, row.xg_for) for row in xg_rows) / len(xg_rows) if xg_rows else None
    xg_against = (
        sum(cast(float, row.xg_against) for row in xg_rows) / len(xg_rows) if xg_rows else None
    )
    return FormWindow(
        match_count=count,
        goals_for=goals_for,
        goals_against=goals_against,
        xg_for=xg_for,
        xg_against=xg_against,
        goal_difference=goals_for - goals_against,
        xg_difference=xg_for - xg_against
        if xg_for is not None and xg_against is not None
        else None,
        points_per_match=sum(row.points for row in rows) / count,
        clean_sheet_rate=sum(row.goals_against == 0 for row in rows) / count,
        failed_to_score_rate=sum(row.goals_for == 0 for row in rows) / count,
        xg_sample_count=len(xg_rows),
        opponent_adjusted_points=sum(row.opponent_adjusted_points for row in rows) / count,
    )


def _rest(rows: Sequence[_TeamRow], cutoff: datetime) -> RestContext:
    if not rows:
        return RestContext(None, 0, 0)
    return RestContext(
        days_since_last_match=(cutoff - rows[-1].match.kickoff_at).total_seconds() / 86_400.0,
        matches_last_7_days=sum(row.match.kickoff_at >= cutoff - timedelta(days=7) for row in rows),
        matches_last_14_days=sum(
            row.match.kickoff_at >= cutoff - timedelta(days=14) for row in rows
        ),
    )


def _opponent_adjustments(run: object) -> dict[tuple[UUID, UUID], float]:
    values: dict[tuple[UUID, UUID], float] = {}
    for match in run.matches:  # type: ignore[attr-defined]
        values[(match.match_id, match.home_team_id)] = (
            match.actual_home_score - match.expected_home_score
        )
        values[(match.match_id, match.away_team_id)] = (
            match.expected_home_score - match.actual_home_score
        )
    return values


def _h2h(
    history: Sequence[HistoricalMatch],
    home_team_id: UUID,
    away_team_id: UUID,
    cutoff: datetime,
) -> tuple[H2HContext, ...]:
    meetings = tuple(
        match
        for match in history
        if {match.home_team_id, match.away_team_id} == {home_team_id, away_team_id}
    )
    return tuple(
        _h2h_category(meetings, context, home_team_id, cutoff) for context in CompetitionContext
    )


def _h2h_category(
    meetings: Sequence[HistoricalMatch],
    context: CompetitionContext,
    home_team_id: UUID,
    cutoff: datetime,
) -> H2HContext:
    rows = tuple(match for match in meetings if match.competition_context is context)
    if not rows:
        return H2HContext(context, 0, 0.0, None, None, None, None, None, None, None, None, None)
    weights = tuple(
        math.pow(0.5, (cutoff - match.kickoff_at).total_seconds() / 86_400.0 / _H2H_HALF_LIFE_DAYS)
        for match in rows
    )
    total_weight = sum(weights)
    effective = total_weight * total_weight / sum(weight * weight for weight in weights)

    def values(match: HistoricalMatch) -> tuple[int, int, float | None, float | None]:
        if match.home_team_id == home_team_id:
            return match.home_goals, match.away_goals, match.home_xg, match.away_xg
        return match.away_goals, match.home_goals, match.away_xg, match.home_xg

    oriented = tuple(values(match) for match in rows)
    wins = sum(weight for weight, row in zip(weights, oriented, strict=True) if row[0] > row[1])
    draws = sum(weight for weight, row in zip(weights, oriented, strict=True) if row[0] == row[1])
    xg = tuple(
        (weight, row[2], row[3])
        for weight, row in zip(weights, oriented, strict=True)
        if row[2] is not None and row[3] is not None
    )
    xg_weight = sum(row[0] for row in xg)
    return H2HContext(
        competition_context=context,
        sample_size=len(rows),
        effective_sample_size=effective,
        home_team_win_rate=wins / total_weight,
        draw_rate=draws / total_weight,
        away_team_win_rate=1.0 - (wins + draws) / total_weight,
        goals_for_mean=sum(weight * row[0] for weight, row in zip(weights, oriented, strict=True))
        / total_weight,
        goals_against_mean=sum(
            weight * row[1] for weight, row in zip(weights, oriented, strict=True)
        )
        / total_weight,
        goal_difference_mean=sum(
            weight * (row[0] - row[1]) for weight, row in zip(weights, oriented, strict=True)
        )
        / total_weight,
        xg_for_mean=sum(weight * float(home_xg) for weight, home_xg, _ in xg) / xg_weight
        if xg
        else None,
        xg_against_mean=sum(weight * float(away_xg) for weight, _, away_xg in xg) / xg_weight
        if xg
        else None,
        most_recent_at=max(match.kickoff_at for match in rows),
    )


def _expected_home(home_rating: float, away_rating: float, home_advantage: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (away_rating - home_rating - home_advantage) / 400.0))
