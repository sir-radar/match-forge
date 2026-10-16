"""Validate native record shapes without changing source values or extra fields."""

from __future__ import annotations

import math
import types
from collections.abc import Mapping
from typing import (
    Any,
    NotRequired,
    Required,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)


class NativeRecordError(ValueError):
    """A native record cannot be read as its provider's declared shape."""


def native_record[T](model: type[T], payload: object) -> T:
    """Return an independent typed copy, retaining missing/null and additive keys."""
    if not is_typeddict(model):
        raise NativeRecordError("a provider-native TypedDict is required")
    _validate_json(payload, model.__name__)
    _validate(model, payload, model.__name__)
    return cast(T, _copy_json(payload))


def _copy_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_json(item) for item in value]
    return value


def _validate_json(value: object, path: str) -> None:
    if value is None or type(value) in (str, int, bool):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise NativeRecordError(f"{path}: JSON object keys must be strings")
        for key, item in value.items():
            _validate_json(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    raise NativeRecordError(f"{path}: expected finite JSON data")


def _validate(annotation: Any, value: object, path: str) -> None:
    origin, arguments = get_origin(annotation), get_args(annotation)
    if origin in (NotRequired, Required):
        _validate(arguments[0], value, path)
    elif origin in (Union, types.UnionType):
        _validate_union(arguments, value, path)
    elif is_typeddict(annotation):
        _validate_record(annotation, value, path)
    elif origin is list:
        _validate_list(arguments[0], value, path)
    elif origin is dict:
        _validate_mapping(arguments, value, path)
    elif annotation is object:
        return
    elif not _primitive_matches(annotation, value):
        raise NativeRecordError(f"{path}: expected {getattr(annotation, '__name__', annotation)}")


def _primitive_matches(annotation: Any, value: object) -> bool:
    if annotation is type(None):
        return value is None
    if annotation is float:
        return type(value) in (int, float)
    return type(value) is annotation


def _validate_record(model: Any, value: object, path: str) -> None:
    if not isinstance(value, Mapping):
        raise NativeRecordError(f"{path}: expected an object")
    hints = get_type_hints(model, include_extras=True)
    for name, annotation in hints.items():
        origin = get_origin(annotation)
        required = origin is Required or (
            origin is not NotRequired and name in model.__required_keys__
        )
        if name not in value:
            if required:
                raise NativeRecordError(f"{path}.{name}: required native field is missing")
            continue
        _validate(annotation, value[name], f"{path}.{name}")


def _validate_list(annotation: Any, value: object, path: str) -> None:
    if not isinstance(value, list):
        raise NativeRecordError(f"{path}: expected an array")
    for index, item in enumerate(value):
        _validate(annotation, item, f"{path}[{index}]")


def _validate_mapping(annotations: tuple[Any, ...], value: object, path: str) -> None:
    if not isinstance(value, Mapping):
        raise NativeRecordError(f"{path}: expected an object")
    for key, item in value.items():
        _validate(annotations[0], key, path)
        _validate(annotations[1], item, f"{path}.{key}")


def _validate_union(annotations: tuple[Any, ...], value: object, path: str) -> None:
    for annotation in annotations:
        try:
            _validate(annotation, value, path)
        except NativeRecordError:
            continue
        return
    raise NativeRecordError(f"{path}: native value does not match any allowed type")
