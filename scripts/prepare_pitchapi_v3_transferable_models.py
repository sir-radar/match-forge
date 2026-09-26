"""Fit and validate PitchAPI V3 models without opening evaluation outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3 import (
    CHALLENGER_ALGORITHM,
    FEATURE_ID,
    HISTORY_WINDOW,
    PROTOCOL_ID,
    REFERENCE_ALGORITHM,
    HistoryObservationV1,
    TransferableParametersV1,
    TransferableTrainingRowV1,
    build_training_rows,
    expected_goals,
    fit_transferable_parameters,
    parameter_payload,
)

SNAPSHOT_SHA256 = "435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea"
CORPUS_SHA256 = "42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4"
DEVELOPMENT_MANIFEST = "be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e"
EVALUATION_MANIFESTS = {
    "bundesliga_2022_23": (
        "893b888a36474c7cf55a207cb266d32a60351c0c87e9659a38a2cdc962784f74",
        216,
    ),
    "bundesliga_2023_24": (
        "0700ee9d976366db3a12b0c3bc4c9e3d6a953d95b7fbe1dac153773553ae9b87",
        216,
    ),
    "ligue1_2022_23": (
        "ded84fa1ce6f2695469f1e258bffd8c2b3ac79ee5edec5afa24be0e4d0b0939d",
        280,
    ),
}


def load_development(root: Path) -> tuple[HistoryObservationV1, ...]:
    season = _load_hashed(root, "manifests", DEVELOPMENT_MANIFEST)
    observations = tuple(
        _development_observation(root, item)
        for item in cast(list[dict[str, Any]], season["matches"])
    )
    if len(observations) != 306:
        raise RuntimeError(f"expected 306 development matches, got {len(observations)}")
    return observations


def structural_coverage(root: Path) -> dict[str, object]:
    domains: dict[str, object] = {}
    all_teams: set[str] = set()
    total_targets = 0
    for scope, (digest, expected) in EVALUATION_MANIFESTS.items():
        season = _load_hashed(root, "manifests", digest)
        target_ids = frozenset(cast(dict[str, Any], season["target_plan"])["target_ids"])
        rows = []
        for item in cast(list[dict[str, Any]], season["matches"]):
            manifest = _load_path(root / str(item["manifest_path"]))
            rows.append(manifest)
        rows.sort(key=lambda item: (str(item["kickoff_at"]), str(item["canonical_match_id"])))
        appearances: dict[str, int] = defaultdict(int)
        unforecastable: list[str] = []
        position = 0
        while position < len(rows):
            end = position + 1
            while end < len(rows) and rows[end]["kickoff_at"] == rows[position]["kickoff_at"]:
                end += 1
            batch = rows[position:end]
            for row in batch:
                match_id = str(row["canonical_match_id"])
                home = str(row["home_canonical_team_id"])
                away = str(row["away_canonical_team_id"])
                all_teams.update((home, away))
                if match_id in target_ids and (
                    appearances[home] < HISTORY_WINDOW or appearances[away] < HISTORY_WINDOW
                ):
                    unforecastable.append(match_id)
            for row in batch:
                appearances[str(row["home_canonical_team_id"])] += 1
                appearances[str(row["away_canonical_team_id"])] += 1
            position = end
        if len(target_ids) != expected:
            raise RuntimeError(f"unexpected structural target count for {scope}")
        domains[scope] = {
            "structural_targets": len(target_ids),
            "unforecastable_targets": len(unforecastable),
        }
        total_targets += len(target_ids)
    return {
        "domains": domains,
        "evaluation_team_count": len(all_teams),
        "structural_target_count": total_targets,
        "unforecastable_evaluation_targets": sum(
            cast(dict[str, int], value)["unforecastable_targets"] for value in domains.values()
        ),
    }


def prepare(root: Path, *, source_commit: str, dependency_lock_sha256: str) -> dict[str, object]:
    observations = load_development(root)
    rows = build_training_rows(observations, scope_key="bundesliga_2021_22")
    if len(rows) != 216:
        raise RuntimeError(f"expected 216 development targets, got {len(rows)}")
    approaches = _compare_approaches(rows, observations)
    reference = fit_transferable_parameters(rows, observations, include_xg=False)
    challenger = fit_transferable_parameters(rows, observations, include_xg=True)
    leave_team_out = _leave_team_out(rows, observations)
    coverage = structural_coverage(root)
    if coverage["structural_target_count"] != 712:
        raise RuntimeError("V3 structural corpus count is not 712")
    if coverage["unforecastable_evaluation_targets"] != 0:
        raise RuntimeError("V3 contains structurally unforecastable targets")
    common = {
        "contract": "PitchApiV3TransferableModelArtifactV1",
        "development_manifest_sha256": DEVELOPMENT_MANIFEST,
        "development_scope": "bundesliga_2021_22",
        "development_target_count": len(rows),
        "dependency_lock_sha256": dependency_lock_sha256,
        "evaluation_outcomes_loaded": False,
        "executor_source_commit": source_commit,
        "snapshot_sha256": SNAPSHOT_SHA256,
    }
    return {
        "artifacts": {
            "reference": {**common, **parameter_payload(reference, model_role="REFERENCE")},
            "challenger": {**common, **parameter_payload(challenger, model_role="CHALLENGER")},
        },
        "evidence": {
            "approach_comparison": approaches,
            "challenger_algorithm": CHALLENGER_ALGORITHM,
            "contract": "PitchApiV3TransferabilityDevelopmentEvidenceV1",
            "corpus_sha256": CORPUS_SHA256,
            "development_only": True,
            "evaluation_outcomes_loaded": False,
            "feature_id": FEATURE_ID,
            "leave_team_out": leave_team_out,
            "protocol_id": PROTOCOL_ID,
            "recommended_approach": "B_FULLY_TRANSFERABLE_FEATURE_BASED_MODEL",
            "reference_algorithm": REFERENCE_ALGORITHM,
            "structural_coverage": coverage,
        },
    }


def _compare_approaches(
    rows: tuple[TransferableTrainingRowV1, ...],
    observations: tuple[HistoryObservationV1, ...],
) -> dict[str, object]:
    goal_mean, npxg_mean = _population_means(observations)
    home_mean = sum(item.home_goals for item in observations) / len(observations)
    away_mean = sum(item.away_goals for item in observations) / len(observations)
    candidates = {
        "A_DEVELOPMENT_DERIVED_PRIOR": TransferableParametersV1(
            math.log(home_mean), math.log(away_mean), 0.5, 0.5, 0.0, goal_mean, npxg_mean
        ),
        "B_FULLY_TRANSFERABLE_FEATURE_BASED_MODEL": fit_transferable_parameters(
            rows, observations, include_xg=False
        ),
        "C_CHRONOLOGICAL_ONLINE_STATE": TransferableParametersV1(
            math.log(home_mean), math.log(away_mean), 1.0, 1.0, 0.0, goal_mean, npxg_mean
        ),
    }
    return {
        name: {
            **_score(parameters, rows),
            "parameters": parameters.to_dict(),
            "team_id_parameters": False,
        }
        for name, parameters in candidates.items()
    }


def _leave_team_out(
    rows: tuple[TransferableTrainingRowV1, ...],
    observations: tuple[HistoryObservationV1, ...],
) -> dict[str, object]:
    team_ids = sorted(
        {team for item in observations for team in (item.home_team_id, item.away_team_id)},
        key=str,
    )
    reference_pairs: list[tuple[TransferableParametersV1, TransferableTrainingRowV1]] = []
    challenger_pairs: list[tuple[TransferableParametersV1, TransferableTrainingRowV1]] = []
    fold_counts: dict[str, int] = {}
    for team_id in team_ids:
        fit_rows = tuple(
            row
            for row in rows
            if team_id not in (row.context.home_team_id, row.context.away_team_id)
        )
        score_rows = tuple(
            row for row in rows if team_id in (row.context.home_team_id, row.context.away_team_id)
        )
        fit_observations = tuple(
            item for item in observations if team_id not in (item.home_team_id, item.away_team_id)
        )
        if not fit_rows or not score_rows:
            raise RuntimeError("leave-team-out fold is empty")
        reference = fit_transferable_parameters(fit_rows, fit_observations, include_xg=False)
        challenger = fit_transferable_parameters(fit_rows, fit_observations, include_xg=True)
        reference_pairs.extend((reference, row) for row in score_rows)
        challenger_pairs.extend((challenger, row) for row in score_rows)
        fold_counts[str(team_id)] = len(score_rows)
    reference_score = _score_pairs(reference_pairs)
    challenger_score = _score_pairs(challenger_pairs)
    return {
        "challenger": challenger_score,
        "challenger_minus_reference_brier": (
            challenger_score["one_x_two_brier"] - reference_score["one_x_two_brier"]
        ),
        "challenger_minus_reference_log_loss": (
            challenger_score["joint_score_log_loss"] - reference_score["joint_score_log_loss"]
        ),
        "fold_count": len(team_ids),
        "fold_target_counts": fold_counts,
        "reference": reference_score,
        "scored_rows": len(reference_pairs),
    }


def _score(
    parameters: TransferableParametersV1, rows: Sequence[TransferableTrainingRowV1]
) -> dict[str, float]:
    return _score_pairs([(parameters, row) for row in rows])


def _score_pairs(
    pairs: Sequence[tuple[TransferableParametersV1, TransferableTrainingRowV1]],
) -> dict[str, float]:
    log_losses: list[float] = []
    brier_scores: list[float] = []
    for parameters, row in pairs:
        home_mean, away_mean = expected_goals(parameters, row.features)
        probability = math.exp(
            -home_mean
            + row.home_goals * math.log(home_mean)
            - math.lgamma(row.home_goals + 1)
            - away_mean
            + row.away_goals * math.log(away_mean)
            - math.lgamma(row.away_goals + 1)
        )
        log_losses.append(-math.log(probability))
        one_x_two = _one_x_two(home_mean, away_mean)
        actual = (
            0 if row.home_goals > row.away_goals else 1 if row.home_goals == row.away_goals else 2
        )
        brier_scores.append(
            sum((value - float(index == actual)) ** 2 for index, value in enumerate(one_x_two))
        )
    return {
        "joint_score_log_loss": sum(log_losses) / len(log_losses),
        "one_x_two_brier": sum(brier_scores) / len(brier_scores),
    }


def _one_x_two(home_mean: float, away_mean: float) -> tuple[float, float, float]:
    from scipy.stats import skellam

    away = float(skellam.cdf(-1, home_mean, away_mean))
    draw = float(skellam.pmf(0, home_mean, away_mean))
    return 1.0 - away - draw, draw, away


def _population_means(
    observations: Sequence[HistoryObservationV1],
) -> tuple[float, float]:
    return (
        sum(item.home_goals + item.away_goals for item in observations) / (2 * len(observations)),
        sum(item.home_npxg + item.away_npxg for item in observations) / (2 * len(observations)),
    )


def write_outputs(payload: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = cast(dict[str, dict[str, object]], payload["artifacts"])
    for role, artifact in artifacts.items():
        _write(output_dir / f"pitchapi-v3-{role}-artifact.json", artifact)
    _write(
        output_dir / "pitchapi-v3-transferability-development-evidence.json",
        cast(dict[str, object], payload["evidence"]),
    )


def _write(path: Path, payload: dict[str, object]) -> None:
    content = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(content)
    print(f"{hashlib.sha256(content).hexdigest()}  {path}")


def _development_observation(root: Path, item: dict[str, Any]) -> HistoryObservationV1:
    manifest = _load_path(root / str(item["manifest_path"]))
    normalized_sha256 = str(manifest["normalized_sha256"])
    normalized = _load_hashed(root, "normalized", normalized_sha256)
    home_provider = str(manifest["home_provider_team_id"])
    away_provider = str(manifest["away_provider_team_id"])
    goals = {home_provider: 0, away_provider: 0}
    npxg = {home_provider: 0.0, away_provider: 0.0}
    for period in cast(list[dict[str, Any]], normalized["data"]["periods"]):
        if period["period"] not in ("FirstHalf", "SecondHalf"):
            continue
        for shot in cast(list[dict[str, object]], period["shots"]):
            team_id = str(shot["team_id"])
            if shot["event_type"] == "Goal":
                goals[team_id] += 1
            if shot["situation"] != "Penalty":
                value = shot["expected_goals"]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise RuntimeError("development expected_goals is not numeric")
                npxg[team_id] += float(value)
    return HistoryObservationV1(
        match_id=UUID(str(manifest["canonical_match_id"])),
        kickoff_at=datetime.fromisoformat(str(manifest["kickoff_at"]).replace("Z", "+00:00")),
        home_team_id=UUID(str(manifest["home_canonical_team_id"])),
        away_team_id=UUID(str(manifest["away_canonical_team_id"])),
        home_goals=goals[home_provider],
        away_goals=goals[away_provider],
        home_npxg=npxg[home_provider],
        away_npxg=npxg[away_provider],
    )


def _load_hashed(root: Path, kind: str, digest: str) -> dict[str, Any]:
    path = root / kind / "sha256" / digest[:2] / f"{digest}.json"
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"{kind} resource hash mismatch")
    return _load_path(path)


def _load_path(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root", type=Path, default=Path(".local/pitchapi-snapshot-v1/primary")
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--dependency-lock-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = prepare(
        args.snapshot_root,
        source_commit=args.source_commit,
        dependency_lock_sha256=args.dependency_lock_sha256,
    )
    write_outputs(payload, args.output_dir)


if __name__ == "__main__":
    main()
