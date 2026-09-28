#!/usr/bin/env python3
"""Measure strictly prior H2H coverage in the fixed development corpus."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from football.forecasting.transferable_npxg_dixon_coles_v2 import (
    ResearchObservationV2,
    ResearchRowV2,
    research_rows,
)

from scripts.run_transferable_npxg_dixon_coles_v2_research import (
    CORPUS_SHA256,
    FIREWALL_SHA256,
    SNAPSHOT_ID,
    SNAPSHOT_SHA256,
    load_development,
)

RESEARCH_ID = "MATCHFORGE_H2H_INCREMENTAL_SIGNAL_DESIGN_V1"
EXPECTED_TARGET_COUNT = 1_270
THRESHOLDS = (1, 2, 3, 5)
LOOKBACK_DAYS = 730.0
MAXIMUM_MEETINGS = 5
DECAY_HALF_LIFE_DAYS = 180.0
CONTINUITY_GAP_DAYS = 270.0
CONTINUITY_SCALE_DAYS = 365.0
PRIOR_SEASON_MULTIPLIER = 0.65
REVERSED_ORIENTATION_MULTIPLIER = 0.9
MAXIMUM_EFFECTIVE_WEIGHT = 1.5


@dataclass(frozen=True, slots=True)
class FrozenH2HTargetCoverage:
    scope_key: str
    competition: str
    usable_meetings: int
    same_orientation: int
    reversed_orientation: int
    latest_age_days: float | None
    effective_weight: float


def analyze_h2h_coverage(
    observations: Sequence[ResearchObservationV2],
    targets: Sequence[ResearchRowV2],
) -> dict[str, object]:
    """Return deterministic H2H coverage without fitting or scoring a model."""
    by_pair: dict[frozenset[UUID], list[ResearchObservationV2]] = defaultdict(list)
    for observation in observations:
        by_pair[frozenset((observation.home_team_id, observation.away_team_id))].append(observation)

    meeting_counts: Counter[int] = Counter()
    latest_ages: list[float] = []
    all_ages: list[float] = []
    scope_counts: dict[str, Counter[int]] = defaultdict(Counter)
    npxg_usable_counts: Counter[int] = Counter()
    orientation: Counter[str] = Counter()
    cross_scope_targets = 0

    for target in targets:
        prior = sorted(
            (
                observation
                for observation in by_pair[frozenset((target.home_team_id, target.away_team_id))]
                if observation.kickoff_at < target.kickoff_at
            ),
            key=lambda observation: (observation.kickoff_at, str(observation.match_id)),
        )
        count = len(prior)
        meeting_counts[count] += 1
        scope_counts[target.scope_key][count] += 1
        usable_npxg = sum(
            math.isfinite(observation.home_npxg)
            and observation.home_npxg >= 0.0
            and math.isfinite(observation.away_npxg)
            and observation.away_npxg >= 0.0
            for observation in prior
        )
        npxg_usable_counts[usable_npxg] += 1
        if not prior:
            continue
        ages = [
            (target.kickoff_at - observation.kickoff_at).total_seconds() / 86_400.0
            for observation in prior
        ]
        latest_ages.append(ages[-1])
        all_ages.extend(ages)
        orientation["same" if prior[-1].home_team_id == target.home_team_id else "reversed"] += 1
        if any(observation.scope_key != target.scope_key for observation in prior):
            cross_scope_targets += 1

    target_count = len(targets)
    coverage = {
        f"at_least_{threshold}": _coverage_record(meeting_counts, threshold, target_count)
        for threshold in THRESHOLDS
    }
    npxg_coverage = {
        f"at_least_{threshold}": _coverage_record(npxg_usable_counts, threshold, target_count)
        for threshold in THRESHOLDS
    }
    return {
        "contract": "MatchForgeH2HCoverageEvidenceV1",
        "research_id": RESEARCH_ID,
        "development_corpus": {
            "corpus_sha256": CORPUS_SHA256,
            "firewall_sha256": FIREWALL_SHA256,
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_sha256": SNAPSHOT_SHA256,
        },
        "source_observation_count": len(observations),
        "target_count": target_count,
        "strictly_prior_rule": "h2h_kickoff_at < target_kickoff_at",
        "coverage": coverage,
        "prior_meeting_count_distribution": {
            str(count): value for count, value in sorted(meeting_counts.items())
        },
        "usable_npxg_coverage": npxg_coverage,
        "latest_prior_meeting_age_days": _distribution(latest_ages),
        "all_prior_meeting_age_days": _distribution(all_ages),
        "latest_prior_meeting_age_buckets": _age_buckets(latest_ages),
        "latest_prior_orientation": dict(sorted(orientation.items())),
        "targets_with_cross_scope_history": cross_scope_targets,
        "coverage_by_scope": {
            scope: {
                "target_count": sum(counts.values()),
                "coverage": {
                    f"at_least_{threshold}": sum(
                        value for count, value in counts.items() if count >= threshold
                    )
                    for threshold in THRESHOLDS
                },
                "prior_meeting_count_distribution": {
                    str(count): value for count, value in sorted(counts.items())
                },
            }
            for scope, counts in sorted(scope_counts.items())
        },
    }


def analyze_frozen_h2h_coverage(
    observations: Sequence[ResearchObservationV2],
    targets: Sequence[ResearchRowV2],
    immediately_prior_scopes: Mapping[str, str | Sequence[str]],
) -> dict[str, object]:
    """Apply the frozen H2H lookback and weight contract to fixed targets."""
    by_pair: dict[frozenset[UUID], list[ResearchObservationV2]] = defaultdict(list)
    for observation in observations:
        by_pair[frozenset((observation.home_team_id, observation.away_team_id))].append(observation)
    records = tuple(
        _frozen_target_coverage(target, by_pair, immediately_prior_scopes) for target in targets
    )
    meeting_counts = Counter(record.usable_meetings for record in records)
    by_scope: dict[str, list[FrozenH2HTargetCoverage]] = defaultdict(list)
    by_competition: dict[str, list[FrozenH2HTargetCoverage]] = defaultdict(list)
    for record in records:
        by_scope[record.scope_key].append(record)
        by_competition[record.competition].append(record)
    effective_weights = [
        record.effective_weight for record in records if record.usable_meetings >= 2
    ]
    latest_ages = [
        record.latest_age_days for record in records if record.latest_age_days is not None
    ]
    return {
        "contract": "MatchForgeFrozenH2HCoverageEvidenceV1",
        "target_count": len(targets),
        "coverage": {
            f"at_least_{threshold}": _coverage_record(meeting_counts, threshold, len(targets))
            for threshold in THRESHOLDS
        },
        "prior_meeting_count_distribution": {
            str(count): value for count, value in sorted(meeting_counts.items())
        },
        "usable_npxg_coverage": {
            f"at_least_{threshold}": _coverage_record(meeting_counts, threshold, len(targets))
            for threshold in THRESHOLDS
        },
        "coverage_by_scope": {
            scope: _coverage_summary(values) for scope, values in sorted(by_scope.items())
        },
        "coverage_by_competition": {
            competition: _coverage_summary(values)
            for competition, values in sorted(by_competition.items())
        },
        "orientation": {
            "same": sum(record.same_orientation for record in records),
            "reversed": sum(record.reversed_orientation for record in records),
        },
        "latest_prior_meeting_age_days": _distribution(latest_ages),
        "effective_weight": _distribution(effective_weights),
        "frozen_contract": {
            "lookback_days": int(LOOKBACK_DAYS),
            "maximum_meetings": MAXIMUM_MEETINGS,
            "minimum_usable_meetings": 2,
            "decay_half_life_days": int(DECAY_HALF_LIFE_DAYS),
            "maximum_effective_weight": MAXIMUM_EFFECTIVE_WEIGHT,
        },
    }


def _frozen_target_coverage(
    target: ResearchRowV2,
    by_pair: Mapping[frozenset[UUID], Sequence[ResearchObservationV2]],
    immediately_prior_scopes: Mapping[str, str | Sequence[str]],
) -> FrozenH2HTargetCoverage:
    configured_prior = immediately_prior_scopes.get(target.scope_key, ())
    prior_scopes = (
        {configured_prior}
        if isinstance(configured_prior, str)
        else set(configured_prior)
    )
    eligible = sorted(
        (
            observation
            for observation in by_pair.get(
                frozenset((target.home_team_id, target.away_team_id)), ()
            )
            if observation.kickoff_at < target.kickoff_at
            and observation.competition == target.competition
            and _age_days(target.kickoff_at, observation.kickoff_at) <= LOOKBACK_DAYS
            and observation.scope_key in {target.scope_key, *prior_scopes}
            and math.isfinite(observation.home_npxg)
            and observation.home_npxg >= 0.0
            and math.isfinite(observation.away_npxg)
            and observation.away_npxg >= 0.0
        ),
        key=lambda observation: (observation.kickoff_at, str(observation.match_id)),
        reverse=True,
    )[:MAXIMUM_MEETINGS]
    weights: list[float] = []
    same = 0
    reversed_count = 0
    for index, observation in enumerate(eligible):
        same_orientation = observation.home_team_id == target.home_team_id
        same += int(same_orientation)
        reversed_count += int(not same_orientation)
        continuity = 1.0
        if index:
            gap = _age_days(eligible[index - 1].kickoff_at, observation.kickoff_at)
            continuity = math.exp(-max(0.0, gap - CONTINUITY_GAP_DAYS) / CONTINUITY_SCALE_DAYS)
        era = 1.0 if observation.scope_key == target.scope_key else PRIOR_SEASON_MULTIPLIER
        orientation = 1.0 if same_orientation else REVERSED_ORIENTATION_MULTIPLIER
        age = _age_days(target.kickoff_at, observation.kickoff_at)
        weights.append(2.0 ** (-age / DECAY_HALF_LIFE_DAYS) * continuity * era * orientation)
    return FrozenH2HTargetCoverage(
        scope_key=target.scope_key,
        competition=target.competition,
        usable_meetings=len(eligible),
        same_orientation=same,
        reversed_orientation=reversed_count,
        latest_age_days=(
            _age_days(target.kickoff_at, eligible[0].kickoff_at) if eligible else None
        ),
        effective_weight=min(MAXIMUM_EFFECTIVE_WEIGHT, sum(weights)),
    )


def _age_days(later: datetime, earlier: datetime) -> float:
    return (later - earlier).total_seconds() / 86_400.0


def _coverage_summary(records: Sequence[FrozenH2HTargetCoverage]) -> dict[str, object]:
    return {
        "target_count": len(records),
        "at_least_1": sum(record.usable_meetings >= 1 for record in records),
        "at_least_2": sum(record.usable_meetings >= 2 for record in records),
        "at_least_3": sum(record.usable_meetings >= 3 for record in records),
        "at_least_5": sum(record.usable_meetings >= 5 for record in records),
    }


def _coverage_record(counts: Mapping[int, int], threshold: int, total: int) -> dict[str, object]:
    count = sum(value for key, value in counts.items() if key >= threshold)
    return {"count": count, "fraction": count / total if total else 0.0}


def _distribution(values: Sequence[float]) -> dict[str, object]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "quantiles": {}}
    return {
        "count": len(ordered),
        "quantiles": {
            "minimum": _quantile(ordered, 0.0),
            "p10": _quantile(ordered, 0.10),
            "p25": _quantile(ordered, 0.25),
            "median": _quantile(ordered, 0.50),
            "p75": _quantile(ordered, 0.75),
            "p90": _quantile(ordered, 0.90),
            "maximum": _quantile(ordered, 1.0),
        },
    }


def _quantile(ordered: Sequence[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    return round(value, 6)


def _age_buckets(values: Sequence[float]) -> dict[str, int]:
    buckets = Counter(
        "0_to_90"
        if value <= 90.0
        else "over_90_to_180"
        if value <= 180.0
        else "over_180_to_365"
        if value <= 365.0
        else "over_365_to_730"
        if value <= 730.0
        else "over_730"
        for value in values
    )
    return {
        key: buckets[key]
        for key in (
            "0_to_90",
            "over_90_to_180",
            "over_180_to_365",
            "over_365_to_730",
            "over_730",
        )
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_root", type=Path)
    args = parser.parse_args()
    observations = load_development(cast(Path, args.snapshot_root))
    targets = research_rows(observations)
    if len(targets) != EXPECTED_TARGET_COUNT:
        raise RuntimeError(f"development target mismatch: {len(targets)}")
    print(json.dumps(analyze_h2h_coverage(observations, targets), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
