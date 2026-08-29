from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

NORMALIZER_VERSION = "statsbomb-normalizer-v1"
EVENT_SCHEMA_VERSION = "v1"
EVENT_SCHEMA_SHA256 = "25869371ba35ed08bafc15c566533153661afacaf9727cc4055cc768482f2f18"

_EVENT_CLOCK = re.compile(r"^([0-9]+):([0-5][0-9]):([0-5][0-9](?:\.[0-9]+)?)$")
_KNOWN_EVENT_TYPES = {
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


class EventNormalizationError(ValueError):
    """StatsBomb event payload cannot satisfy the normalized event contract."""


@dataclass(frozen=True)
class CanonicalEventReference:
    canonical_event_id: UUID
    canonical_match_id: UUID
    provider_event_id: str
    event_index: int
    provider_event_type: str
    period: int
    event_clock: timedelta
    canonical_team_id: UUID | None
    canonical_player_id: UUID | None


def normalize_statsbomb_events(
    payload: bytes,
    provider_match_id: str,
    references: Mapping[str, CanonicalEventReference],
    team_mappings: Mapping[str, UUID],
    player_mappings: Mapping[str, UUID],
) -> tuple[dict[str, Any], ...]:
    _provider_identifier(provider_match_id, "provider match ID")
    events = _json_array(payload)
    parsed = [_event_object(value, index) for index, value in enumerate(events)]
    provider_event_ids = [_uuid_string(event, "id") for event in parsed]
    _require_unique(provider_event_ids, "event identifiers")
    indexes = [_bounded_positive_int(event, "index", 2**31 - 1) for event in parsed]
    _require_unique(indexes, "event indexes")
    if set(provider_event_ids) != set(references):
        raise EventNormalizationError("event payload does not match canonical event catalogue")
    ordered = sorted(parsed, key=lambda event: _bounded_positive_int(event, "index", 2**31 - 1))
    return tuple(
        _normalize_event(
            event,
            provider_match_id,
            references,
            team_mappings,
            player_mappings,
        )
        for event in ordered
    )


def logical_sha256(rows: tuple[dict[str, Any], ...]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical_json_bytes(row))
        digest.update(b"\n")
    return digest.hexdigest()


def _normalize_event(
    event: dict[str, object],
    provider_match_id: str,
    references: Mapping[str, CanonicalEventReference],
    team_mappings: Mapping[str, UUID],
    player_mappings: Mapping[str, UUID],
) -> dict[str, Any]:
    provider_event_id = _uuid_string(event, "id")
    reference = references[provider_event_id]
    event_index = _bounded_positive_int(event, "index", 2**31 - 1)
    period = _bounded_positive_int(event, "period", 127)
    timestamp = _string(event, "timestamp")
    event_clock = _clock(timestamp)
    event_type = _object_field(event, "type")
    event_type_id = _positive_int(event_type, "id")
    event_type_name = _string(event_type, "name")
    provider_team_id = _entity_identifier(event, "team")
    provider_player_id = _entity_identifier(event, "player")
    _verify_reference(
        reference,
        event_index,
        period,
        event_clock,
        event_type_name,
        provider_team_id,
        provider_player_id,
        team_mappings,
        player_mappings,
    )
    location = _location(event)
    source_x, source_y, x_norm, y_norm, location_quality = _coordinates(location)
    return {
        "canonical_event_id": str(reference.canonical_event_id),
        "canonical_match_id": str(reference.canonical_match_id),
        "provider_event_id": provider_event_id,
        "provider_match_id": provider_match_id,
        "event_index": event_index,
        "period": period,
        "timestamp": timestamp,
        "minute": _bounded_nonnegative_int(event, "minute", 32767),
        "second": _bounded_nonnegative_int(event, "second", 59),
        "provider_event_type_id": str(event_type_id),
        "provider_event_type_name": event_type_name,
        "canonical_event_type_id": _KNOWN_EVENT_TYPES.get(event_type_id),
        "canonical_team_id": _uuid_text(reference.canonical_team_id),
        "provider_team_id": provider_team_id,
        "canonical_player_id": _uuid_text(reference.canonical_player_id),
        "provider_player_id": provider_player_id,
        "source_coordinate_system": "statsbomb_120x80" if location is not None else None,
        "source_x": source_x,
        "source_y": source_y,
        "x_norm": x_norm,
        "y_norm": y_norm,
        "location_quality": location_quality,
        "provider_payload_json": _canonical_json_bytes(event).decode("utf-8"),
    }


def _verify_reference(
    reference: CanonicalEventReference,
    event_index: int,
    period: int,
    event_clock: timedelta,
    event_type: str,
    provider_team_id: str | None,
    provider_player_id: str | None,
    team_mappings: Mapping[str, UUID],
    player_mappings: Mapping[str, UUID],
) -> None:
    if reference.event_index != event_index:
        raise EventNormalizationError("event payload conflicts with canonical event index")
    facts = (period, event_clock, event_type)
    expected = (reference.period, reference.event_clock, reference.provider_event_type)
    if facts != expected:
        raise EventNormalizationError(
            f"event {reference.provider_event_id} conflicts with canonical catalogue facts"
        )
    _verify_entity_mapping(
        reference.provider_event_id,
        "team",
        provider_team_id,
        reference.canonical_team_id,
        team_mappings,
    )
    _verify_entity_mapping(
        reference.provider_event_id,
        "player",
        provider_player_id,
        reference.canonical_player_id,
        player_mappings,
    )


def _verify_entity_mapping(
    provider_event_id: str,
    label: str,
    provider_entity_id: str | None,
    canonical_entity_id: UUID | None,
    mappings: Mapping[str, UUID],
) -> None:
    mapped = mappings.get(provider_entity_id) if provider_entity_id is not None else None
    if mapped != canonical_entity_id:
        raise EventNormalizationError(
            f"event {provider_event_id} conflicts with canonical {label} mapping"
        )


def _json_array(payload: bytes) -> list[object]:
    try:
        value = json.loads(payload, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EventNormalizationError("event resource must be valid UTF-8 JSON") from error
    if not isinstance(value, list):
        raise EventNormalizationError("event resource must contain a JSON array")
    return value


def _reject_json_constant(value: str) -> object:
    raise EventNormalizationError(f"event resource contains non-finite JSON number: {value}")


def _event_object(value: object, index: int) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EventNormalizationError(f"event resource row {index} must be an object")
    return value


def _object_field(row: dict[str, object], field: str) -> dict[str, object]:
    value = row.get(field)
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EventNormalizationError(f"event {field} must be an object")
    return value


def _string(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise EventNormalizationError(f"event {field} must be a non-empty string")
    return value


def _positive_int(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EventNormalizationError(f"event {field} must be a positive integer")
    return value


def _bounded_positive_int(row: dict[str, object], field: str, maximum: int) -> int:
    value = _positive_int(row, field)
    if value > maximum:
        raise EventNormalizationError(f"event {field} exceeds normalized schema range")
    return value


def _bounded_nonnegative_int(row: dict[str, object], field: str, maximum: int) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise EventNormalizationError(f"event {field} must be an integer between 0 and {maximum}")
    return value


def _provider_identifier(value: str, label: str) -> str:
    if not value.isascii() or not value.isdigit() or int(value) <= 0:
        raise EventNormalizationError(f"{label} must be a positive integer string")
    return value


def _uuid_string(row: dict[str, object], field: str) -> str:
    value = _string(row, field)
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise EventNormalizationError(f"event {field} must be a UUID") from error
    if str(parsed) != value:
        raise EventNormalizationError(f"event {field} must be a canonical lowercase UUID")
    return value


def _entity_identifier(row: dict[str, object], field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    entity = _object_field(row, field)
    return str(_positive_int(entity, "id"))


def _clock(value: str) -> timedelta:
    match = _EVENT_CLOCK.fullmatch(value)
    if match is None:
        raise EventNormalizationError("event timestamp must use hour:minute:second format")
    try:
        seconds = Decimal(match.group(3))
    except InvalidOperation as error:
        raise EventNormalizationError("event timestamp has invalid seconds") from error
    return timedelta(
        hours=int(match.group(1)),
        minutes=int(match.group(2)),
        seconds=float(seconds),
    )


def _location(row: dict[str, object]) -> tuple[float, float] | None:
    value = row.get("location")
    if value is None:
        return None
    if not isinstance(value, list) or len(value) < 2:
        raise EventNormalizationError("event location must contain x and y coordinates")
    coordinates: list[float] = []
    for coordinate in value[:2]:
        if isinstance(coordinate, bool) or not isinstance(coordinate, int | float):
            raise EventNormalizationError("event location coordinates must be numbers")
        number = float(coordinate)
        if not math.isfinite(number):
            raise EventNormalizationError("event location coordinates must be finite")
        coordinates.append(number)
    return coordinates[0], coordinates[1]


def _coordinates(
    location: tuple[float, float] | None,
) -> tuple[float | None, float | None, float | None, float | None, str]:
    if location is None:
        return None, None, None, None, "missing"
    source_x, source_y = location
    if not 0 <= source_x <= 120 or not 0 <= source_y <= 80:
        return source_x, source_y, None, None, "out_of_bounds"
    return source_x, source_y, source_x / 120, source_y / 80, "valid"


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise EventNormalizationError(
            "event payload cannot be encoded as canonical JSON"
        ) from error


def _uuid_text(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _require_unique(values: Sequence[object], label: str) -> None:
    if len(values) != len(set(values)):
        raise EventNormalizationError(f"event resource contains duplicate {label}")
