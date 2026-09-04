from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from football.normalization.football_data_uk import FootballDataUkNormalizedMatchV1


class FootballDataUkOverlapSelectionError(ValueError):
    """The frozen overlap source cannot supply a safe bounded P1 prefix."""


@dataclass(frozen=True, slots=True)
class FootballDataUkOverlapPrefixSelectionV1:
    selection_rule_version: str
    provider_team_labels: frozenset[str]
    ordered_records: tuple[FootballDataUkNormalizedMatchV1, ...]
    selected_records: tuple[FootballDataUkNormalizedMatchV1, ...]
    selected_trusted_record_indexes: frozenset[int]


def select_football_data_uk_overlap_prefix(
    records: tuple[FootballDataUkNormalizedMatchV1, ...],
    *,
    corners_declared: bool,
    trusted_record_indexes: frozenset[int],
) -> FootballDataUkOverlapPrefixSelectionV1:
    """Select the shortest source-ordered prefix satisfying frozen P1 conditions."""

    if not records:
        raise FootballDataUkOverlapSelectionError("overlap source contains no records")
    indexes = [record.csv_record_index for record in records]
    if len(indexes) != len(set(indexes)):
        raise FootballDataUkOverlapSelectionError("overlap CSV record indexes must be unique")
    ordered_records = tuple(sorted(records, key=_source_order))
    provider_team_labels = frozenset(
        team
        for record in ordered_records
        for team in (record.provider_home_team_name, record.provider_away_team_name)
    )
    seen_teams: set[str] = set()
    corners_seen = not corners_declared
    trusted_match_seen = False
    selected_records: list[FootballDataUkNormalizedMatchV1] = []
    for record in ordered_records:
        selected_records.append(record)
        seen_teams.update((record.provider_home_team_name, record.provider_away_team_name))
        corners_seen = corners_seen or _has_corners(record)
        trusted_match_seen = trusted_match_seen or record.csv_record_index in trusted_record_indexes
        if seen_teams == provider_team_labels and corners_seen and trusted_match_seen:
            return FootballDataUkOverlapPrefixSelectionV1(
                selection_rule_version="FootballDataUkOverlapPrefixSelectionV1",
                provider_team_labels=provider_team_labels,
                ordered_records=ordered_records,
                selected_records=tuple(selected_records),
                selected_trusted_record_indexes=frozenset(
                    record.csv_record_index
                    for record in selected_records
                    if record.csv_record_index in trusted_record_indexes
                ),
            )
    raise FootballDataUkOverlapSelectionError(
        "overlap prefix cannot satisfy team, corner, and trusted match conditions"
    )


def _source_order(record: FootballDataUkNormalizedMatchV1) -> tuple[object, ...]:
    kickoff_time = record.provider_local_kickoff_time
    return (
        record.provider_match_date,
        kickoff_time is None,
        kickoff_time or time.max,
        record.csv_record_index,
    )


def _has_corners(record: FootballDataUkNormalizedMatchV1) -> bool:
    statistics = record.provider_aggregate_statistics
    return "HC" in statistics and "AC" in statistics
