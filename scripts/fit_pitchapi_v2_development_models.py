#!/usr/bin/env python3
"""Fit frozen V2 models using only PitchAPI Bundesliga 2021/22."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.forecasting.artifacts import serialize_dixon_coles_fit
from football.forecasting.dixon_coles import DixonColesConfig, DixonColesModel, GoalMatch
from football.forecasting.phase3a_xg import (
    ALGORITHM_VERSION,
    FEATURE_ID,
    Phase3AXgForModelV1,
    XgFeatureMatchV1,
    deserialize_phase3a_fit,
    serialize_phase3a_fit,
)

DEVELOPMENT_SCOPE = "bundesliga_2021_22"
DEVELOPMENT_MANIFEST = "be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e"
SNAPSHOT_SHA256 = "435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea"


def build_rows(root: Path) -> tuple[XgFeatureMatchV1, ...]:
    season = _load(root / _hashed("manifests", DEVELOPMENT_MANIFEST))
    if season.get("scope_key") != DEVELOPMENT_SCOPE or season.get("role") != "development":
        raise RuntimeError("frozen development manifest identity or role changed")
    matches = []
    for entry in cast(list[dict[str, object]], season["matches"]):
        matches.append(_match_row(root, _load(root / str(entry["manifest_path"]))))
    matches.sort(key=lambda row: (row[0], row[1]))
    histories: defaultdict[UUID, deque[float]] = defaultdict(lambda: deque(maxlen=10))
    prior_team_xg: list[float] = []
    rows: list[XgFeatureMatchV1] = []
    position = 0
    while position < len(matches):
        kickoff = matches[position][0]
        end = position
        while end < len(matches) and matches[end][0] == kickoff:
            end += 1
        batch = matches[position:end]
        competition_mean = sum(prior_team_xg) / len(prior_team_xg) if prior_team_xg else 0.0
        for _, match_id, home, away, home_goals, away_goals, _, _ in batch:
            if len(histories[home]) == 10 and len(histories[away]) == 10:
                home_mean = sum(histories[home]) / 10
                away_mean = sum(histories[away]) / 10
                if min(home_mean, away_mean, competition_mean) <= 0.0:
                    raise RuntimeError("non-positive frozen xG signal input")
                rows.append(
                    XgFeatureMatchV1(
                        match=GoalMatch(
                            UUID(match_id), kickoff, home, away, home_goals, away_goals
                        ),
                        home_signal=math_log(home_mean / competition_mean),
                        away_signal=math_log(away_mean / competition_mean),
                    )
                )
        for _, _, home, away, _, _, home_xg, away_xg in batch:
            histories[home].append(home_xg)
            histories[away].append(away_xg)
            prior_team_xg.extend((home_xg, away_xg))
        position = end
    if len(rows) != 216:
        raise RuntimeError(f"expected 216 development targets, got {len(rows)}")
    return tuple(rows)


def fit(
    root: Path, source_commit: str, dependency_lock_sha256: str
) -> dict[str, dict[str, object]]:
    rows = build_rows(root)
    matches = tuple(row.match for row in rows)
    reference_config = DixonColesConfig(model_version="pitchapi-v2-reference-goals-dc-v1")
    challenger_config = DixonColesConfig(model_version="pitchapi-v2-challenger-npxg-last10-v1")
    reference = DixonColesModel(reference_config).fit(matches)
    challenger_model = Phase3AXgForModelV1(challenger_config)
    challenger = challenger_model.fit(rows)
    restored = deserialize_phase3a_fit(serialize_phase3a_fit(challenger))
    probe = rows[-1]
    if challenger_model.forecast(
        challenger.parameters,
        probe.match.home_team_id,
        probe.match.away_team_id,
        probe.home_signal,
        probe.away_signal,
    ) != challenger_model.forecast(
        restored.parameters,
        probe.match.home_team_id,
        probe.match.away_team_id,
        probe.home_signal,
        probe.away_signal,
    ):
        raise RuntimeError("challenger reload equivalence failed")
    common = {
        "contract": "PitchApiV2ModelArtifactV1",
        "development_scope": DEVELOPMENT_SCOPE,
        "development_manifest_sha256": DEVELOPMENT_MANIFEST,
        "evaluation_scope_loaded": False,
        "feature_target_count": len(rows),
        "source_commit": source_commit,
        "dependency_lock_sha256": dependency_lock_sha256,
        "snapshot_sha256": SNAPSHOT_SHA256,
    }
    return {
        "reference": {
            **common,
            "model_role": "REFERENCE",
            "algorithm_version": "dixon-coles-goals-v1",
            "state": serialize_dixon_coles_fit(reference),
        },
        "challenger": {
            **common,
            "model_role": "CHALLENGER",
            "algorithm_version": ALGORITHM_VERSION,
            "feature_id": FEATURE_ID,
            "state": serialize_phase3a_fit(challenger),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--snapshot-root", type=Path, default=Path(".local/pitchapi-snapshot-v1/primary")
    )
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--dependency-lock-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    artifacts = fit(args.snapshot_root, args.source_commit, args.dependency_lock_sha256)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for role, artifact in artifacts.items():
        payload = canonical_json_bytes(artifact) + b"\n"
        path = args.output_dir / f"pitchapi-v2-{role}-artifact.json"
        path.write_bytes(payload)
        print(f"{role} {hashlib.sha256(payload).hexdigest()} {path}")


def _hashed(kind: str, digest: str) -> str:
    return f"{kind}/sha256/{digest[:2]}/{digest}.json"


def _load(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _match_row(
    root: Path, manifest: dict[str, Any]
) -> tuple[datetime, str, UUID, UUID, int, int, float, float]:
    normalized_hash = str(manifest["normalized_sha256"])
    resource_path = root / _hashed("normalized", normalized_hash)
    if hashlib.sha256(resource_path.read_bytes()).hexdigest() != normalized_hash:
        raise RuntimeError("development normalized resource hash mismatch")
    resource = _load(resource_path)
    home_provider = str(manifest["home_provider_team_id"])
    away_provider = str(manifest["away_provider_team_id"])
    xg = {home_provider: 0.0, away_provider: 0.0}
    goals = {home_provider: 0, away_provider: 0}
    for period in cast(list[dict[str, Any]], resource["data"]["periods"]):
        if period["period"] not in ("FirstHalf", "SecondHalf"):
            continue
        for shot in cast(list[dict[str, object]], period["shots"]):
            team = str(shot["team_id"])
            if shot["event_type"] == "Goal":
                goals[team] += 1
            if shot["situation"] != "Penalty":
                xg[team] += _float(shot["expected_goals"], "expected_goals")
    return (
        datetime.fromisoformat(str(manifest["kickoff_at"]).replace("Z", "+00:00")),
        str(manifest["canonical_match_id"]),
        UUID(str(manifest["home_canonical_team_id"])),
        UUID(str(manifest["away_canonical_team_id"])),
        goals[home_provider],
        goals[away_provider],
        xg[home_provider],
        xg[away_provider],
    )


def _float(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{field} must be numeric")
    return float(value)


def math_log(value: float) -> float:
    import math

    return math.log(value)


if __name__ == "__main__":
    main()
