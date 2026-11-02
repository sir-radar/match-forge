"""Strict wire encoding and semantic checks shared by resource observations."""

from __future__ import annotations

import json
import types
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from functools import cache, lru_cache
from typing import Annotated, Any, Union, cast, get_args, get_origin, get_type_hints
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from football.contracts.observation_schema import observation_schema, observation_types
from football.contracts.observations import (
    ExpectedGoalsObservationV1,
    FixtureObservationV1,
    LineupObservationV1,
    Observation,
    ObservationError,
    PlayerStatisticObservationV1,
    ResultObservationV1,
    ShotObservationV1,
    TeamStatisticObservationV1,
)
from football.contracts.observations_v2 import EntityReferenceV2
from football.contracts.observations_v3 import (
    ObservationVersionsV3,
    PeriodScoreObservationV3,
    PlayerStatisticObservationV3,
    RefereeObservationV3,
    ShotObservationV3,
    TeamRatingObservationV3,
    TeamStatisticObservationV3,
)


def _encode(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ObservationError("observation timestamps require a timezone")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value):
        return {item.name: _encode(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


def observation_payload(value: Observation) -> dict[str, object]:
    return {"contract": value.CONTRACT, **_encode(value)}


def observation_bytes(value: Observation) -> bytes:
    try:
        return (
            json.dumps(
                observation_payload(value),
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode()
    except ObservationError:
        raise
    except (ValueError, TypeError) as error:
        raise ObservationError("observation must contain finite JSON values") from error


@cache
def _validator(version: str, contract: str) -> Draft202012Validator:
    # The caller resolves a declared model first, so this cache has a finite key set.
    # Distinct contract constants make every other union branch impossible.
    schema = {
        **observation_schema(version),
        "oneOf": [{"$ref": f"#/$defs/{contract}"}],
    }
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_payload(payload: object) -> None:
    model = _observation_model(payload)
    try:
        _validator(model.VERSIONS_TYPE.VERSION, model.CONTRACT).validate(payload)
    except ValidationError as error:
        raise ObservationError(f"invalid resource observation: {error.message}") from error


@lru_cache(maxsize=1)
def _models() -> dict[str, type[Observation]]:
    return {
        model.CONTRACT: model for version in ("1", "2", "3") for model in observation_types(version)
    }


def _observation_model(payload: object) -> type[Observation]:
    if isinstance(payload, dict) and isinstance(payload.get("contract"), str):
        model = _models().get(payload["contract"])
        if model is not None:
            return model
    raise ObservationError("unknown resource observation contract")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ObservationError(f"duplicate observation field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ObservationError(f"non-finite observation value: {value}")


def _decode(annotation: Any, value: Any) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if value is None:
        return None
    if origin is Annotated:
        return _decode(args[0], value)
    if origin in (Union, types.UnionType):
        return _decode(next(arg for arg in args if arg is not type(None)), value)
    if origin is tuple:
        return tuple(_decode(args[0], item) for item in value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        hints = get_type_hints(annotation, include_extras=True)
        if issubclass(annotation, Observation):
            hints["versions"] = annotation.VERSIONS_TYPE
        return annotation(
            **{
                item.name: _decode(hints[item.name], value[item.name])
                for item in fields(annotation)
                if item.name in value
            }
        )
    parsers: dict[Any, Callable[[Any], Any]] = {
        UUID: UUID,
        datetime: datetime.fromisoformat,
        date: date.fromisoformat,
        float: float,
        int: int,
    }
    return parsers[annotation](value) if annotation in parsers else value


def decode_observation(payload: bytes) -> Observation:
    try:
        value = json.loads(
            payload, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise ObservationError("observation must be valid finite UTF-8 JSON") from error
    _validate_payload(value)
    return cast(Observation, _decode(_observation_model(value), value))


def validate_observation(item: Observation) -> None:
    _validate_payload(json.loads(observation_bytes(item)))
    _validate_time(item)
    if item.provenance.provider_native_id is None and item.provenance.source_record_key is None:
        raise ObservationError("a native ID or source-record locator is required")
    if isinstance(item, FixtureObservationV1):
        home, away = item.home_team, item.away_team
        if (
            home.provider_native_id is not None
            and home.provider_native_id == away.provider_native_id
        ):
            raise ObservationError("fixture participants must be distinct")
        if home.canonical_id is not None and home.canonical_id == away.canonical_id:
            raise ObservationError("fixture canonical participants must be distinct")
        if (
            isinstance(home, EntityReferenceV2)
            and isinstance(away, EntityReferenceV2)
            and home.source_record_key is not None
            and home.source_record_key == away.source_record_key
        ):
            raise ObservationError("fixture participants must reference distinct source fields")
    _validate_resource(item)


def _validate_time(item: Observation) -> None:
    time = item.time
    if time.known_at < time.acquired_at or time.known_at < time.observed_at:
        raise ObservationError("known_at cannot precede acquisition or observation")
    if time.valid_to is not None and (time.valid_from is None or time.valid_to <= time.valid_from):
        raise ObservationError("observation validity interval is empty or reversed")


def _validate_resource(item: Observation) -> None:
    if isinstance(item, ResultObservationV1):
        if (item.home_goals is None) != (item.away_goals is None):
            raise ObservationError("observed scores require both sides")
        if item.status == "FINISHED" and item.home_goals is None:
            raise ObservationError("a finished result requires scores")
    if isinstance(item, ShotObservationV1) and (item.x_norm is None) != (item.y_norm is None):
        raise ObservationError("shot coordinates require both axes")
    if (
        isinstance(item, ExpectedGoalsObservationV1)
        and item.scope == "SHOT"
        and (item.shot is None or item.expected_goals > 1)
    ):
        raise ObservationError("shot xG requires a shot reference and a probability")
    if isinstance(item, LineupObservationV1):
        _validate_lineup(item)
    if isinstance(item, TeamStatisticObservationV1 | PlayerStatisticObservationV1):
        _validate_statistics(item)
    _validate_v3_resource(item)


def _validate_v3_resource(item: Observation) -> None:
    versions = item.versions
    if (
        isinstance(versions, ObservationVersionsV3)
        and versions.semantic_version is not None
        and not versions.semantic_version.strip()
    ):
        raise ObservationError("semantic_version must be nonblank or unknown")
    if isinstance(item, TeamStatisticObservationV3 | PlayerStatisticObservationV3):
        _validate_rich_counts(item)
    if isinstance(item, ShotObservationV3) and (
        (item.home_goals_before_shot is None) != (item.away_goals_before_shot is None)
    ):
        raise ObservationError("shot score context requires both sides")
    if isinstance(item, PeriodScoreObservationV3):
        required = "EXTRA_TIME" if item.period == "EXTRA_TIME" else "REGULATION_90"
        if item.score_basis not in {required, "UNKNOWN"}:
            raise ObservationError("period and score basis are incompatible")
    if isinstance(item, RefereeObservationV3):
        _validate_referee(item)
    if isinstance(item, TeamRatingObservationV3) and not item.rating_system.strip():
        raise ObservationError("rating_system must be nonblank")


def _validate_rich_counts(item: TeamStatisticObservationV3 | PlayerStatisticObservationV3) -> None:
    total = "total_shots" if isinstance(item, TeamStatisticObservationV3) else "shots"
    pairs = [("shots_on_target", total), ("accurate_passes", "passes")]
    if isinstance(item, TeamStatisticObservationV3):
        pairs.extend((("shots_off_target", total), ("blocked_shots", total)))
    for part, whole in pairs:
        part_value, whole_value = getattr(item, part), getattr(item, whole)
        if part_value is not None and whole_value is not None and part_value > whole_value:
            raise ObservationError(f"{part} cannot exceed {whole}")


def _validate_referee(item: RefereeObservationV3) -> None:
    if item.name is not None and not item.name.strip():
        raise ObservationError("referee name must be nonblank or unknown")
    if (
        item.name is None
        and item.referee.provider_native_id is None
        and item.referee.canonical_id is None
    ):
        raise ObservationError("referee observation requires an observed identifier or name")


def _validate_lineup(item: LineupObservationV1) -> None:
    native = [
        member.player.provider_native_id
        for member in item.players
        if member.player.provider_native_id is not None
    ]
    canonical = [
        member.player.canonical_id
        for member in item.players
        if member.player.canonical_id is not None
    ]
    source_fields = [
        member.player.source_record_key
        for member in item.players
        if isinstance(member.player, EntityReferenceV2)
        and member.player.source_record_key is not None
    ]
    if not item.players or len(native) != len(set(native)) or len(canonical) != len(set(canonical)):
        raise ObservationError("lineup requires players with no duplicate identities")
    if len(source_fields) != len(set(source_fields)):
        raise ObservationError("lineup contains duplicate source fields")


def _validate_statistics(item: TeamStatisticObservationV1 | PlayerStatisticObservationV1) -> None:
    identifiers = {"provenance", "time", "versions", "fixture", "team", "player", "period"}
    if all(
        getattr(item, field.name) is None for field in fields(item) if field.name not in identifiers
    ):
        raise ObservationError("a statistic observation requires an observed measurement")
