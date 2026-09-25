#!/usr/bin/env python3
"""Compare raw and logistic-recalibrated xG on the frozen development scope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

import numpy as np
from analyze_pitchapi_snapshot_v1 import _logistic_fit
from football.contracts.source import canonical_json_bytes

_SNAPSHOT_DOCUMENT = (
    "manifests/sha256/b3/b390a335b8c2cb94a1cdbfe220d78b02cdd812eeee2144c97e02cf42b59487f5.json"
)
_DEVELOPMENT_MANIFEST = (
    "manifests/sha256/be/be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e.json"
)


def analyze(root: Path) -> dict[str, object]:
    snapshot = _load_json(root / _SNAPSHOT_DOCUMENT)
    season = _load_json(root / _DEVELOPMENT_MANIFEST)
    kickoffs = {
        str(match["provider_match_id"]): str(
            _load_json(root / str(match["manifest_path"]))["kickoff_at"]
        )
        for match in cast(list[dict[str, object]], season["matches"])
    }
    resources = {
        str(resource["resource_ref"]).rsplit(":", 1)[-1]: resource
        for resource in cast(list[dict[str, object]], snapshot["resources"])
        if resource["scope_key"] == "bundesliga_2021_22" and resource["kind"] == "match_shots"
    }
    matches = sorted(
        (
            kickoffs[match_id],
            match_id,
            _non_penalty_shots(root / str(resource["normalized_relative_path"])),
        )
        for match_id, resource in resources.items()
    )
    held_out: list[tuple[int, float, float, float, float]] = []
    fold_parameters: list[list[float]] = []
    for fold in range(4):
        train_end = round(len(matches) * (fold + 1) / 5)
        validation_end = round(len(matches) * (fold + 2) / 5)
        parameters = _fit(matches[:train_end])
        fold_parameters.append(list(parameters))
        held_out.extend(
            _score(parameters, values)
            for _kickoff, _match_id, values in matches[train_end:validation_end]
        )
    log_delta, brier_delta = _pooled_deltas(held_out)
    intervals = _bootstrap_intervals(held_out)
    selected = (
        "LOGISTIC_RECALIBRATION"
        if log_delta < 0
        and intervals["log_loss"][1] < 0
        and brier_delta <= 0
        and intervals["brier_score"][1] <= 0
        else "RAW"
    )
    full_fit = _fit(matches)
    return {
        "contract": "PitchApiV2DevelopmentXgComparisonV1",
        "protocol_id": "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2",
        "development_scope": "bundesliga_2021_22",
        "development_matches": len(matches),
        "development_non_penalty_shots": sum(len(values) for _, _, values in matches),
        "folds": 4,
        "held_out_matches": len(held_out),
        "held_out_non_penalty_shots": sum(row[0] for row in held_out),
        "bootstrap_replicates": 2000,
        "bootstrap_seed": 20260924,
        "fold_parameters": fold_parameters,
        "transformed_minus_raw_log_loss": log_delta,
        "log_loss_interval_95": intervals["log_loss"],
        "transformed_minus_raw_brier": brier_delta,
        "brier_interval_95": intervals["brier_score"],
        "selected_treatment": selected,
        "unselected_full_development_fit": {
            "intercept": full_fit[0],
            "slope": full_fit[1],
        },
        "evaluation_scope_loaded": False,
        "evaluation_executed": False,
    }


def _load_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _non_penalty_shots(path: Path) -> list[tuple[float, float]]:
    payload = _load_json(path)
    result: list[tuple[float, float]] = []
    for period in payload["data"]["periods"]:
        for shot in period["shots"]:
            if shot["situation"] != "Penalty":
                result.append(
                    (float(shot["expected_goals"]), 1.0 if shot["event_type"] == "Goal" else 0.0)
                )
    return result


def _fit(matches: list[tuple[str, str, list[tuple[float, float]]]]) -> tuple[float, float]:
    xg = np.asarray([xg for _kickoff, _match_id, rows in matches for xg, _goal in rows])
    goals = np.asarray([goal for _kickoff, _match_id, rows in matches for _xg, goal in rows])
    fit = _logistic_fit(xg, goals, clip=1e-6)
    if fit is None:
        raise RuntimeError("development logistic recalibration did not converge")
    return cast(tuple[float, float], fit)


def _score(
    parameters: tuple[float, float], rows: list[tuple[float, float]]
) -> tuple[int, float, float, float, float]:
    xg = np.asarray([row[0] for row in rows])
    goals = np.asarray([row[1] for row in rows])
    raw = np.clip(xg, 1e-6, 1 - 1e-6)
    predictor = np.log(raw / (1 - raw))
    transformed = 1 / (1 + np.exp(-np.clip(parameters[0] + parameters[1] * predictor, -40, 40)))
    raw_log = float(np.sum(-(goals * np.log(raw) + (1 - goals) * np.log(1 - raw))))
    transformed_log = float(
        np.sum(-(goals * np.log(transformed) + (1 - goals) * np.log(1 - transformed)))
    )
    return (
        len(rows),
        raw_log,
        transformed_log,
        float(np.sum((raw - goals) ** 2)),
        float(np.sum((transformed - goals) ** 2)),
    )


def _pooled_deltas(rows: list[tuple[int, float, float, float, float]]) -> tuple[float, float]:
    shots = sum(row[0] for row in rows)
    return (
        sum(row[2] - row[1] for row in rows) / shots,
        sum(row[4] - row[3] for row in rows) / shots,
    )


def _bootstrap_intervals(
    rows: list[tuple[int, float, float, float, float]],
) -> dict[str, list[float]]:
    generator = np.random.default_rng(20260924)
    samples: list[tuple[float, float]] = []
    for _replicate in range(2000):
        indices = generator.integers(0, len(rows), len(rows))
        sampled = [rows[index] for index in indices]
        samples.append(_pooled_deltas(sampled))
    values = np.asarray(samples)
    return {
        "log_loss": [float(value) for value in np.quantile(values[:, 0], (0.025, 0.975))],
        "brier_score": [float(value) for value in np.quantile(values[:, 1], (0.025, 0.975))],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path(".local/pitchapi-snapshot-v1/primary"),
    )
    args = parser.parse_args()
    print(canonical_json_bytes(analyze(args.snapshot_root)).decode("utf-8"))


if __name__ == "__main__":
    main()
