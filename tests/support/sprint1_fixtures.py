from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from football.contracts import SourceResource, SourceSnapshot

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPRINT1_FIXTURE_ROOT = _REPOSITORY_ROOT / "data/fixtures/statsbomb/sprint1"

FixtureOutcome = Literal["passed", "warnings", "quarantined", "ingestion_error"]


class FixtureContractError(ValueError):
    """A committed Sprint 1 fixture violates its checksum-pinned contract."""


@dataclass(frozen=True)
class FixtureResource:
    descriptor: SourceResource
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class FixtureExpectation:
    outcome: FixtureOutcome
    canonical: dict[str, int]
    dataset_rows: int | None
    finding_counts: dict[str, int]
    error_message: str | None


@dataclass(frozen=True)
class Sprint1Fixture:
    root: Path
    name: str
    description: str
    snapshot: SourceSnapshot
    acquired_at: datetime
    resources: tuple[FixtureResource, ...]
    expected: FixtureExpectation

    @property
    def source_resources(self) -> tuple[SourceResource, ...]:
        return tuple(resource.descriptor for resource in self.resources)

    def payload(self, resource: SourceResource) -> bytes:
        expected = next(
            (
                item
                for item in self.resources
                if item.descriptor.path == resource.path
                and item.descriptor.media_type == resource.media_type
            ),
            None,
        )
        if expected is None:
            raise FixtureContractError(f"undeclared fixture resource requested: {resource.path}")
        payload = _read_payload(self.root, resource.path)
        _verify_payload(resource.path, payload, expected.size_bytes, expected.sha256)
        return payload


class FixtureProvider:
    def __init__(self, fixture: Sprint1Fixture) -> None:
        self._fixture = fixture
        self.fetches: list[str] = []

    @property
    def snapshot(self) -> SourceSnapshot:
        return self._fixture.snapshot

    def competitions(self) -> SourceResource:
        return SourceResource("data/competitions.json")

    def matches(self, *, competition_id: int, season_id: int) -> SourceResource:
        return SourceResource(f"data/matches/{competition_id}/{season_id}.json")

    def lineups(self, *, match_id: int) -> SourceResource:
        return SourceResource(f"data/lineups/{match_id}.json")

    def events(self, *, match_id: int) -> SourceResource:
        return SourceResource(f"data/events/{match_id}.json")

    def fetch(self, resource: SourceResource) -> bytes:
        payload = self._fixture.payload(resource)
        self.fetches.append(resource.path)
        return payload


def load_sprint1_fixture(name: str, *, fixture_root: Path = SPRINT1_FIXTURE_ROOT) -> Sprint1Fixture:
    safe_name_characters = "abcdefghijklmnopqrstuvwxyz0123456789-"
    if not name or any(character not in safe_name_characters for character in name):
        raise FixtureContractError("fixture name must use lowercase letters, digits, and hyphens")
    root = (fixture_root / name).resolve()
    manifest_path = root / "fixture.json"
    try:
        document = json.loads(manifest_path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FixtureContractError(f"invalid fixture manifest: {manifest_path}") from error
    if not isinstance(document, dict) or document.get("contract") != "Sprint1FixtureV1":
        raise FixtureContractError("fixture manifest must use Sprint1FixtureV1")
    manifest_name = _string(document, "name")
    if manifest_name != name or root.name != name:
        raise FixtureContractError("fixture manifest name must match its directory")

    snapshot = SourceSnapshot(
        provider=_string(document, "provider"),
        repository=_string(document, "repository"),
        source_git_sha=_string(document, "source_git_sha"),
        license=_string(document, "license"),
        license_url=_string(document, "license_url"),
        attribution=_string(document, "attribution"),
    )
    acquired_at = _datetime(document, "acquired_at")
    resources = _resources(document, root)
    expected = _expectation(document)
    return Sprint1Fixture(
        root=root,
        name=name,
        description=_string(document, "description"),
        snapshot=snapshot,
        acquired_at=acquired_at,
        resources=resources,
        expected=expected,
    )


def _resources(document: dict[str, object], root: Path) -> tuple[FixtureResource, ...]:
    raw_resources = document.get("resources")
    if not isinstance(raw_resources, list) or not raw_resources:
        raise FixtureContractError("fixture resources must be a non-empty array")
    resources: list[FixtureResource] = []
    for raw_resource in raw_resources:
        if not isinstance(raw_resource, dict):
            raise FixtureContractError("fixture resource must be an object")
        descriptor = SourceResource(
            path=_string(raw_resource, "path"),
            media_type=_string(raw_resource, "media_type"),
        )
        size_bytes = _integer(raw_resource, "size_bytes")
        sha256 = _string(raw_resource, "sha256")
        resource = FixtureResource(descriptor, size_bytes, sha256)
        _verify_payload(descriptor.path, _read_payload(root, descriptor.path), size_bytes, sha256)
        resources.append(resource)

    paths = [resource.descriptor.path for resource in resources]
    if len(paths) != len(set(paths)):
        raise FixtureContractError("fixture resource paths must be unique")
    if paths != sorted(paths):
        raise FixtureContractError("fixture resource paths must be sorted")
    data_root = root / "data"
    if data_root.is_symlink() or any(path.is_symlink() for path in data_root.rglob("*")):
        raise FixtureContractError("fixture data must not contain symbolic links")
    actual_paths = {
        path.relative_to(root).as_posix() for path in data_root.rglob("*") if path.is_file()
    }
    if set(paths) != actual_paths:
        raise FixtureContractError("fixture manifest must declare every data file exactly once")
    return tuple(resources)


def _expectation(document: dict[str, object]) -> FixtureExpectation:
    raw_expected = document.get("expected")
    if not isinstance(raw_expected, dict):
        raise FixtureContractError("fixture expected result must be an object")
    outcome = _string(raw_expected, "outcome")
    if outcome not in {"passed", "warnings", "quarantined", "ingestion_error"}:
        raise FixtureContractError("fixture outcome is unsupported")
    canonical = _integer_map(raw_expected, "canonical", allow_zero=True)
    finding_counts = _integer_map(raw_expected, "finding_counts", allow_zero=False)
    dataset_rows = raw_expected.get("dataset_rows")
    if dataset_rows is not None and (
        not isinstance(dataset_rows, int) or isinstance(dataset_rows, bool) or dataset_rows < 0
    ):
        raise FixtureContractError("fixture dataset_rows must be null or a non-negative integer")
    error_message = raw_expected.get("error_message")
    if error_message is not None and (not isinstance(error_message, str) or not error_message):
        raise FixtureContractError("fixture error_message must be a non-empty string")
    if outcome == "ingestion_error":
        if error_message is None or canonical or dataset_rows is not None or finding_counts:
            raise FixtureContractError("ingestion error fixture has invalid expected results")
    elif error_message is not None or dataset_rows is None:
        raise FixtureContractError("successful ingestion fixture has invalid expected results")
    return FixtureExpectation(
        outcome=cast(FixtureOutcome, outcome),
        canonical=canonical,
        dataset_rows=dataset_rows,
        finding_counts=finding_counts,
        error_message=error_message,
    )


def _verify_payload(path: str, payload: bytes, size_bytes: int, sha256: str) -> None:
    if len(payload) != size_bytes:
        raise FixtureContractError(f"fixture resource size mismatch: {path}")
    if hashlib.sha256(payload).hexdigest() != sha256:
        raise FixtureContractError(f"fixture resource checksum mismatch: {path}")


def _read_payload(root: Path, relative_path: str) -> bytes:
    try:
        return (root / relative_path).read_bytes()
    except OSError as error:
        raise FixtureContractError(f"fixture resource cannot be read: {relative_path}") from error


def _string(document: dict[str, object], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise FixtureContractError(f"fixture {field} must be a non-empty string")
    return value


def _integer(document: dict[str, object], field: str) -> int:
    value = document.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise FixtureContractError(f"fixture {field} must be a positive integer")
    return value


def _integer_map(document: dict[str, object], field: str, *, allow_zero: bool) -> dict[str, int]:
    value = document.get(field)
    if not isinstance(value, dict):
        raise FixtureContractError(f"fixture {field} must be an object")
    minimum = 0 if allow_zero else 1
    if any(
        not isinstance(key, str)
        or not isinstance(item, int)
        or isinstance(item, bool)
        or item < minimum
        for key, item in value.items()
    ):
        raise FixtureContractError(f"fixture {field} contains an invalid count")
    return cast(dict[str, int], value)


def _datetime(document: dict[str, object], field: str) -> datetime:
    value = _string(document, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FixtureContractError(f"fixture {field} must be an ISO 8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise FixtureContractError(f"fixture {field} must include a timezone")
    return parsed
