#!/usr/bin/env python3
"""Diagnose frozen DCv3 low-score structure without fitting any model."""

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
from statistics import fmean, median, stdev

_INPUT_SHA256 = "120ca2e0e135942d7d0b0316d8035562e9d57426225fe3d49dedf4ada445ee5e"
_TARGET_SHA256 = "b758e795d41f0cc84145626d20d791eccbcfbd9fb94d2767039bdcdf50f3eb18"
_TARGET_COUNT = 280
_BATCH_COUNT = 243
_BLOCK_LENGTH = 10
_REPLICATES = 2_000
_SEED = 20260909
_ALPHA = 0.05
_CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))


class LowScoreDiagnosticError(RuntimeError):
    """The bound artifact or frozen low-score protocol is invalid."""


@dataclass(frozen=True, slots=True)
class Forecast:
    match_id: str
    kickoff_at: str
    home_team_id: str
    away_team_id: str
    lambda_home: float
    lambda_away: float
    rho: float
    home_goals: int
    away_goals: int

    def observed(self, cell: tuple[int, int]) -> float:
        return float((self.home_goals, self.away_goals) == cell)

    def independent(self, cell: tuple[int, int]) -> float:
        return _poisson(cell[0], self.lambda_home) * _poisson(cell[1], self.lambda_away)

    def dc(self, cell: tuple[int, int]) -> float:
        return self.independent(cell) * _tau(
            cell[0], cell[1], self.lambda_home, self.lambda_away, self.rho
        )

    def rho_derivative(self, cell: tuple[int, int]) -> float:
        base = self.independent(cell)
        if cell == (0, 0):
            return -base * self.lambda_home * self.lambda_away
        if cell == (0, 1):
            return base * self.lambda_home
        if cell == (1, 0):
            return base * self.lambda_away
        if cell == (1, 1):
            return -base
        raise LowScoreDiagnosticError("unsupported low-score cell")


def main() -> int:
    arguments = _arguments()
    input_path = arguments.input.resolve()
    output_path = arguments.output.resolve()
    payload = _canonical_json_bytes(_run(input_path)) + b"\n"
    if output_path.exists() and output_path.read_bytes() != payload:
        raise LowScoreDiagnosticError("output already exists with different bytes")
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
    source, records = _load_input(input_path)
    batches = _batches(records)
    samples = _bootstrap_samples(batches)
    frozen_cells = _cell_rows(records, "dc")
    independent_cells = _cell_rows(records, "independent")
    simultaneous = _simultaneous_intervals(records, samples)
    for row, interval in zip(frozen_cells, simultaneous["intervals"], strict=True):
        row["simultaneous_interval"] = interval
        row["simultaneous_interval_excludes_zero"] = interval[0] > 0.0 or interval[1] < 0.0
    for row, interval in zip(
        independent_cells, _marginal_intervals(samples, "independent"), strict=True
    ):
        row["marginal_interval"] = interval
    rho = _rho_distribution(records, batches)
    counterfactual = _counterfactual(independent_cells, frozen_cells)
    scalar = _scalar_compatibility(frozen_cells, simultaneous, records)
    chronological = _chronological(records, batches)
    result = {
        "rho_distribution": rho,
        "frozen_dc_cells": frozen_cells,
        "independent_poisson_cells": independent_cells,
        "simultaneous_inference": simultaneous,
        "counterfactual": counterfactual,
        "zero_probability_strata": _zero_probability_strata(records, samples),
        "chronological_0_0": chronological,
        "team_concentration": _team_concentration(records),
        "scalar_rho": scalar,
    }
    conclusion, recommendation = _classify(result)
    result["conclusion"] = conclusion
    result["recommended_next_action"] = recommendation
    entry_gate = _mapping(source.get("entry_gate"), "entry_gate")
    plan = _mapping(source.get("target_plan"), "target_plan")
    reproducibility = _mapping(source.get("reproducibility"), "reproducibility")
    return {
        "contract": "FrozenDCv3LowScoreStructureDiagnosticV1",
        "input": {
            "diagnostic_artifact_sha256": _INPUT_SHA256,
            "dataset_version_id": _string(entry_gate, "dataset_version_id"),
            "source_snapshot_id": _string(entry_gate, "source_snapshot_id"),
            "diagnostic_target_count": len(records),
            "diagnostic_target_sha256": _string(plan, "diagnostic_target_sha256"),
            "frozen_model": "sprint2-dixon-coles-v3",
        },
        "protocol": {
            "bootstrap_method": "circular-chronological-moving-block-bootstrap-v1",
            "sampling_unit": "reconstructed-retained-kickoff-batches",
            "kickoff_batch_count": len(batches),
            "block_length_batches": _BLOCK_LENGTH,
            "replicates": _REPLICATES,
            "seed": _SEED,
            "primary_cell_family": [_cell_name(cell) for cell in _CELLS],
            "primary_interval": "simultaneous-95-max-standardized-centered-bootstrap-v1",
            "independent_poisson_interval": "marginal-percentile-95-bootstrap-v1",
            "zero_probability_buckets": "three-equal-count-frozen-dc-0-0-probability-buckets",
            "chronological_blocks": "four-equal-count-retained-kickoff-batch-blocks",
        },
        "results": result,
        "result_sha256": _sha256(_canonical_json_bytes(result)),
        "reproducibility": {
            "code_git_sha": _git_sha(),
            "script_sha256": _sha256(Path(__file__).read_bytes()),
            "dependency_lock_sha256": _string(reproducibility, "dependency_lock_sha256"),
            "input_diagnostic_script_sha256": _string(reproducibility, "diagnostic_script_sha256"),
            "python_version": sys.version.split()[0],
        },
    }


def _load_input(input_path: Path) -> tuple[Mapping[str, object], tuple[Forecast, ...]]:
    raw = input_path.read_bytes()
    if _sha256(raw) != _INPUT_SHA256:
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_SHA256_MISMATCH")
    try:
        source = _mapping(json.loads(raw), "input diagnostic")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise LowScoreDiagnosticError("input diagnostic is not valid JSON") from error
    if source.get("contract") != "FrozenDCv3IndependentLaLigaDiagnosticV1":
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_CONTRACT_MISMATCH")
    plan = _mapping(source.get("target_plan"), "target_plan")
    if _string(plan, "diagnostic_target_sha256") != _TARGET_SHA256:
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_TARGET_SHA256_MISMATCH")
    raw_forecasts = source.get("forecasts")
    if not isinstance(raw_forecasts, list) or len(raw_forecasts) != _TARGET_COUNT:
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_TARGET_COUNT_MISMATCH")
    records = tuple(_forecast(_mapping(row, "forecast")) for row in raw_forecasts)
    if len({record.match_id for record in records}) != _TARGET_COUNT:
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_DUPLICATE_FORECAST")
    if any(record.lambda_home <= 0.0 or record.lambda_away <= 0.0 for record in records):
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_INVALID_MEAN")
    for raw_forecast, record in zip(raw_forecasts, records, strict=True):
        _verify_frozen_low_score_state(_mapping(raw_forecast, "forecast"), record)
    return source, records


def _forecast(row: Mapping[str, object]) -> Forecast:
    return Forecast(
        match_id=_string(row, "canonical_match_id"),
        kickoff_at=_string(row, "kickoff_at"),
        home_team_id=_string(row, "home_team_id"),
        away_team_id=_string(row, "away_team_id"),
        lambda_home=_finite_float(row, "lambda_home"),
        lambda_away=_finite_float(row, "lambda_away"),
        rho=_finite_float(row, "rho"),
        home_goals=_integer(row, "observed_home_goals"),
        away_goals=_integer(row, "observed_away_goals"),
    )


def _verify_frozen_low_score_state(row: Mapping[str, object], record: Forecast) -> None:
    state = _mapping(row.get("joint_probability_state"), "joint_probability_state")
    labels = state.get("labels")
    probabilities = state.get("probabilities")
    if labels != ["0", "1", "2", "3", "4", "5+"] or not isinstance(probabilities, list):
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_JOINT_STATE_MISMATCH")
    for home, away in _CELLS:
        try:
            stored = probabilities[home][away]
        except (IndexError, TypeError) as error:
            raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_JOINT_STATE_MISMATCH") from error
        if not isinstance(stored, (int, float)) or not math.isclose(
            float(stored), record.dc((home, away)), abs_tol=1e-12
        ):
            raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_FROZEN_DC_CELL_MISMATCH")


def _batches(records: Sequence[Forecast]) -> tuple[tuple[Forecast, ...], ...]:
    grouped: dict[str, list[Forecast]] = defaultdict(list)
    for record in records:
        grouped[record.kickoff_at].append(record)
    batches = tuple(tuple(grouped[kickoff]) for kickoff in sorted(grouped))
    if len(batches) != _BATCH_COUNT:
        raise LowScoreDiagnosticError("INPUT_DIAGNOSTIC_KICKOFF_BATCH_MISMATCH")
    return batches


def _bootstrap_samples(batches: Sequence[Sequence[Forecast]]) -> list[tuple[Forecast, ...]]:
    random_source = random.Random(_SEED)
    samples: list[tuple[Forecast, ...]] = []
    for _ in range(_REPLICATES):
        selected: list[Sequence[Forecast]] = []
        while len(selected) < len(batches):
            start = random_source.randrange(len(batches))
            selected.extend(
                batches[(start + offset) % len(batches)] for offset in range(_BLOCK_LENGTH)
            )
        samples.append(tuple(record for batch in selected[: len(batches)] for record in batch))
    return samples


def _cell_rows(records: Sequence[Forecast], model: str) -> list[dict[str, object]]:
    probability = _probability(model)
    rows: list[dict[str, object]] = []
    for cell in _CELLS:
        predicted = fmean(probability(record, cell) for record in records)
        observed = fmean(record.observed(cell) for record in records)
        rows.append(
            {
                "cell": _cell_name(cell),
                "predicted_expected_count": predicted * len(records),
                "predicted_frequency": predicted,
                "observed_count": sum(record.observed(cell) for record in records),
                "observed_frequency": observed,
                "error": observed - predicted,
            }
        )
    return rows


def _simultaneous_intervals(
    records: Sequence[Forecast], samples: Sequence[Sequence[Forecast]]
) -> dict[str, object]:
    observed = _error_vector(records, "dc")
    bootstrap = [_error_vector(sample, "dc") for sample in samples]
    errors = tuple(
        _sample_standard_deviation([row[index] for row in bootstrap]) for index in range(4)
    )
    maxima = [
        max(abs((replicate[index] - observed[index]) / errors[index]) for index in range(4))
        for replicate in bootstrap
    ]
    critical = _quantile(maxima, 1.0 - _ALPHA)
    intervals = [
        [observed[index] - critical * errors[index], observed[index] + critical * errors[index]]
        for index in range(4)
    ]
    return {
        "critical_value": critical,
        "bootstrap_standard_errors": list(errors),
        "intervals": intervals,
        "simultaneous_exclusions": sum(
            interval[0] > 0.0 or interval[1] < 0.0 for interval in intervals
        ),
    }


def _marginal_intervals(samples: Sequence[Sequence[Forecast]], model: str) -> list[list[float]]:
    vectors = [_error_vector(sample, model) for sample in samples]
    return [_interval([vector[index] for vector in vectors]) for index in range(4)]


def _counterfactual(
    independent: Sequence[Mapping[str, object]], frozen: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for raw, dc in zip(independent, frozen, strict=True):
        raw_error = _finite_float(raw, "error")
        dc_error = _finite_float(dc, "error")
        effect = _effect(abs(raw_error), abs(dc_error))
        rows.append(
            {
                "cell": _string(raw, "cell"),
                "independent_error": raw_error,
                "frozen_dc_error": dc_error,
                "rho_correction_effect": effect,
            }
        )
    zero = rows[0]
    raw_error = _finite_float(zero, "independent_error")
    dc_error = _finite_float(zero, "frozen_dc_error")
    return {
        "cells": rows,
        "zero_error_origin": _error_origin(raw_error, dc_error),
        "zero_rho_correction_effect": _string(zero, "rho_correction_effect"),
    }


def _rho_distribution(
    records: Sequence[Forecast], batches: Sequence[Sequence[Forecast]]
) -> dict[str, object]:
    values = sorted(record.rho for record in records)
    near = 0.01
    chronological = []
    for index, group in enumerate(_equal_count_groups(batches, 4), start=1):
        flattened = tuple(record for batch in group for record in batch)
        chronological.append(
            {
                "block": index,
                "sample_count": len(flattened),
                "kickoff_at_start": flattened[0].kickoff_at,
                "kickoff_at_end": flattened[-1].kickoff_at,
                "mean_rho": fmean(record.rho for record in flattened),
                "median_rho": median(record.rho for record in flattened),
            }
        )
    means = [row["mean_rho"] for row in chronological]
    if not all(isinstance(value, float) for value in means):
        raise LowScoreDiagnosticError("RHO_CHRONOLOGICAL_SUMMARY_INVALID")
    return {
        "count": len(values),
        "mean": fmean(values),
        "median": median(values),
        "sample_standard_deviation": stdev(values),
        "minimum": min(values),
        "maximum": max(values),
        "quantiles": {
            "p05": _quantile(values, 0.05),
            "p25": _quantile(values, 0.25),
            "p75": _quantile(values, 0.75),
            "p95": _quantile(values, 0.95),
        },
        "fraction_at_lower_bound": sum(
            math.isclose(value, -0.25, abs_tol=1e-12) for value in values
        )
        / len(values),
        "fraction_at_upper_bound": sum(math.isclose(value, 0.25, abs_tol=1e-12) for value in values)
        / len(values),
        "fraction_near_lower_bound_within_0_01": sum(value <= -0.25 + near for value in values)
        / len(values),
        "fraction_near_upper_bound_within_0_01": sum(value >= 0.25 - near for value in values)
        / len(values),
        "fraction_near_zero_abs_at_most_0_01": sum(abs(value) <= near for value in values)
        / len(values),
        "chronological_blocks": chronological,
        "chronological_block_mean_range": max(means) - min(means),
    }


def _zero_probability_strata(
    records: Sequence[Forecast], samples: Sequence[Sequence[Forecast]]
) -> list[dict[str, object]]:
    buckets = _equal_count_groups(
        sorted(records, key=lambda record: (record.dc((0, 0)), record.match_id)), 3
    )
    memberships = [{record.match_id for record in bucket} for bucket in buckets]
    rows: list[dict[str, object]] = []
    for index, bucket in enumerate(buckets):
        errors = [record.observed((0, 0)) - record.dc((0, 0)) for record in bucket]
        bootstrap = []
        for sample in samples:
            selected = [record for record in sample if record.match_id in memberships[index]]
            if not selected:
                raise LowScoreDiagnosticError("BOOTSTRAP_EMPTY_ZERO_PROBABILITY_STRATUM")
            bootstrap.append(
                fmean(record.observed((0, 0)) - record.dc((0, 0)) for record in selected)
            )
        rows.append(
            {
                "bucket": index + 1,
                "sample_count": len(bucket),
                "mean_lambda_home": fmean(record.lambda_home for record in bucket),
                "mean_lambda_away": fmean(record.lambda_away for record in bucket),
                "predicted_0_0_frequency": fmean(record.dc((0, 0)) for record in bucket),
                "observed_0_0_frequency": fmean(record.observed((0, 0)) for record in bucket),
                "error": fmean(errors),
                "marginal_interval": _interval(bootstrap),
            }
        )
    return rows


def _chronological(
    records: Sequence[Forecast], batches: Sequence[Sequence[Forecast]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index, group in enumerate(_equal_count_groups(batches, 4), start=1):
        flattened = tuple(record for batch in group for record in batch)
        rows.append(
            {
                "block": index,
                "sample_count": len(flattened),
                "kickoff_at_start": flattened[0].kickoff_at,
                "kickoff_at_end": flattened[-1].kickoff_at,
                "predicted_0_0_frequency": fmean(record.dc((0, 0)) for record in flattened),
                "observed_0_0_frequency": fmean(record.observed((0, 0)) for record in flattened),
                "error": fmean(record.observed((0, 0)) - record.dc((0, 0)) for record in flattened),
            }
        )
    return rows


def _team_concentration(records: Sequence[Forecast]) -> dict[str, object]:
    contributions: dict[str, float] = defaultdict(float)
    for record in records:
        residual = (record.observed((0, 0)) - record.dc((0, 0))) / 2.0
        contributions[record.home_team_id] += residual
        contributions[record.away_team_id] += residual
    ranked = sorted(contributions.items(), key=lambda item: (-abs(item[1]), item[0]))
    denominator = sum(abs(value) for value in contributions.values())
    if denominator <= 0.0:
        raise LowScoreDiagnosticError("TEAM_CONCENTRATION_ZERO_DENOMINATOR")
    shares = [abs(value) / denominator for _team, value in ranked]
    return {
        "method": "absolute-net-team-contribution-share-v1",
        "top_team": {"team_id": ranked[0][0], "residual": ranked[0][1], "share": shares[0]},
        "top_three": [
            {"team_id": team_id, "residual": value, "share": shares[index]}
            for index, (team_id, value) in enumerate(ranked[:3])
        ],
        "top_three_share": sum(shares[:3]),
        "effective_team_count": 1.0 / sum(share**2 for share in shares),
        "total_signed_residual": sum(contributions.values()),
    }


def _scalar_compatibility(
    frozen: Sequence[Mapping[str, object]],
    simultaneous: Mapping[str, object],
    records: Sequence[Forecast],
) -> dict[str, object]:
    intervals = simultaneous.get("intervals")
    if not isinstance(intervals, list) or len(intervals) != len(_CELLS):
        raise LowScoreDiagnosticError("SIMULTANEOUS_INTERVAL_SHAPE_MISMATCH")
    errors = [_finite_float(row, "error") for row in frozen]
    derivatives = [fmean(record.rho_derivative(cell) for record in records) for cell in _CELLS]
    robust = [_interval_excludes_zero(value) for value in intervals]
    compatible_positive = all(
        error * derivative > 0.0 for error, derivative in zip(errors, derivatives, strict=True)
    )
    compatible_negative = all(
        error * derivative < 0.0 for error, derivative in zip(errors, derivatives, strict=True)
    )
    if not all(robust):
        classification = "INCONCLUSIVE"
    elif compatible_positive or compatible_negative:
        classification = "SCALAR_RHO_DIRECTION_COMPATIBLE"
    else:
        classification = "SCALAR_RHO_DIRECTION_INCOMPATIBLE"
    return {
        "cell_error_vector": {row["cell"]: errors[index] for index, row in enumerate(frozen)},
        "mean_probability_derivative_by_rho": {
            _cell_name(cell): derivatives[index] for index, cell in enumerate(_CELLS)
        },
        "simultaneously_supported_cells": [
            _cell_name(cell) for index, cell in enumerate(_CELLS) if robust[index]
        ],
        "positive_rho_direction_compatible": compatible_positive,
        "negative_rho_direction_compatible": compatible_negative,
        "classification": classification,
    }


def _classify(result: Mapping[str, object]) -> tuple[str, str]:
    frozen = _rows(result, "frozen_dc_cells")
    counterfactual = _mapping(result.get("counterfactual"), "counterfactual")
    scalar = _mapping(result.get("scalar_rho"), "scalar_rho")
    zero_interval = _float_pair(
        _mapping(frozen[0], "cell").get("simultaneous_interval"), "interval"
    )
    zero_supported = zero_interval[0] > 0.0 or zero_interval[1] < 0.0
    effect = _string(counterfactual, "zero_rho_correction_effect")
    scalar_classification = _string(scalar, "classification")
    robust_cells = _strings(scalar.get("simultaneously_supported_cells"), "supported cells")
    if not zero_supported:
        return "D. LOW_SCORE_SIGNAL_NOT_ROBUST", "NO_CHALLENGER_YET"
    if effect == "WORSENS" and scalar_classification == "SCALAR_RHO_DIRECTION_COMPATIBLE":
        return (
            "A. FROZEN_SCALAR_RHO_MISSPECIFICATION_SUPPORTED",
            "AUTHORIZE_SCALAR_RHO_CONTRACT_RESEARCH",
        )
    if (
        len(robust_cells) == len(_CELLS)
        and scalar_classification == "SCALAR_RHO_DIRECTION_INCOMPATIBLE"
    ):
        return (
            "C. BROADER_LOW_SCORE_DEPENDENCE_MISSPECIFICATION_SUPPORTED",
            "AUTHORIZE_LOW_SCORE_DEPENDENCE_CONTRACT_RESEARCH",
        )
    if effect != "WORSENS" and _string(counterfactual, "zero_error_origin") == "BASE_MEAN_DRIVEN":
        return (
            "B. LOW_SCORE_ERROR_PRIMARILY_MEAN_DRIVEN",
            "AUTHORIZE_MEAN_MODEL_DIAGNOSTIC_RESEARCH",
        )
    return (
        "E. LOW_SCORE_MECHANISM_INCONCLUSIVE",
        "AUTHORIZE_ADDITIONAL_INDEPENDENT_LOW_SCORE_DIAGNOSTIC",
    )


def _error_vector(records: Sequence[Forecast], model: str) -> tuple[float, ...]:
    probability = _probability(model)
    return tuple(
        fmean(record.observed(cell) - probability(record, cell) for record in records)
        for cell in _CELLS
    )


def _probability(model: str):
    if model == "dc":
        return lambda record, cell: record.dc(cell)
    if model == "independent":
        return lambda record, cell: record.independent(cell)
    raise LowScoreDiagnosticError("unsupported probability model")


def _effect(raw: float, corrected: float) -> str:
    if math.isclose(raw, corrected, abs_tol=1e-15):
        return "NEGLIGIBLE"
    return "IMPROVES" if corrected < raw else "WORSENS"


def _error_origin(raw_error: float, corrected_error: float) -> str:
    if math.isclose(raw_error, 0.0, abs_tol=1e-15):
        return (
            "RHO_CORRECTION_DRIVEN"
            if not math.isclose(corrected_error, 0.0, abs_tol=1e-15)
            else "NEITHER_CLEARLY"
        )
    if math.isclose(corrected_error, raw_error, abs_tol=1e-15):
        return "BASE_MEAN_DRIVEN"
    return "BOTH"


def _tau(home: int, away: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if home == 0 and away == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home == 0 and away == 1:
        return 1.0 + lambda_home * rho
    if home == 1 and away == 0:
        return 1.0 + lambda_away * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def _poisson(goals: int, mean: float) -> float:
    return math.exp(goals * math.log(mean) - mean - math.lgamma(goals + 1.0))


def _equal_count_groups(values: Sequence[object], count: int) -> list[Sequence[object]]:
    return [
        values[index * len(values) // count : (index + 1) * len(values) // count]
        for index in range(count)
    ]


def _sample_standard_deviation(values: Sequence[float]) -> float:
    value = stdev(values)
    if not math.isfinite(value) or value <= 0.0:
        raise LowScoreDiagnosticError("BOOTSTRAP_STANDARD_ERROR_INVALID")
    return value


def _interval(values: Sequence[float]) -> list[float]:
    return [_quantile(values, 0.025), _quantile(values, 0.975)]


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values or not 0.0 <= probability <= 1.0:
        raise LowScoreDiagnosticError("BOOTSTRAP_QUANTILE_INVALID")
    return sorted(values)[int(probability * (len(values) - 1))]


def _cell_name(cell: tuple[int, int]) -> str:
    return f"{cell[0]}-{cell[1]}"


def _interval_excludes_zero(value: object) -> bool:
    interval = _float_pair(value, "interval")
    return interval[0] > 0.0 or interval[1] < 0.0


def _mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise LowScoreDiagnosticError(f"{name} must be an object")
    return value


def _rows(value: Mapping[str, object], name: str) -> list[Mapping[str, object]]:
    rows = value.get(name)
    if not isinstance(rows, list) or len(rows) != len(_CELLS):
        raise LowScoreDiagnosticError(f"{name} must contain four rows")
    return [_mapping(row, name) for row in rows]


def _strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LowScoreDiagnosticError(f"{name} must be a string list")
    return list(value)


def _string(value: Mapping[str, object], name: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or not item:
        raise LowScoreDiagnosticError(f"{name} must be a non-empty string")
    return item


def _integer(value: Mapping[str, object], name: str) -> int:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int) or item < 0:
        raise LowScoreDiagnosticError(f"{name} must be a non-negative integer")
    return item


def _finite_float(value: Mapping[str, object], name: str) -> float:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
        raise LowScoreDiagnosticError(f"{name} must be a finite number")
    return float(item)


def _float_pair(value: object, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 2:
        raise LowScoreDiagnosticError(f"{name} must be a pair")
    return [
        _finite_float({"value": value[0]}, "value"),
        _finite_float({"value": value[1]}, "value"),
    ]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LowScoreDiagnosticError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
