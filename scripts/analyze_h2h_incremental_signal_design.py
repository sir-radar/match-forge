#!/usr/bin/env python3
"""Measure strictly prior H2H coverage in the fixed development corpus."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
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
