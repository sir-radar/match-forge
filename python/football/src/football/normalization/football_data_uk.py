from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from types import MappingProxyType
from typing import Literal

from football.providers import FootballDataUkCsvRecordV1, FootballDataUkSourceResourceV1

_AGGREGATE_FIELDS = frozenset(
    (
        "HS",
        "AS",
        "HST",
        "AST",
        "HC",
        "AC",
        "HF",
        "AF",
        "HO",
        "AO",
        "HY",
        "AY",
        "HR",
        "AR",
        "HFKC",
        "AFKC",
        "HBP",
        "ABP",
        "HHW",
        "AHW",
    )
)

FootballDataUkResultV1 = Literal["HOME_WIN", "DRAW", "AWAY_WIN"]


class FootballDataUkNormalizationError(ValueError):
    """A Football-Data row cannot become a provider-normalized observation."""


@dataclass(frozen=True, slots=True)
class FootballDataUkNormalizedMatchV1:
    provider_match_ref: str
    source_resource_identity: str
    csv_record_index: int
    provider_competition_code: str
    provider_match_date: date
    provider_local_kickoff_time: time | None
    timezone: None
    kickoff_at: None
    provider_home_team_name: str
    provider_away_team_name: str
    full_time_home_goals: int
    full_time_away_goals: int
    full_time_result: FootballDataUkResultV1
    half_time_home_goals: int
    half_time_away_goals: int
    half_time_result: FootballDataUkResultV1
    provider_aggregate_statistics: Mapping[str, int]
    raw_values: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_aggregate_statistics",
            MappingProxyType(dict(self.provider_aggregate_statistics)),
        )
        object.__setattr__(self, "raw_values", MappingProxyType(dict(self.raw_values)))


def normalize_football_data_uk_record(
    receipt: FootballDataUkSourceResourceV1,
    record: FootballDataUkCsvRecordV1,
) -> FootballDataUkNormalizedMatchV1:
    """Normalize one aggregate row without creating event-level data."""

    values = record.values
    competition = _required_text(values, "Div")
    if competition != receipt.provider_competition_code:
        raise FootballDataUkNormalizationError(
            "provider competition conflicts with frozen resource"
        )
    full_time = _score(values, "FTHG", "FTAG", "FTR")
    half_time = _score(values, "HTHG", "HTAG", "HTR")
    return FootballDataUkNormalizedMatchV1(
        provider_match_ref=(f"{receipt.resource_identity}/record/{record.csv_record_index}"),
        source_resource_identity=receipt.resource_identity,
        csv_record_index=record.csv_record_index,
        provider_competition_code=competition,
        provider_match_date=_date(_required_text(values, "Date")),
        provider_local_kickoff_time=_time(values.get("Time", "")),
        timezone=None,
        kickoff_at=None,
        provider_home_team_name=_required_text(values, "HomeTeam"),
        provider_away_team_name=_required_text(values, "AwayTeam"),
        full_time_home_goals=full_time[0],
        full_time_away_goals=full_time[1],
        full_time_result=full_time[2],
        half_time_home_goals=half_time[0],
        half_time_away_goals=half_time[1],
        half_time_result=half_time[2],
        provider_aggregate_statistics=_aggregate_statistics(values),
        raw_values=values,
    )


def _required_text(values: Mapping[str, str], field: str) -> str:
    value = values.get(field)
    if value is None or value == "":
        raise FootballDataUkNormalizationError(f"{field} is required")
    return value


def _date(value: str) -> date:
    for format_string in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            continue
    raise FootballDataUkNormalizationError("Date must use dd/mm/yy or dd/mm/yyyy")


def _time(value: str) -> time | None:
    if value == "":
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _score(
    values: Mapping[str, str],
    home_field: str,
    away_field: str,
    result_field: str,
) -> tuple[int, int, FootballDataUkResultV1]:
    home = _nonnegative_integer(values, home_field)
    away = _nonnegative_integer(values, away_field)
    provider_result = _required_text(values, result_field)
    normalized_result = _result(home, away)
    expected = {"HOME_WIN": "H", "DRAW": "D", "AWAY_WIN": "A"}[normalized_result]
    if provider_result != expected:
        raise FootballDataUkNormalizationError(f"{result_field} is inconsistent with goals")
    return home, away, normalized_result


def _nonnegative_integer(values: Mapping[str, str], field: str) -> int:
    value = _required_text(values, field)
    try:
        parsed = int(value)
    except ValueError as error:
        raise FootballDataUkNormalizationError(f"{field} must be a non-negative integer") from error
    if parsed < 0 or str(parsed) != value:
        raise FootballDataUkNormalizationError(f"{field} must be a non-negative integer")
    return parsed


def _result(home_goals: int, away_goals: int) -> FootballDataUkResultV1:
    if home_goals > away_goals:
        return "HOME_WIN"
    if home_goals < away_goals:
        return "AWAY_WIN"
    return "DRAW"


def _aggregate_statistics(values: Mapping[str, str]) -> dict[str, int]:
    return {
        field: _nonnegative_integer(values, field)
        for field in _AGGREGATE_FIELDS & values.keys()
        if values[field] != ""
    }
