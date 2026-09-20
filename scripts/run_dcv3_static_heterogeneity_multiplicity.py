#!/usr/bin/env python3
"""Confirm static residual heterogeneity with a frozen joint block bootstrap."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean

_INPUT_SHA256 = "120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e"
_TARGET_COUNT = 280
_BATCH_COUNT = 243
_BLOCK_LENGTH = 10
_REPLICATES = 2_000
_SEED = 20260909
_TEAM_MINIMUM = 12
_ALPHA = 0.05


class MultiplicityDiagnosticError(RuntimeError):
    """The frozen multiplicity protocol could not be reproduced."""


@dataclass(frozen=True, slots=True)
class ForecastResidual:
    kickoff_at: str
    home_team_id: str
    away_team_id: str
    home_residual: float
    away_residual: float


def main() -> int:
    arguments = _arguments()
    input_path = arguments.input.resolve()
    output_path = arguments.output.resolve()
    payload = _canonical_json_bytes(_run(input_path)) + b"\n"
    if output_path.exists() and output_path.read_bytes() != payload:
        raise MultiplicityDiagnosticError("output already exists with different bytes")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        output_path.write_bytes(payload)
    print(json.dumps({"output": str(output_path), "sha256": _sha256(payload)}, sort_keys=True))
    return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _run(input_path: Path) -> dict[str, object]:
    source = _load_input(input_path)
    records = _records(source)
    batches = _batches(records)
    observed, appearances, keys = _observed_statistics(records)
    bootstrap = _bootstrap_statistics(batches, keys)
    standard_errors = _standard_errors(bootstrap)
    split = len(keys) // 2
    primary = _simultaneous_inference(observed, standard_errors, bootstrap)
    attack = _simultaneous_inference(
        observed[:split], standard_errors[:split], [row[:split] for row in bootstrap]
    )
    defence = _simultaneous_inference(
        observed[split:], standard_errors[split:], [row[split:] for row in bootstrap]
    )
    global_result = _global_inference(observed, standard_errors, bootstrap)
    rows = _rows(keys, observed, standard_errors, appearances, primary, attack, defence)
    core_result = {
        "global": global_result,
        "primary_40_series": primary,
        "attack_family": attack,
        "defence_family": defence,
        "series": rows,
        "conclusion": _classify(global_result, primary),
    }
    entry_gate = _mapping(source.get("entry_gate"), "entry_gate")
    target_plan = _mapping(source.get("target_plan"), "target_plan")
    reproducibility = _mapping(source.get("reproducibility"), "reproducibility")
    return {
        "contract": "FrozenDCv3StaticTeamMultiplicityConfirmationV1",
        "input": {
            "diagnostic_artifact_sha256": _INPUT_SHA256,
            "dataset_version_id": _string(entry_gate, "dataset_version_id"),
            "source_snapshot_id": _string(entry_gate, "source_snapshot_id"),
            "diagnostic_target_count": len(records),
            "diagnostic_target_sha256": _string(target_plan, "diagnostic_target_sha256"),
        },
        "protocol": {
            "method": "circular-chronological-moving-block-bootstrap-v1",
            "sampling_unit": "reconstructed-retained-kickoff-batches",
            "batch_reconstruction": "identical retained kickoff_at UTC string",
            "kickoff_batch_count": len(batches),
            "block_length_batches": _BLOCK_LENGTH,
            "replicates": _REPLICATES,
            "seed": _SEED,
            "team_minimum_appearances": _TEAM_MINIMUM,
            "primary_family": "all-eligible-attack-and-defence-series",
            "primary_statistic": "max-standardized-bootstrap-error-v1",
            "global_statistic": "sum-squared-standardized-team-mean-residuals-v1",
            "quantile_rule": "empirical-order-statistic-floor-index-v1",
        },
        "eligibility": {
            "attack_team_ids": [team_id for role, team_id in keys if role == "attack"],
            "defence_team_ids": [team_id for role, team_id in keys if role == "defence"],
            "eligible_series_sha256": _sha256(
                _canonical_json_bytes(
                    {
                        "attack": [team_id for role, team_id in keys if role == "attack"],
                        "defence": [team_id for role, team_id in keys if role == "defence"],
                    }
                )
            ),
        },
        "results": core_result,
        "joint_result_sha256": _sha256(_canonical_json_bytes(core_result)),
        "reproducibility": {
            "code_git_sha": _git_sha(),
            "script_sha256": _sha256(Path(__file__).read_bytes()),
            "python_version": sys.version.split()[0],
            "input_diagnostic_script_sha256": _string(
                reproducibility, "diagnostic_script_sha256"
            ),
            "dependency_lock_sha256": _string(reproducibility, "dependency_lock_sha256"),
        },
    }


def _load_input(input_path: Path) -> Mapping[str, object]:
    raw = input_path.read_bytes()
    if _sha256(raw) != _INPUT_SHA256:
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_SHA256_MISMATCH")
    try:
        source = _mapping(json.loads(raw), "input diagnostic")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise MultiplicityDiagnosticError("input diagnostic is not valid JSON") from error
    if source.get("contract") != "FrozenDCv3IndependentLaLigaDiagnosticV1":
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_CONTRACT_MISMATCH")
    return source


def _records(source: Mapping[str, object]) -> tuple[ForecastResidual, ...]:
    raw_forecasts = source.get("forecasts")
    if not isinstance(raw_forecasts, list) or len(raw_forecasts) != _TARGET_COUNT:
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_TARGET_COUNT_MISMATCH")
    records: list[ForecastResidual] = []
    for raw in raw_forecasts:
        row = _mapping(raw, "forecast")
        records.append(
            ForecastResidual(
                kickoff_at=_string(row, "kickoff_at"),
                home_team_id=_string(row, "home_team_id"),
                away_team_id=_string(row, "away_team_id"),
                home_residual=_integer(row, "observed_home_goals")
                - _finite_float(row, "lambda_home"),
                away_residual=_integer(row, "observed_away_goals")
                - _finite_float(row, "lambda_away"),
            )
        )
    if len({(item.kickoff_at, item.home_team_id, item.away_team_id) for item in records}) != len(
        records
    ):
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_DUPLICATE_FORECAST")
    return tuple(records)


def _batches(records: Sequence[ForecastResidual]) -> tuple[tuple[ForecastResidual, ...], ...]:
    grouped: dict[str, list[ForecastResidual]] = defaultdict(list)
    for record in records:
        grouped[record.kickoff_at].append(record)
    batches = tuple(tuple(grouped[kickoff]) for kickoff in sorted(grouped))
    if len(batches) != _BATCH_COUNT:
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_KICKOFF_BATCH_MISMATCH")
    return batches


def _observed_statistics(
    records: Sequence[ForecastResidual],
) -> tuple[tuple[float, ...], tuple[int, ...], tuple[tuple[str, str], ...]]:
    values = _series_values(records)
    attack_ids = tuple(
        sorted(
            team_id
            for role, team_id in values
            if role == "attack" and len(values[(role, team_id)]) >= _TEAM_MINIMUM
        )
    )
    defence_ids = tuple(
        sorted(
            team_id
            for role, team_id in values
            if role == "defence" and len(values[(role, team_id)]) >= _TEAM_MINIMUM
        )
    )
    if len(attack_ids) != 20 or len(defence_ids) != 20:
        raise MultiplicityDiagnosticError("INPUT_DIAGNOSTIC_TEAM_ELIGIBILITY_MISMATCH")
    keys = tuple(("attack", team_id) for team_id in attack_ids) + tuple(
        ("defence", team_id) for team_id in defence_ids
    )
    return (
        tuple(fmean(values[key]) for key in keys),
        tuple(len(values[key]) for key in keys),
        keys,
    )


def _bootstrap_statistics(
    batches: Sequence[Sequence[ForecastResidual]], keys: Sequence[tuple[str, str]]
) -> list[tuple[float, ...]]:
    random_source = random.Random(_SEED)
    values: list[tuple[float, ...]] = []
    for _ in range(_REPLICATES):
        sampled_batches: list[Sequence[ForecastResidual]] = []
        while len(sampled_batches) < len(batches):
            start = random_source.randrange(len(batches))
            sampled_batches.extend(
                batches[(start + offset) % len(batches)] for offset in range(_BLOCK_LENGTH)
            )
        series = _series_values(
            tuple(record for batch in sampled_batches[: len(batches)] for record in batch)
        )
        try:
            values.append(tuple(fmean(series[key]) for key in keys))
        except KeyError as error:
            raise MultiplicityDiagnosticError("BOOTSTRAP_ELIGIBLE_SERIES_MISSING") from error
    return values


def _series_values(
    records: Sequence[ForecastResidual],
) -> dict[tuple[str, str], list[float]]:
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in records:
        values[("attack", record.home_team_id)].append(record.home_residual)
        values[("attack", record.away_team_id)].append(record.away_residual)
        values[("defence", record.home_team_id)].append(record.away_residual)
        values[("defence", record.away_team_id)].append(record.home_residual)
    return values


def _standard_errors(bootstrap: Sequence[Sequence[float]]) -> tuple[float, ...]:
    if not bootstrap:
        raise MultiplicityDiagnosticError("BOOTSTRAP_EMPTY")
    errors: list[float] = []
    for index in range(len(bootstrap[0])):
        values = [row[index] for row in bootstrap]
        variance = sum((value - fmean(values)) ** 2 for value in values) / (len(values) - 1)
        error = math.sqrt(variance)
        if not math.isfinite(error) or error <= 0.0:
            raise MultiplicityDiagnosticError("BOOTSTRAP_STANDARD_ERROR_INVALID")
        errors.append(error)
    return tuple(errors)


def _simultaneous_inference(
    observed: Sequence[float],
    standard_errors: Sequence[float],
    bootstrap: Sequence[Sequence[float]],
) -> dict[str, object]:
    maxima = [
        max(
            abs((replicate[index] - observed[index]) / standard_errors[index])
            for index in range(len(observed))
        )
        for replicate in bootstrap
    ]
    critical = _quantile(maxima, 1.0 - _ALPHA)
    intervals = [
        [observed[index] - critical * standard_errors[index], observed[index] + critical * standard_errors[index]]
        for index in range(len(observed))
    ]
    return {
        "critical_value": critical,
        "simultaneous_intervals": intervals,
        "simultaneous_exclusions": sum(
            interval[0] > 0.0 or interval[1] < 0.0 for interval in intervals
        ),
    }


def _global_inference(
    observed: Sequence[float],
    standard_errors: Sequence[float],
    bootstrap: Sequence[Sequence[float]],
) -> dict[str, object]:
    statistic = sum(
        (observed[index] / standard_errors[index]) ** 2 for index in range(len(observed))
    )
    reference = [
        sum(
            ((replicate[index] - observed[index]) / standard_errors[index]) ** 2
            for index in range(len(observed))
        )
        for replicate in bootstrap
    ]
    probability = sum(value >= statistic for value in reference) / len(reference)
    return {
        "statistic": statistic,
        "reference_interval": [_quantile(reference, 0.025), _quantile(reference, 0.975)],
        "reference_probability": probability,
        "supported": probability <= _ALPHA,
    }


def _classify(global_result: Mapping[str, object], primary: Mapping[str, object]) -> str:
    statistic = _finite_float(global_result, "statistic")
    reference = _float_pair(global_result.get("reference_interval"), "reference_interval")
    exclusions = _integer(primary, "simultaneous_exclusions")
    if bool(global_result.get("supported")) and (exclusions > 1 or statistic > reference[1]):
        return "A. STATIC_HETEROGENEITY_CONFIRMED_AFTER_MULTIPLICITY"
    return "B. STATIC_HETEROGENEITY_NOT_CONFIRMED_AFTER_MULTIPLICITY"


def _rows(
    keys: Sequence[tuple[str, str]],
    observed: Sequence[float],
    standard_errors: Sequence[float],
    appearances: Sequence[int],
    primary: Mapping[str, object],
    attack: Mapping[str, object],
    defence: Mapping[str, object],
) -> list[dict[str, object]]:
    primary_intervals = _intervals(primary, len(keys))
    attack_intervals = _intervals(attack, len(keys) // 2)
    defence_intervals = _intervals(defence, len(keys) // 2)
    split = len(keys) // 2
    rows: list[dict[str, object]] = []
    for index, (role, team_id) in enumerate(keys):
        secondary = attack_intervals[index] if role == "attack" else defence_intervals[index - split]
        interval = primary_intervals[index]
        rows.append(
            {
                "team_id": team_id,
                "dimension": role.upper(),
                "mean_residual": observed[index],
                "bootstrap_standard_error": standard_errors[index],
                "appearances": appearances[index],
                "primary_simultaneous_interval": interval,
                "secondary_family_simultaneous_interval": secondary,
                "primary_interval_excludes_zero": interval[0] > 0.0 or interval[1] < 0.0,
            }
        )
    return rows


def _intervals(result: Mapping[str, object], count: int) -> list[list[float]]:
    raw = result.get("simultaneous_intervals")
    if not isinstance(raw, list) or len(raw) != count:
        raise MultiplicityDiagnosticError("BOOTSTRAP_INTERVAL_SHAPE_MISMATCH")
    return [_float_pair(value, "simultaneous_interval") for value in raw]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise MultiplicityDiagnosticError("BOOTSTRAP_QUANTILE_INVALID")
    return sorted(values)[int(probability * (len(values) - 1))]


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise MultiplicityDiagnosticError(f"{name} must be an object")
    return value


def _string(value: Mapping[str, object], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise MultiplicityDiagnosticError(f"{name} must be a non-empty string")
    return item


def _integer(value: Mapping[str, object], name: str) -> int:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int):
        raise MultiplicityDiagnosticError(f"{name} must be an integer")
    return item


def _finite_float(value: Mapping[str, object], name: str) -> float:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
        raise MultiplicityDiagnosticError(f"{name} must be a finite number")
    return float(item)


def _float_pair(value: object, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise MultiplicityDiagnosticError(f"{name} must be a pair")
    return [
        _finite_float({"value": value[0]}, "value"),
        _finite_float({"value": value[1]}, "value"),
    ]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MultiplicityDiagnosticError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2)
