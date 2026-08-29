from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier

import pytest
from football.contracts.source import SourceResource, SourceSnapshot
from football.ingestion import SourceAcquirer, SourceIntegrityError
from football.storage import ImmutableRawStore, RawResourceConflict
from jsonschema import validate as validate_json

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_MANIFEST_SCHEMA = PROJECT_ROOT / "schemas" / "contracts" / "source-manifest-v1.schema.json"


@dataclass
class FakeProvider:
    payloads: dict[str, bytes]
    snapshot: SourceSnapshot = SourceSnapshot(
        provider="statsbomb_open_data",
        repository="https://github.com/statsbomb/open-data",
        source_git_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec",
        license="StatsBomb Open Data license",
        license_url=(
            "https://github.com/statsbomb/open-data/blob/"
            "b0bc9f22dd77c206ddedc1d742893b3bbe64baec/LICENSE.pdf"
        ),
        attribution="Data provided by StatsBomb",
    )
    fetches: list[str] = field(default_factory=list)

    def fetch(self, resource: SourceResource) -> bytes:
        self.fetches.append(resource.path)
        return self.payloads[resource.path]


def fixed_clock() -> datetime:
    return datetime(2026, 8, 29, 8, 0, tzinfo=UTC)


def test_acquisition_preserves_exact_bytes_and_writes_valid_manifest(tmp_path: Path) -> None:
    provider = FakeProvider(
        {
            "data/competitions.json": b'[ {"competition_id": 43} ]\n',
            "data/matches/43/106.json": b"[]\n",
        }
    )
    resources = (
        SourceResource("data/matches/43/106.json"),
        SourceResource("data/competitions.json"),
    )

    result = SourceAcquirer(tmp_path, clock=fixed_clock).acquire(provider, resources)

    assert provider.fetches == ["data/competitions.json", "data/matches/43/106.json"]
    assert result.statuses == {
        "data/competitions.json": "acquired",
        "data/matches/43/106.json": "acquired",
    }
    raw_competitions = tmp_path / result.manifest.resources[0].raw_path
    assert raw_competitions.read_bytes() == b'[ {"competition_id": 43} ]\n'
    manifest_payload = json.loads(result.manifest_path.read_bytes())
    validate_json(manifest_payload, json.loads(SOURCE_MANIFEST_SCHEMA.read_bytes()))
    assert manifest_payload["acquired_at"] == "2026-08-29T08:00:00Z"
    assert [item["path"] for item in manifest_payload["resources"]] == [
        "data/competitions.json",
        "data/matches/43/106.json",
    ]
    assert all(item["media_type"] == "application/json" for item in manifest_payload["resources"])


def test_identical_rerun_uses_manifest_and_raw_bytes_without_network(tmp_path: Path) -> None:
    resource = SourceResource("data/competitions.json")
    first_provider = FakeProvider({resource.path: b"[]\n"})
    acquirer = SourceAcquirer(tmp_path, clock=fixed_clock)
    first = acquirer.acquire(first_provider, (resource,))
    raw_path = tmp_path / first.manifest.resources[0].raw_path
    original_mtime = raw_path.stat().st_mtime_ns

    offline_provider = FakeProvider({})
    second = acquirer.acquire(offline_provider, (resource,))

    assert offline_provider.fetches == []
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.manifest_path == first.manifest_path
    assert second.statuses == {resource.path: "verified_existing"}
    assert raw_path.stat().st_mtime_ns == original_mtime


def test_existing_raw_resource_without_manifest_is_verified_against_provider(
    tmp_path: Path,
) -> None:
    resource = SourceResource("data/competitions.json")
    provider = FakeProvider({resource.path: b"upstream"})
    store = ImmutableRawStore(tmp_path)
    store.publish(provider.snapshot, resource, b"local")

    with pytest.raises(RawResourceConflict, match="immutable raw resource conflict") as raised:
        SourceAcquirer(tmp_path, clock=fixed_clock).acquire(provider, (resource,))

    assert raised.value.code == "SB_SOURCE_CHECKSUM_MISMATCH"
    assert provider.fetches == [resource.path]
    assert store.path_for(provider.snapshot, resource).read_bytes() == b"local"


def test_manifest_detects_external_raw_corruption_without_refetching(tmp_path: Path) -> None:
    resource = SourceResource("data/competitions.json")
    provider = FakeProvider({resource.path: b"[]\n"})
    acquirer = SourceAcquirer(tmp_path, clock=fixed_clock)
    first = acquirer.acquire(provider, (resource,))
    (tmp_path / first.manifest.resources[0].raw_path).write_bytes(b"corrupt")
    retry_provider = FakeProvider({resource.path: b"[]\n"})

    with pytest.raises(SourceIntegrityError, match="checksum mismatch") as raised:
        acquirer.acquire(retry_provider, (resource,))

    assert raised.value.code == "SB_SOURCE_CHECKSUM_MISMATCH"
    assert retry_provider.fetches == []


def test_acquisition_rejects_tampered_manifest_before_provider_access(tmp_path: Path) -> None:
    resource = SourceResource("data/competitions.json")
    provider = FakeProvider({resource.path: b"[]\n"})
    acquirer = SourceAcquirer(tmp_path, clock=fixed_clock)
    first = acquirer.acquire(provider, (resource,))
    payload = json.loads(first.manifest_path.read_bytes())
    payload["unexpected"] = True
    first.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    retry_provider = FakeProvider({resource.path: b"[]\n"})

    with pytest.raises(SourceIntegrityError, match="invalid immutable source manifest") as raised:
        acquirer.acquire(retry_provider, (resource,))

    assert raised.value.code == "SOURCE_MANIFEST_INVALID"
    assert retry_provider.fetches == []


def test_missing_raw_resource_is_recovered_only_when_bytes_match_manifest(
    tmp_path: Path,
) -> None:
    resource = SourceResource("data/competitions.json")
    acquirer = SourceAcquirer(tmp_path, clock=fixed_clock)
    first_provider = FakeProvider({resource.path: b"[]\n"})
    first = acquirer.acquire(first_provider, (resource,))
    raw_path = tmp_path / first.manifest.resources[0].raw_path
    raw_path.unlink()

    recovery_provider = FakeProvider({resource.path: b"[]\n"})
    recovered = acquirer.acquire(recovery_provider, (resource,))

    assert recovery_provider.fetches == [resource.path]
    assert recovered.statuses == {resource.path: "acquired"}
    assert recovered.manifest_sha256 == first.manifest_sha256
    assert raw_path.read_bytes() == b"[]\n"

    raw_path.unlink()
    changed_provider = FakeProvider({resource.path: b"[1]\n"})
    with pytest.raises(SourceIntegrityError, match="recovery checksum mismatch"):
        acquirer.acquire(changed_provider, (resource,))
    assert not raw_path.exists()


def test_partial_acquisition_is_resumable_without_overwriting_preserved_bytes(
    tmp_path: Path,
) -> None:
    first = SourceResource("data/competitions.json")
    second = SourceResource("data/matches/43/106.json")

    class InterruptedProvider(FakeProvider):
        def fetch(self, resource: SourceResource) -> bytes:
            if resource == second:
                raise OSError("simulated provider outage")
            return super().fetch(resource)

    interrupted = InterruptedProvider({first.path: b"competitions"})
    acquirer = SourceAcquirer(tmp_path, clock=fixed_clock)
    with pytest.raises(OSError, match="simulated provider outage"):
        acquirer.acquire(interrupted, (first, second))

    first_path = ImmutableRawStore(tmp_path).path_for(interrupted.snapshot, first)
    first_mtime = first_path.stat().st_mtime_ns
    retry = FakeProvider({first.path: b"competitions", second.path: b"matches"})
    result = acquirer.acquire(retry, (first, second))

    assert result.statuses == {first.path: "verified_existing", second.path: "acquired"}
    assert first_path.read_bytes() == b"competitions"
    assert first_path.stat().st_mtime_ns == first_mtime


def test_acquisition_rejects_duplicate_scope_and_naive_clock(tmp_path: Path) -> None:
    resource = SourceResource("data/competitions.json")
    provider = FakeProvider({resource.path: b"[]"})

    with pytest.raises(ValueError, match="paths must be unique"):
        SourceAcquirer(tmp_path, clock=fixed_clock).acquire(provider, (resource, resource))

    with pytest.raises(ValueError, match="clock must return a timezone-aware datetime"):
        SourceAcquirer(tmp_path, clock=lambda: datetime(2026, 8, 29)).acquire(
            provider,
            (resource,),
        )


def test_concurrent_acquisition_publishes_one_raw_file_and_one_manifest(
    tmp_path: Path,
) -> None:
    resource = SourceResource("data/competitions.json")
    barrier = Barrier(2)

    class ConcurrentProvider(FakeProvider):
        def fetch(self, resource: SourceResource) -> bytes:
            barrier.wait(timeout=5)
            return super().fetch(resource)

    providers = [
        ConcurrentProvider({resource.path: b"[]\n"}),
        ConcurrentProvider({resource.path: b"[]\n"}),
    ]
    clocks = [
        lambda: datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        lambda: datetime(2026, 8, 29, 8, 1, tzinfo=UTC),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(SourceAcquirer(tmp_path, clock=clock).acquire, provider, (resource,))
            for provider, clock in zip(providers, clocks, strict=True)
        ]
        results = [future.result(timeout=10) for future in futures]

    assert len({result.manifest_sha256 for result in results}) == 1
    assert len(list(tmp_path.glob("raw/**/competitions.json"))) == 1
    assert len(list(tmp_path.glob("manifests/**/source-manifest-v1.json"))) == 1
    assert not list(tmp_path.rglob(".staging-*"))


@pytest.mark.parametrize(
    "path",
    ["../escape.json", "/absolute.json", "a/../../b.json", "a\\b", "a\nb", "a\x00b"],
)
def test_raw_resource_paths_reject_traversal(path: str, tmp_path: Path) -> None:
    provider = FakeProvider({})

    with pytest.raises(ValueError, match="relative POSIX path"):
        ImmutableRawStore(tmp_path).path_for(provider.snapshot, SourceResource(path))
