"""Normalize one registered retained resource into shadow observation artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection

from football.contracts.observations import ObservationProvenance, ObservationTime
from football.contracts.source import SourceManifest, SourceResource, canonical_json_bytes
from football.ingestion.registration import MAX_SOURCE_MANIFEST_BYTES, MAX_SOURCE_RESOURCE_BYTES
from football.observations.storage import ObservationArtifactStore
from football.product.identity_admission import _retained_payload
from football.providers.football_data_uk_evidence import FootballDataUkAcquisitionEvidenceV1
from football.providers.football_data_uk_storage import FootballDataUkRawStoreV1
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.storage.experimental import experimental_connection
from football.storage.raw import ImmutableFileStore, ImmutableRawStore
from football.work.contracts import RetryPolicy, WorkRequest, WorkState, WorkType
from football.work.storage import WorkRegistry


def registered_resource(
    connection: Connection[Any], root: Path, resource_id: UUID, **scope: str | None
) -> tuple[NormalizationContext, bytes]:
    row = connection.execute(
        """SELECT s.manifest_path,s.manifest_sha256,s.source_identity,s.source_revision,
           s.id,r.id,r.provider_path,r.sha256,r.size_bytes,p.code,r.acquired_at,s.acquired_at,s.git_sha
           FROM football.source_resources r
           JOIN football.source_snapshots s ON s.id=r.source_snapshot_id
           JOIN football.providers p ON p.id=s.provider_id WHERE r.id=%s""",
        (resource_id,),
    ).fetchone()
    if row is None:
        raise ValueError("source resource is not registered")
    # The legacy reader's fifth value is the pinned Git SHA used in file paths.
    # Keep the snapshot UUID at row[4] for observation provenance.
    legacy_row = (*row[:4], row[12], *row[5:9])
    raw: bytes | None
    if row[9] == "statsbomb_open_data":
        raw = _statsbomb_payload(root, row[:9])
    elif (row[9], row[2]) == (
        "football_data_uk",
        "football_data_uk/phase1b/frozen-resource-bundle",
    ):
        raw = _frozen_csv_payload(root, row)
    else:
        raw = _retained_payload(root, row[9], legacy_row)
    if raw is None:
        raise ValueError("source bytes are missing or fail registered checksum verification")
    context = NormalizationContext(
        provenance=ObservationProvenance(row[9], None, row[4], row[5], row[7]),
        time=ObservationTime(
            observed_at=row[11], acquired_at=row[10], known_at=max(row[10], row[11])
        ),
        resource_key=row[6],
        fixture_native_id=scope.get("fixture_native_id"),
        competition_native_id=scope.get("competition_native_id"),
        season_label=scope.get("season_label"),
    )
    return context, raw


def _frozen_csv_payload(root: Path, row: tuple[Any, ...]) -> bytes:
    files = ImmutableFileStore(root)
    manifest_raw = _read_source(files.path_for(row[0]), MAX_SOURCE_MANIFEST_BYTES)
    evidence = FootballDataUkAcquisitionEvidenceV1.from_bytes(manifest_raw)
    if (evidence.sha256, evidence.sha256) != (row[1], row[3]):
        raise ValueError("registered acquisition evidence checksum mismatch")
    matches = [receipt for receipt in evidence.receipts if receipt.source_path == row[6]]
    if len(matches) != 1:
        raise ValueError("registered resource is absent from acquisition evidence")
    receipt = matches[0]
    if (receipt.raw_sha256, receipt.raw_byte_size, receipt.observed_by_matchforge_at) != (
        row[7],
        row[8],
        row[10],
    ):
        raise ValueError("source receipt differs from its registered resource")
    if max(item.observed_by_matchforge_at for item in evidence.receipts) != row[11]:
        raise ValueError("source receipt clocks differ from the registered snapshot")
    raw = _read_source(
        files.path_for(FootballDataUkRawStoreV1.relative_path(receipt)), MAX_SOURCE_RESOURCE_BYTES
    )
    if hashlib.sha256(raw).hexdigest() != receipt.raw_sha256 or len(raw) != receipt.raw_byte_size:
        raise ValueError("registered source resource checksum mismatch")
    return raw


def _statsbomb_payload(root: Path, row: tuple[Any, ...]) -> bytes:
    files = ImmutableFileStore(root)
    path = files.path_for(row[0])
    manifest_raw = _read_source(path, MAX_SOURCE_MANIFEST_BYTES)
    if hashlib.sha256(manifest_raw).hexdigest() != row[1]:
        raise ValueError("registered source manifest checksum mismatch")
    manifest = SourceManifest.from_bytes(manifest_raw)
    if (manifest.snapshot.provider, manifest.snapshot.source_git_sha) != (
        "statsbomb_open_data",
        row[3],
    ):
        raise ValueError("source manifest differs from the registered snapshot")
    matches = [resource for resource in manifest.resources if resource.path == row[6]]
    if len(matches) != 1 or (matches[0].sha256, matches[0].size_bytes) != (row[7], row[8]):
        raise ValueError("source manifest resource differs from its registration")
    resource = matches[0]
    expected_path = ImmutableRawStore(root).relative_path(
        manifest.snapshot, SourceResource(resource.path, resource.media_type)
    )
    if resource.raw_path != expected_path:
        raise ValueError("source manifest raw path differs from the pinned storage layout")
    raw = _read_source(files.path_for(resource.raw_path), MAX_SOURCE_RESOURCE_BYTES)
    if hashlib.sha256(raw).hexdigest() != resource.sha256 or len(raw) != resource.size_bytes:
        raise ValueError("registered source resource checksum mismatch")
    return raw


def _read_source(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("registered source is missing or is not a regular file")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("source exceeds the existing acquisition byte limit")
    return raw


def report_bytes(
    context: NormalizationContext, resource: str, result: NormalizationResult
) -> bytes:
    report = {
        "provider": context.provenance.provider,
        "source_snapshot_id": str(context.provenance.source_snapshot_id),
        "source_resource_id": str(context.provenance.source_resource_id),
        "source_sha256": context.provenance.source_sha256,
        "resource_key": context.resource_key,
        "resource_type": resource,
        "scope": {
            "fixture_native_id": context.fixture_native_id,
            "competition_native_id": context.competition_native_id,
            "season_label": context.season_label,
        },
        "records_seen": result.records_seen,
        "observations": [
            {
                "observation_id": str(o.observation_id),
                "contract": o.CONTRACT,
                "sha256": o.sha256,
                "versions": asdict(o.versions),
            }
            for o in result.observations
        ],
        "findings": [
            {**asdict(f), "source_resource_id": str(f.source_resource_id)} for f in result.findings
        ],
    }
    return canonical_json_bytes(report) + b"\n"


def persist_normalization(
    connection: Connection[Any],
    artifact_root: Path,
    context: NormalizationContext,
    resource: str,
    result: NormalizationResult,
    *,
    worker: str,
    lease: timedelta,
    retry_policy: RetryPolicy,
    max_attempts: int,
) -> UUID:
    """Publish one retained feature scope through the existing fenced work owner.

    The report binds exact source, native fixture/competition/season scope,
    processing versions, observations and findings. Changed results create new
    work; identical retries reuse succeeded work without changing source clocks.
    """
    digest = hashlib.sha256(report_bytes(context, resource, result)).hexdigest()
    store = ObservationArtifactStore(connection, artifact_root)
    prepared = tuple(store.prepare(observation) for observation in result.observations)
    registry = WorkRegistry(connection)
    work_id = registry.enqueue(
        WorkRequest(
            work_type=WorkType.NORMALIZATION,
            semantic_key=f"normalization:{digest}",
            input_hash=digest,
            priority=0,
            available_at=context.time.known_at,
            max_attempts=max_attempts,
            retry_policy=retry_policy,
        )
    )
    if registry.state(work_id) == WorkState.SUCCEEDED:
        return work_id
    claim = registry.claim(worker, lease, (WorkType.NORMALIZATION,), work_ids=(work_id,))
    if claim is None:
        raise ValueError(f"normalization work is not claimable: {work_id}")
    with registry.publication(claim, result_hash=digest):
        for item in prepared:
            store.register_prepared(item)
    return work_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-resource-id", type=UUID, required=True)
    parser.add_argument("--resource", required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--fixture-native-id")
    parser.add_argument("--competition-native-id")
    parser.add_argument("--season-label")
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--database-url")
    parser.add_argument("--operating-database-url")
    args = parser.parse_args(argv)
    if args.persist and (not args.database_url or not args.operating_database_url):
        parser.error("--persist requires explicit --database-url and --operating-database-url")
    selected = (
        experimental_connection(args.database_url, args.operating_database_url)
        if args.persist
        else psycopg.connect(
            args.database_url or os.environ["DATABASE_URL"],
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )
    )
    with selected as connection:
        context, raw = registered_resource(
            connection,
            args.data_root,
            args.source_resource_id,
            fixture_native_id=args.fixture_native_id,
            competition_native_id=args.competition_native_id,
            season_label=args.season_label,
        )
        result = normalize_resource(context, args.resource, raw)
        report = report_bytes(context, args.resource, result)
        digest = hashlib.sha256(report).hexdigest()
        written = ImmutableFileStore(args.artifact_root).publish(
            f"reports/normalization/{digest}.json", report
        )
        if args.persist:
            persist_normalization(
                connection,
                args.artifact_root,
                context,
                args.resource,
                result,
                worker="retained-resource-normalization",
                lease=timedelta(minutes=5),
                retry_policy=RetryPolicy(timedelta(seconds=60), timedelta(hours=1), 2),
                max_attempts=3,
            )
    print(
        json.dumps(
            {
                "report": str(written.path),
                "report_sha256": digest,
                "observations": len(result.observations),
                "findings": len(result.findings),
                "persisted": args.persist,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
