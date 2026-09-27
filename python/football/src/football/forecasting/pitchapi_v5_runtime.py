"""Frozen-snapshot adapter for the proposed PitchAPI V5 evidence contract."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

from scipy.stats import ks_2samp

from football.forecasting.pitchapi_v3 import HistoryObservationV1
from football.forecasting.pitchapi_v3_runtime import (
    _DOMAINS,
    PitchApiSnapshotCorpusV4,
    _load_hashed,
    _quantile,
)
from football.forecasting.pitchapi_v5_evaluation import goal_on_xg_calibration

V5_PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V5"


class PitchApiSnapshotCorpusV5(PitchApiSnapshotCorpusV4):
    """Preserve V4 corpus semantics and add own-goal calibration categories."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._own_goal_flags: dict[str, list[bool]] = defaultdict(list)

    def preflight(self) -> Mapping[str, object]:
        result = dict(super().preflight())
        result["protocol_id"] = V5_PROTOCOL_ID
        return result

    def _read_observation(self, domain: str, manifest: dict[str, Any]) -> HistoryObservationV1:
        observation = super()._read_observation(domain, manifest)
        normalized = _load_hashed(self._root, "normalized", str(manifest["normalized_sha256"]))
        for period in cast(list[dict[str, Any]], normalized["data"]["periods"]):
            if period["period"] not in ("FirstHalf", "SecondHalf"):
                continue
            for shot in cast(list[dict[str, object]], period["shots"]):
                self._own_goal_flags[domain].append(shot.get("is_own_goal") is True)
        if len(self._own_goal_flags[domain]) != len(self._xg[domain]):
            raise RuntimeError("V5 own-goal calibration categories are misaligned")
        return observation

    def heterogeneity(self) -> Mapping[str, object]:
        domains: dict[str, object] = {}
        for domain in _DOMAINS:
            values = self._xg[domain]
            ordered = sorted(values)
            boundary = goal_on_xg_calibration(
                tuple(values),
                tuple(self._goals[domain]),
                tuple(self._own_goal_flags[domain]),
            )
            domains[domain] = {
                "goal_on_logit_xg_calibration": asdict(boundary.fit),
                "goal_on_logit_xg_input": {
                    "boundary_policy": "EXCLUDE_OWN_GOAL_XG_ZERO_AND_REPORT",
                    "interior_count": boundary.interior_count,
                    "own_goal_zero_count": boundary.own_goal_zero_count,
                    "raw_count": boundary.raw_count,
                    "raw_values_modified": False,
                },
                "npxg_count": len(values),
                "npxg_mean": sum(values) / len(values),
                "npxg_quantiles": {
                    "0.1": _quantile(ordered, 0.1),
                    "0.5": _quantile(ordered, 0.5),
                    "0.9": _quantile(ordered, 0.9),
                },
                "penalty_count": len(self._penalties[domain]),
                "penalty_mean": (
                    sum(self._penalties[domain]) / len(self._penalties[domain])
                    if self._penalties[domain]
                    else None
                ),
                "shot_situations": dict(sorted(self._situations[domain].items())),
            }
        pairwise = _pairwise(self._xg)
        situation_pairwise: list[dict[str, object]] = []
        names = tuple(_DOMAINS)
        situations = sorted({name for domain in _DOMAINS for name in self._situation_xg[domain]})
        for situation in situations:
            for left_index, left in enumerate(names):
                for right in names[left_index + 1 :]:
                    left_values = self._situation_xg[left][situation]
                    right_values = self._situation_xg[right][situation]
                    if not left_values or not right_values:
                        continue
                    result = ks_2samp(left_values, right_values, method="auto")
                    situation_pairwise.append(
                        {
                            "left": left,
                            "p_value": float(result.pvalue),
                            "right": right,
                            "situation": situation,
                            "statistic": float(result.statistic),
                        }
                    )
        return {
            "domains": domains,
            "pairwise_npxg_ks": pairwise,
            "pairwise_situation_xg_ks": situation_pairwise,
        }


def _pairwise(values: Mapping[str, list[float]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    names = tuple(_DOMAINS)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            result = ks_2samp(values[left], values[right], method="auto")
            output.append(
                {
                    "left": left,
                    "p_value": float(result.pvalue),
                    "right": right,
                    "statistic": float(result.statistic),
                }
            )
    return output
