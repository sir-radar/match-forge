from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
from jsonschema import validate as validate_json

from experiments.sprint1_roundtrip import NORMALIZER_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_ROOT = PROJECT_ROOT / "experiments" / "sprint1_roundtrip"
RUNTIME_ROOT = PROJECT_ROOT / ".local" / "prototype" / "sprint1-roundtrip"
FIXTURE_PATH = EXPERIMENT_ROOT / "prototype-fixture.json"
SOURCE_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "contracts" / "source-manifest-v1.schema.json"
DATASET_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "contracts" / "dataset-manifest-v1.schema.json"
EVENT_SCHEMA_SPEC_PATH = PROJECT_ROOT / "schemas" / "arrow" / "normalized-events-v1.json"
THREE_SIXTY_SCHEMA_SPEC_PATH = PROJECT_ROOT / "schemas" / "arrow" / "three-sixty-v1.json"
QUALITY_POLICY_PATH = PROJECT_ROOT / "schemas" / "quality" / "statsbomb-quality-policy-v1.json"

NAMESPACE = uuid.UUID("6f57ba57-984c-4c42-877d-d355561742ea")

KNOWN_EVENT_TYPES = {
    2: "ball-recovery",
    3: "dispossessed",
    4: "duel",
    6: "block",
    8: "offside",
    9: "clearance",
    10: "interception",
    14: "dribble",
    16: "shot",
    17: "pressure",
    18: "half-start",
    19: "substitution",
    21: "foul-won",
    22: "foul-committed",
    23: "goalkeeper",
    24: "bad-behaviour",
    26: "player-on",
    27: "player-off",
    28: "shield",
    30: "pass",
    33: "fifty-fifty",
    34: "half-end",
    35: "starting-xi",
    36: "tactical-shift",
    38: "miscontrol",
    39: "dribbled-past",
    40: "injury-stoppage",
    42: "ball-receipt",
    43: "carry",
}


class PrototypeError(RuntimeError):
    """Base failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SourceIntegrityError(PrototypeError):
    pass


@dataclass(frozen=True)
class Finding:
    rule_code: str
    severity: str
    action: str
    scope_type: str
    message: str
    evidence: dict[str, Any]
    provider_entity_id: str | None = None
    field_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Acquisition:
    manifest: dict[str, Any]
    manifest_path: Path
    manifest_sha256: str
    statuses: dict[str, str]


@dataclass(frozen=True)
class NormalizedEvents:
    rows: list[dict[str, Any]]
    findings: list[Finding]
    raw_count: int
    quarantined_count: int
    ignored_count: int


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_text(value: datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_uuid(kind: str, provider_id: str | int) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:statsbomb_open_data:{provider_id}")


def dataset_uuid(source_sha: str, schema_hash: str, dataset_name: str = "events") -> uuid.UUID:
    identity = f"dataset:{dataset_name}:{source_sha}:{schema_hash}:{NORMALIZER_VERSION}:3869685"
    return uuid.uuid5(NAMESPACE, identity)


def load_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def write_json_exclusive_or_verify(path: Path, value: dict[str, Any]) -> None:
    payload = canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise PrototypeError("IMMUTABLE_ARTIFACT_CONFLICT", f"conflicting artifact: {path}")
        return
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def load_fixture() -> dict[str, Any]:
    fixture = load_json(FIXTURE_PATH)
    assert isinstance(fixture, dict)
    return fixture


def _download_to_cache(source_sha: str, provider_path: str, cache_path: Path) -> None:
    url = f"https://raw.githubusercontent.com/statsbomb/open-data/{source_sha}/{provider_path}"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    os.replace(temporary, cache_path)


def acquire_source() -> Acquisition:
    fixture = load_fixture()
    source_sha = str(fixture["source_git_sha"])
    raw_root = RUNTIME_ROOT / "raw" / "provider=statsbomb_open_data" / f"snapshot={source_sha}"
    cache_root = RUNTIME_ROOT / "source-cache"
    manifest_path = RUNTIME_ROOT / "manifests" / "source-manifest-v1.json"
    statuses: dict[str, str] = {}
    manifest_resources: list[dict[str, Any]] = []

    for resource in fixture["resources"]:
        provider_path = str(resource["path"])
        expected_size = int(resource["size_bytes"])
        expected_hash = str(resource["sha256"])
        raw_path = raw_root / provider_path
        cache_path = cache_root / provider_path

        if raw_path.exists():
            actual_hash = sha256_path(raw_path)
            if actual_hash != expected_hash or raw_path.stat().st_size != expected_size:
                raise SourceIntegrityError(
                    "SB_SOURCE_CHECKSUM_MISMATCH",
                    f"immutable raw resource mismatch: {provider_path}",
                )
            status = "verified_existing"
        else:
            if not cache_path.exists():
                _download_to_cache(source_sha, provider_path, cache_path)
            cache_hash = sha256_path(cache_path)
            if cache_hash != expected_hash or cache_path.stat().st_size != expected_size:
                raise SourceIntegrityError(
                    "SB_SOURCE_CHECKSUM_MISMATCH",
                    f"downloaded resource mismatch: {provider_path}",
                )
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = raw_path.with_suffix(raw_path.suffix + ".part")
            shutil.copyfile(cache_path, temporary)
            if sha256_path(temporary) != expected_hash:
                raise SourceIntegrityError(
                    "SB_SOURCE_CHECKSUM_MISMATCH",
                    f"staged resource mismatch: {provider_path}",
                )
            os.replace(temporary, raw_path)
            status = "acquired"

        statuses[provider_path] = status
        manifest_resources.append(
            {
                "path": provider_path,
                "size_bytes": expected_size,
                "sha256": expected_hash,
                "raw_path": str(raw_path.relative_to(PROJECT_ROOT)),
                "status": "acquired",
            }
        )

    if manifest_path.exists():
        manifest = load_json(manifest_path)
    else:
        manifest = {
            "contract": "SourceManifestV1",
            "provider": fixture["provider"],
            "repository": fixture["repository"],
            "source_git_sha": source_sha,
            "acquired_at": utc_text(),
            "resources": manifest_resources,
        }
        schema = load_json(SOURCE_SCHEMA_PATH)
        validate_json(manifest, schema)
        write_json_exclusive_or_verify(manifest_path, manifest)

    schema = load_json(SOURCE_SCHEMA_PATH)
    validate_json(manifest, schema)
    for resource in manifest["resources"]:
        path = PROJECT_ROOT / resource["raw_path"]
        if sha256_path(path) != resource["sha256"]:
            raise SourceIntegrityError(
                "SB_SOURCE_CHECKSUM_MISMATCH",
                f"manifest read-back mismatch: {resource['path']}",
            )

    return Acquisition(
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_sha256=sha256_path(manifest_path),
        statuses=statuses,
    )


def raw_resource_path(provider_path: str) -> Path:
    fixture = load_fixture()
    return (
        RUNTIME_ROOT
        / "raw"
        / "provider=statsbomb_open_data"
        / f"snapshot={fixture['source_git_sha']}"
        / provider_path
    )


def load_source_documents() -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    fixture = load_fixture()
    competition_rows = load_json(raw_resource_path("data/competitions.json"))
    match_rows = load_json(raw_resource_path("data/matches/43/106.json"))
    events = load_json(raw_resource_path("data/events/3869685.json"))
    lineups = load_json(raw_resource_path("data/lineups/3869685.json"))
    three_sixty = load_json(raw_resource_path("data/three-sixty/3869685.json"))
    competition = next(
        row
        for row in competition_rows
        if row["competition_id"] == fixture["competition_id"]
        and row["season_id"] == fixture["season_id"]
    )
    match = next(row for row in match_rows if row["match_id"] == fixture["match_id"])
    return competition, [match], events, lineups, three_sixty


def quality_policy() -> dict[str, Any]:
    policy = load_json(QUALITY_POLICY_PATH)
    assert isinstance(policy, dict)
    return policy


def policy_hash() -> str:
    return sha256_path(QUALITY_POLICY_PATH)


def finding(
    rule_code: str,
    scope_type: str,
    message: str,
    evidence: dict[str, Any],
    provider_entity_id: str | None = None,
    field_path: str | None = None,
) -> Finding:
    rule = quality_policy()["rules"][rule_code]
    return Finding(
        rule_code=rule_code,
        severity=str(rule["severity"]),
        action=str(rule["action"]),
        scope_type=scope_type,
        message=message,
        evidence=evidence,
        provider_entity_id=provider_entity_id,
        field_path=field_path,
    )


def normalize_events(events: list[dict[str, Any]], provider_match_id: int) -> NormalizedEvents:
    indexes = [int(event["index"]) for event in events]
    duplicate_indexes = sorted({index for index in indexes if indexes.count(index) > 1})
    if duplicate_indexes:
        duplicate = duplicate_indexes[0]
        return NormalizedEvents(
            rows=[],
            findings=[
                finding(
                    "SB_DUPLICATE_EVENT_INDEX",
                    "event",
                    f"conflicting duplicate event index {duplicate}",
                    {"event_index": duplicate},
                    field_path="index",
                )
            ],
            raw_count=len(events),
            quarantined_count=len(events),
            ignored_count=0,
        )

    rows: list[dict[str, Any]] = []
    findings: list[Finding] = []
    canonical_match_id = stable_uuid("match", provider_match_id)

    for event in sorted(events, key=lambda item: int(item["index"])):
        event_id = str(event["id"])
        event_type = event["type"]
        event_type_id = int(event_type["id"])
        canonical_type = KNOWN_EVENT_TYPES.get(event_type_id)
        if canonical_type is None:
            findings.append(
                finding(
                    "SB_UNKNOWN_EVENT_TYPE",
                    "event",
                    f"unknown provider event type {event_type_id}",
                    {"provider_id": event_type_id, "provider_name": event_type.get("name")},
                    provider_entity_id=event_id,
                    field_path="type",
                )
            )

        if "prototype_future_field" in event:
            findings.append(
                finding(
                    "SB_UNKNOWN_ADDITIVE_FIELD",
                    "event",
                    "unknown additive field preserved in raw payload",
                    {"field": "prototype_future_field"},
                    provider_entity_id=event_id,
                    field_path="prototype_future_field",
                )
            )

        location = event.get("location")
        source_x: float | None = None
        source_y: float | None = None
        x_norm: float | None = None
        y_norm: float | None = None
        location_quality = "missing"
        if isinstance(location, list) and len(location) >= 2:
            source_x = float(location[0])
            source_y = float(location[1])
            if 0 <= source_x <= 120 and 0 <= source_y <= 80:
                x_norm = source_x / 120
                y_norm = source_y / 80
                location_quality = "valid"
            else:
                location_quality = "out_of_bounds"
                findings.append(
                    finding(
                        "SB_EVENT_LOCATION_OUT_OF_BOUNDS",
                        "event",
                        "provider coordinate is outside StatsBomb 120x80 bounds",
                        {"source_x": source_x, "source_y": source_y},
                        provider_entity_id=event_id,
                        field_path="location",
                    )
                )

        team = event.get("team") or {}
        player = event.get("player") or {}
        team_id = team.get("id")
        player_id = player.get("id")
        rows.append(
            {
                "canonical_event_id": str(stable_uuid("event", event_id)),
                "canonical_match_id": str(canonical_match_id),
                "provider_event_id": event_id,
                "provider_match_id": str(provider_match_id),
                "event_index": int(event["index"]),
                "period": int(event["period"]),
                "timestamp": str(event["timestamp"]),
                "minute": int(event["minute"]),
                "second": int(event["second"]),
                "provider_event_type_id": str(event_type_id),
                "provider_event_type_name": str(event_type["name"]),
                "canonical_event_type_id": canonical_type,
                "canonical_team_id": str(stable_uuid("team", team_id)) if team_id else None,
                "provider_team_id": str(team_id) if team_id else None,
                "canonical_player_id": str(stable_uuid("player", player_id)) if player_id else None,
                "provider_player_id": str(player_id) if player_id else None,
                "source_coordinate_system": "statsbomb_120x80" if location else None,
                "source_x": source_x,
                "source_y": source_y,
                "x_norm": x_norm,
                "y_norm": y_norm,
                "location_quality": location_quality,
                "provider_payload_json": canonical_json_bytes(event).decode("utf-8"),
            }
        )

    return NormalizedEvents(
        rows=rows,
        findings=findings,
        raw_count=len(events),
        quarantined_count=0,
        ignored_count=0,
    )


def normalized_event_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("canonical_event_id", pa.string(), nullable=False),
            pa.field("canonical_match_id", pa.string(), nullable=False),
            pa.field("provider_event_id", pa.string(), nullable=False),
            pa.field("provider_match_id", pa.string(), nullable=False),
            pa.field("event_index", pa.int32(), nullable=False),
            pa.field("period", pa.int8(), nullable=False),
            pa.field("timestamp", pa.string(), nullable=False),
            pa.field("minute", pa.int16(), nullable=False),
            pa.field("second", pa.int16(), nullable=False),
            pa.field("provider_event_type_id", pa.string(), nullable=False),
            pa.field("provider_event_type_name", pa.string(), nullable=False),
            pa.field("canonical_event_type_id", pa.string()),
            pa.field("canonical_team_id", pa.string()),
            pa.field("provider_team_id", pa.string()),
            pa.field("canonical_player_id", pa.string()),
            pa.field("provider_player_id", pa.string()),
            pa.field("source_coordinate_system", pa.string()),
            pa.field("source_x", pa.float64()),
            pa.field("source_y", pa.float64()),
            pa.field("x_norm", pa.float64()),
            pa.field("y_norm", pa.float64()),
            pa.field("location_quality", pa.string(), nullable=False),
            pa.field("provider_payload_json", pa.string(), nullable=False),
        ]
    )


def three_sixty_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("canonical_event_id", pa.string(), nullable=False),
            pa.field("provider_event_id", pa.string(), nullable=False),
            pa.field("visible_area_json", pa.string(), nullable=False),
            pa.field("freeze_frame_json", pa.string(), nullable=False),
        ]
    )


def normalize_three_sixty(frames: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "canonical_event_id": str(stable_uuid("event", frame["event_uuid"])),
            "provider_event_id": str(frame["event_uuid"]),
            "visible_area_json": canonical_json_bytes(frame.get("visible_area", [])).decode(
                "utf-8"
            ),
            "freeze_frame_json": canonical_json_bytes(frame.get("freeze_frame", [])).decode(
                "utf-8"
            ),
        }
        for frame in sorted(frames, key=lambda item: str(item["event_uuid"]))
    ]


def logical_checksum(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical_json_bytes(row))
        digest.update(b"\n")
    return digest.hexdigest()


def event_schema_hash() -> str:
    return sha256_path(EVENT_SCHEMA_SPEC_PATH)


def three_sixty_schema_hash() -> str:
    return sha256_path(THREE_SIXTY_SCHEMA_SPEC_PATH)


def validate_fixture_copy(path: Path, expected_hash: str) -> Finding | None:
    actual = sha256_path(path)
    if actual == expected_hash:
        return None
    return finding(
        "SB_SOURCE_CHECKSUM_MISMATCH",
        "source_resource",
        "fixture checksum differs from immutable source registration",
        {"expected_sha256": expected_hash, "actual_sha256": actual, "path": str(path)},
    )
