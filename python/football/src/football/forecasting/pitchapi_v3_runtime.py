"""Frozen snapshot and Rust adapters for an authorized PitchAPI V3 run."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from scipy.stats import ks_2samp

from football.contracts.source import canonical_json_bytes
from football.forecasting.pitchapi_v3 import (
    PROTOCOL_ID,
    HistoryObservationV1,
    RollingHistoryV1,
    TransferableForecastContextV1,
)
from football.forecasting.pitchapi_v3_evaluation import ExactScoreDistributionV1, calibration_fit
from football.forecasting.pitchapi_v3_executor import (
    ForecastBatchV1,
    PreparedTargetV1,
    RevealedOutcomeV1,
    SimulationReceiptV1,
    V4SimulationReceiptV1,
)

SNAPSHOT_ID = "9eb89b53-1a29-5dcd-bc9b-24f0320b3c8d"
SNAPSHOT_SHA256 = "435bc3760cd3790e9f79cfc48801da0289fa73dbd30b02e63dc84468fd5a74ea"
CORPUS_SHA256 = "42d229ddbdc8a1349115c2cb258d970b82083265f64cadf6050b7a2f46b8f9a4"
FIREWALL_SHA256 = "bb5e9899fc73acda3d1f1f67e27ad4004ee83867b30ceb3b74e2e870303e14d2"
ALIAS_SHA256 = "0ffe5660872a081ae262c6045825b0e1db4e775093cd213a02cd9947ffa47716"
SIMULATION_COUNT = 112_460
ALGORITHM_VERSION = "pitchapi-score-categorical-v1"
SEED_SCHEDULE_ID = "pitchapi-v3-splitmix64-sha256-v1"
V4_PROTOCOL_ID = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V4"
V4_ALGORITHM_VERSION = "pitchapi-score-categorical-v2"
V4_SEED_SCHEDULE_ID = "pitchapi-v4-splitmix64-sha256-v1"
V3_CANONICALIZER_SHA256 = "4f4709b38c8d6c72e93c433074fed3d7788eb4018cfddfe67f73ae5f438e209c"
_DOMAINS = {
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


class PitchApiV3RuntimeError(RuntimeError):
    """Frozen runtime input or subprocess violated the V3 contract."""


class PitchApiSnapshotCorpusV3:
    """Reveal evaluation outcomes only after each target batch is sealed."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._pending: tuple[str, tuple[HistoryObservationV1, ...], frozenset[str]] | None = None
        self._history: RollingHistoryV1 | None = None
        self._xg: dict[str, list[float]] = defaultdict(list)
        self._goals: dict[str, list[int]] = defaultdict(list)
        self._situations: dict[str, Counter[str]] = defaultdict(Counter)
        self._situation_xg: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._penalties: dict[str, list[float]] = defaultdict(list)

    def preflight(self) -> Mapping[str, object]:
        result = _load_path(self._root.parent / "RESULT.json")
        expected = {
            "snapshot_id": SNAPSHOT_ID,
            "snapshot_sha256": SNAPSHOT_SHA256,
            "corpus_sha256": CORPUS_SHA256,
            "firewall_sha256": FIREWALL_SHA256,
            "exact_evaluation_targets": 712,
        }
        if any(result.get(key) != value for key, value in expected.items()):
            raise PitchApiV3RuntimeError("snapshot acquisition report identity mismatch")
        for digest, _ in _DOMAINS.values():
            season = _load_hashed(self._root, "manifests", digest)
            for item in cast(list[dict[str, Any]], season["matches"]):
                manifest_path = self._root / str(item["manifest_path"])
                if (
                    hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                    != item["manifest_sha256"]
                ):
                    raise PitchApiV3RuntimeError("match manifest hash mismatch")
                manifest = _load_path(manifest_path)
                for kind in ("raw", "normalized"):
                    resource_digest = str(manifest[f"{kind}_sha256"])
                    resource_path = _hashed_path(self._root, kind, resource_digest)
                    if hashlib.sha256(resource_path.read_bytes()).hexdigest() != resource_digest:
                        raise PitchApiV3RuntimeError(f"{kind} resource hash mismatch")
        return {
            "alias_reconciliation_sha256": ALIAS_SHA256,
            "corpus_sha256": CORPUS_SHA256,
            "firewall_sha256": FIREWALL_SHA256,
            "protocol_id": PROTOCOL_ID,
            "snapshot_sha256": SNAPSHOT_SHA256,
            "target_count": 712,
        }

    def batches(self) -> Iterator[ForecastBatchV1]:
        if self._pending is not None:
            raise PitchApiV3RuntimeError("a previous batch remains unrevealed")
        global_batch = 0
        for domain, (digest, expected_targets) in _DOMAINS.items():
            season = _load_hashed(self._root, "manifests", digest)
            targets = frozenset(cast(dict[str, Any], season["target_plan"])["target_ids"])
            if len(targets) != expected_targets:
                raise PitchApiV3RuntimeError("frozen target count mismatch")
            manifests = [
                _load_path(self._root / str(item["manifest_path"]))
                for item in cast(list[dict[str, Any]], season["matches"])
            ]
            manifests.sort(key=lambda row: (str(row["kickoff_at"]), str(row["canonical_match_id"])))
            self._history = RollingHistoryV1()
            position = 0
            while position < len(manifests):
                end = position + 1
                while (
                    end < len(manifests)
                    and manifests[end]["kickoff_at"] == manifests[position]["kickoff_at"]
                ):
                    end += 1
                observations = tuple(
                    self._read_observation(domain, row) for row in manifests[position:end]
                )
                target_observations = tuple(
                    row for row in observations if str(row.match_id) in targets
                )
                if not target_observations:
                    self._history.update_batch(observations)
                    position = end
                    continue
                prepared = tuple(
                    PreparedTargetV1(
                        context=TransferableForecastContextV1(
                            match_id=row.match_id,
                            scope_key=domain,
                            kickoff_at=row.kickoff_at,
                            home_team_id=row.home_team_id,
                            away_team_id=row.away_team_id,
                        ),
                        domain=domain,
                        kickoff_batch=global_batch,
                        features=self._history.features(
                            row.home_team_id,
                            row.away_team_id,
                            cutoff=row.kickoff_at,
                        ),
                    )
                    for row in target_observations
                )
                batch_id = f"{domain}:{global_batch}"
                self._pending = (batch_id, observations, targets)
                yield ForecastBatchV1(batch_id=batch_id, targets=prepared)
                if self._pending is not None:
                    raise PitchApiV3RuntimeError("executor did not reveal sealed batch")
                global_batch += 1
                position = end

    def reveal_batch(self, batch_id: str) -> tuple[RevealedOutcomeV1, ...]:
        if self._pending is None or self._pending[0] != batch_id or self._history is None:
            raise PitchApiV3RuntimeError("batch reveal order is invalid")
        _, observations, targets = self._pending
        outcomes = tuple(
            RevealedOutcomeV1(str(row.match_id), row.home_goals, row.away_goals)
            for row in observations
            if str(row.match_id) in targets
        )
        self._history.update_batch(observations)
        self._pending = None
        return outcomes

    def heterogeneity(self) -> Mapping[str, object]:
        domains: dict[str, object] = {}
        for domain in _DOMAINS:
            values = self._xg[domain]
            ordered = sorted(values)
            domains[domain] = {
                "goal_on_logit_xg_calibration": asdict(
                    calibration_fit(tuple(values), tuple(self._goals[domain]))
                ),
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
        pairwise = []
        names = tuple(_DOMAINS)
        for left_index, left in enumerate(names):
            for right in names[left_index + 1 :]:
                result = ks_2samp(self._xg[left], self._xg[right], method="auto")
                pairwise.append(
                    {
                        "left": left,
                        "p_value": float(result.pvalue),
                        "right": right,
                        "statistic": float(result.statistic),
                    }
                )
        situation_pairwise = []
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

    def _read_observation(self, domain: str, manifest: dict[str, Any]) -> HistoryObservationV1:
        normalized = _load_hashed(self._root, "normalized", str(manifest["normalized_sha256"]))
        home_provider = str(manifest["home_provider_team_id"])
        away_provider = str(manifest["away_provider_team_id"])
        goals = {home_provider: 0, away_provider: 0}
        npxg = {home_provider: 0.0, away_provider: 0.0}
        for period in cast(list[dict[str, Any]], normalized["data"]["periods"]):
            if period["period"] not in ("FirstHalf", "SecondHalf"):
                continue
            for shot in cast(list[dict[str, object]], period["shots"]):
                team = str(shot["team_id"])
                value = _finite_float(shot["expected_goals"], "expected_goals")
                situation = str(shot["situation"])
                self._xg[domain].append(value)
                self._goals[domain].append(int(shot["event_type"] == "Goal"))
                self._situations[domain][situation] += 1
                self._situation_xg[domain][situation].append(value)
                if situation == "Penalty":
                    self._penalties[domain].append(value)
                else:
                    npxg[team] += value
                if shot["event_type"] == "Goal":
                    goals[team] += 1
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


class RustSimulationV3:
    def __init__(self, *, binary: Path, policy_sha256: str, build_sha256: str) -> None:
        if hashlib.sha256(binary.read_bytes()).hexdigest() != build_sha256:
            raise PitchApiV3RuntimeError("Rust executable identity mismatch")
        self._binary = binary
        self._policy_sha256 = policy_sha256
        self._build_sha256 = build_sha256

    def validate(
        self,
        *,
        target: PreparedTargetV1,
        model_role: str,
        model_artifact_sha256: str,
        distribution: ExactScoreDistributionV1,
    ) -> SimulationReceiptV1:
        atoms = [
            {
                "away_goals": away,
                "home_goals": home,
                "kind": "EXACT_SCORE",
                "probability": probability,
            }
            for home, away, probability in distribution.atoms
        ] + [
            {
                "away_goals": None,
                "home_goals": None,
                "kind": "UNRESOLVED_TAIL",
                "probability": distribution.unresolved_tail,
            }
        ]
        probability_sha256 = hashlib.sha256(
            self._canonicalize(canonical_json_bytes(atoms), atoms=True)
        ).hexdigest()
        forecast_payload = {
            "model_artifact_sha256": model_artifact_sha256,
            "model_role": model_role,
            "probability_sha256": probability_sha256,
            "target_id": str(target.context.match_id),
        }
        forecast_sha256 = hashlib.sha256(canonical_json_bytes(forecast_payload)).hexdigest()
        payload = {
            "algorithm_version": ALGORITHM_VERSION,
            "analytic_probabilities": _analytic_probabilities(distribution),
            "atoms": atoms,
            "canonical_match_id": str(target.context.match_id),
            "forecast_artifact_sha256": forecast_sha256,
            "forecast_id": f"{target.context.match_id}:{model_role.lower()}",
            "forecast_probability_sha256": probability_sha256,
            "model_artifact_sha256": model_artifact_sha256,
            "policy_sha256": self._policy_sha256,
            "protocol_id": PROTOCOL_ID,
            "schema_version": "PitchApiSimulationInputV1",
            "seed_schedule_id": SEED_SCHEDULE_ID,
            "simulation_count": SIMULATION_COUNT,
        }
        input_bytes = self._canonicalize(canonical_json_bytes(payload))
        input_sha256 = hashlib.sha256(input_bytes).hexdigest()
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(input_bytes)
            handle.flush()
            serial = self._run(handle.name, input_sha256, 1)
            parallel = self._run(handle.name, input_sha256, 4)
        if serial != parallel:
            raise PitchApiV3RuntimeError("Rust serial/parallel replay mismatch")
        output = json.loads(serial)
        if output.get("status") != "PASS" or output.get("simulation_count") != SIMULATION_COUNT:
            raise PitchApiV3RuntimeError("Rust simulation result is not PASS")
        return SimulationReceiptV1(
            target_id=str(target.context.match_id),
            model_role=model_role,
            seed_identity=str(output["base_seed_commitment"]),
            simulation_count=SIMULATION_COUNT,
            input_sha256=input_sha256,
            output_sha256=hashlib.sha256(serial).hexdigest(),
            rust_build_sha256=self._build_sha256,
            status="PASS",
        )

    def _run(self, path: str, digest: str, workers: int) -> bytes:
        result = subprocess.run(
            [str(self._binary), path, digest, str(workers)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PitchApiV3RuntimeError(
                f"Rust simulation failed: {result.stderr.decode(errors='replace')}"
            )
        return result.stdout

    def _canonicalize(self, payload: bytes, *, atoms: bool = False) -> bytes:
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(payload)
            handle.flush()
            result = subprocess.run(
                [
                    str(self._binary),
                    "--canonicalize-atoms" if atoms else "--canonicalize",
                    handle.name,
                ],
                capture_output=True,
                check=False,
            )
        if result.returncode != 0:
            raise PitchApiV3RuntimeError(
                f"Rust canonicalization failed: {result.stderr.decode(errors='replace')}"
            )
        return result.stdout


class PitchApiSnapshotCorpusV4(PitchApiSnapshotCorpusV3):
    def preflight(self) -> Mapping[str, object]:
        result = dict(super().preflight())
        result["protocol_id"] = V4_PROTOCOL_ID
        return result


class RustSimulationV4:
    def __init__(
        self,
        *,
        binary: Path,
        canonicalizer_binary: Path,
        policy_sha256: str,
        build_sha256: str,
    ) -> None:
        if hashlib.sha256(binary.read_bytes()).hexdigest() != build_sha256:
            raise PitchApiV3RuntimeError("V4 Rust executable identity mismatch")
        if hashlib.sha256(canonicalizer_binary.read_bytes()).hexdigest() != V3_CANONICALIZER_SHA256:
            raise PitchApiV3RuntimeError("frozen V3 canonicalizer identity mismatch")
        self._binary = binary
        self._canonicalizer_binary = canonicalizer_binary
        self._policy_sha256 = policy_sha256
        self._build_sha256 = build_sha256

    def validate(
        self,
        *,
        target: PreparedTargetV1,
        model_role: str,
        model_artifact_sha256: str,
        distribution: ExactScoreDistributionV1,
    ) -> SimulationReceiptV1:
        atoms = [
            {
                "away_goals": away,
                "home_goals": home,
                "kind": "EXACT_SCORE",
                "probability": probability,
            }
            for home, away, probability in distribution.atoms
        ] + [
            {
                "away_goals": None,
                "home_goals": None,
                "kind": "UNRESOLVED_TAIL",
                "probability": distribution.unresolved_tail,
            }
        ]
        probability_sha256 = hashlib.sha256(self._canonicalize_atoms(atoms)).hexdigest()
        forecast_payload = {
            "model_artifact_sha256": model_artifact_sha256,
            "model_role": model_role,
            "probability_sha256": probability_sha256,
            "target_id": str(target.context.match_id),
        }
        payload = {
            "algorithm_version": V4_ALGORITHM_VERSION,
            "analytic_probabilities": _analytic_probabilities(distribution),
            "atoms": atoms,
            "canonical_match_id": str(target.context.match_id),
            "forecast_artifact_sha256": hashlib.sha256(
                canonical_json_bytes(forecast_payload)
            ).hexdigest(),
            "forecast_id": f"{target.context.match_id}:{model_role.lower()}",
            "forecast_probability_sha256": probability_sha256,
            "model_artifact_sha256": model_artifact_sha256,
            "policy_sha256": self._policy_sha256,
            "protocol_id": V4_PROTOCOL_ID,
            "schema_version": "PitchApiSimulationInputV1",
            "seed_schedule_id": V4_SEED_SCHEDULE_ID,
            "simulation_count": SIMULATION_COUNT,
        }
        input_bytes = canonical_json_bytes(payload)
        input_sha256 = hashlib.sha256(input_bytes).hexdigest()
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(input_bytes)
            handle.flush()
            serial = self._run(handle.name, input_sha256, 1)
            parallel = self._run(handle.name, input_sha256, 4)
        if serial != parallel:
            raise PitchApiV3RuntimeError("V4 Rust serial/parallel replay mismatch")
        output = cast(dict[str, Any], json.loads(serial))
        status = str(output.get("status"))
        if status not in {"PASS", "PASS_WITH_WARNINGS"}:
            raise PitchApiV3RuntimeError("V4 Rust simulation result did not pass")
        if output.get("simulation_count") != SIMULATION_COUNT:
            raise PitchApiV3RuntimeError("V4 Rust simulation count mismatch")
        return V4SimulationReceiptV1(
            target_id=str(target.context.match_id),
            model_role=model_role,
            seed_identity=str(output["base_seed_commitment"]),
            simulation_count=SIMULATION_COUNT,
            input_sha256=input_sha256,
            output_sha256=hashlib.sha256(serial).hexdigest(),
            rust_build_sha256=self._build_sha256,
            status=status,
            total_variation=float(output["total_variation"]),
            total_variation_limit=float(output["total_variation_limit"]),
            warnings=tuple(str(item) for item in cast(list[object], output["warnings"])),
        )

    def _run(self, path: str, digest: str, workers: int) -> bytes:
        result = subprocess.run(
            [str(self._binary), path, digest, str(workers)],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise PitchApiV3RuntimeError(
                f"V4 Rust simulation failed: {result.stderr.decode(errors='replace')}"
            )
        return result.stdout

    def _canonicalize_atoms(self, atoms: list[dict[str, object]]) -> bytes:
        with tempfile.NamedTemporaryFile() as handle:
            handle.write(canonical_json_bytes(atoms))
            handle.flush()
            result = subprocess.run(
                [str(self._canonicalizer_binary), "--canonicalize-atoms", handle.name],
                capture_output=True,
                check=False,
            )
        if result.returncode != 0:
            raise PitchApiV3RuntimeError(
                f"V3 atom canonicalization failed: {result.stderr.decode(errors='replace')}"
            )
        return result.stdout


def load_model_parameters(payload: Mapping[str, object]) -> dict[str, float]:
    if payload.get("contract") != "PitchApiV3TransferableModelArtifactV1":
        raise PitchApiV3RuntimeError("unsupported V3 model artifact")
    if payload.get("team_id_parameters") is not False:
        raise PitchApiV3RuntimeError("V3 artifact must not contain team-ID parameters")
    parameters = payload.get("parameters")
    if not isinstance(parameters, dict):
        raise PitchApiV3RuntimeError("V3 model parameters are missing")
    return {str(key): _finite_float(value, str(key)) for key, value in parameters.items()}


def _analytic_probabilities(
    distribution: ExactScoreDistributionV1,
) -> list[dict[str, object]]:
    values: dict[str, float] = {}
    for home in range(6):
        for away in range(6):
            label = f"score:{home if home < 5 else '5+'}-{away if away < 5 else '5+'}"
            values[label] = 0.0
    for home, away, probability in distribution.atoms:
        score_id = f"score:{home if home < 5 else '5+'}-{away if away < 5 else '5+'}"
        values[score_id] += probability
    values["outcome:home_win"] = sum(
        value for home, away, value in distribution.atoms if home > away
    )
    values["outcome:draw"] = sum(value for home, away, value in distribution.atoms if home == away)
    values["outcome:away_win"] = sum(
        value for home, away, value in distribution.atoms if home < away
    )
    values["btts:yes"] = sum(
        value for home, away, value in distribution.atoms if home > 0 and away > 0
    )
    values["btts:no"] = 1.0 - values["btts:yes"]
    for threshold in range(5):
        over = sum(value for home, away, value in distribution.atoms if home + away > threshold)
        values[f"total:over_{threshold}.5"] = over
        values[f"total:under_{threshold}.5"] = 1.0 - over
    values["clean_sheet:home_yes"] = sum(
        value for _, away, value in distribution.atoms if away == 0
    )
    values["clean_sheet:home_no"] = 1.0 - values["clean_sheet:home_yes"]
    values["clean_sheet:away_yes"] = sum(
        value for home, _, value in distribution.atoms if home == 0
    )
    values["clean_sheet:away_no"] = 1.0 - values["clean_sheet:away_yes"]
    for total in range(6):
        label = str(total) if total < 5 else "5+"
        values[f"total_goals:{label}"] = sum(
            value for home, away, value in distribution.atoms if min(home + away, 5) == total
        )
    values["unresolved_tail"] = distribution.unresolved_tail
    return [
        {"event_id": event_id, "probability": probability}
        for event_id, probability in values.items()
    ]


def _hashed_path(root: Path, kind: str, digest: str) -> Path:
    return root / kind / "sha256" / digest[:2] / f"{digest}.json"


def _load_hashed(root: Path, kind: str, digest: str) -> dict[str, Any]:
    path = _hashed_path(root, kind, digest)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise PitchApiV3RuntimeError(f"{kind} resource hash mismatch")
    return _load_path(path)


def _load_path(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PitchApiV3RuntimeError(f"{field_name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PitchApiV3RuntimeError(f"{field_name} must be finite")
    return result


def _quantile(values: list[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction
