from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
from football.observations.storage import ObservationArtifactStore
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.pipeline import normalize_resource
from football.temporal.repository import PointInTimeRepository
from football.work.contracts import RetryPolicy, WorkRequest, WorkState, WorkType
from football.work.storage import WorkRegistry


def test_understat_manifest_normalization_fenced_publication_and_retry(tmp_path: Path) -> None:
    raw = gzip.compress(
        json.dumps(
            {
                "dates": [
                    {
                        "id": "26602",
                        "isResult": True,
                        "h": {"id": "89", "title": "Home"},
                        "a": {"id": "228", "title": "Away"},
                        "goals": {"h": "1", "a": "0"},
                        "xG": {"h": "0.5", "a": "0.25"},
                        "datetime": "2024-08-16 19:00:00",
                    }
                ]
            }
        ).encode(),
        mtime=0,
    )
    digest = hashlib.sha256(raw).hexdigest()
    now = datetime(2026, 11, 1, tzinfo=UTC)
    identity = "https://understat.com/getLeagueData/EPL/2024"
    path = "getLeagueData/EPL/2024"
    manifest = publish_manifest(
        tmp_path,
        provider="understat",
        source_identity=identity,
        source_revision=digest,
        acquired_at=now,
        resources=[(path, f"understat/raw/{digest}", raw)],
    )
    # The storage harness owns this disposable DB; control calls require idle connections.
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as c:
        owner = HistoricalBackfillStore(
            c, "understat", "Understat", "understat-results-v1", data_root=tmp_path
        )
        snapshot = owner.ensure_snapshot(
            source_identity=identity,
            source_revision=digest,
            acquired_at=now,
            manifest_path=manifest,
        )
        resource = owner.record_resource(
            snapshot_id=snapshot,
            provider_path=path,
            payload=raw,
            media_type="text/javascript",
            acquired_at=now,
            import_pending=True,
        )
        context, retained = registered_resource(c, tmp_path, resource)
        assert retained == raw and context.time.known_at == now
        result = normalize_resource(context, "results", retained)
        assert not result.findings
        store = ObservationArtifactStore(c, tmp_path)
        prepared = [store.prepare(o) for o in result.observations]
        output_hash = hashlib.sha256(
            json.dumps([o.sha256 for o in result.observations]).encode()
        ).hexdigest()
        request = WorkRequest(
            work_type=WorkType.NORMALIZATION,
            semantic_key=f"understat-test:{digest}",
            input_hash=digest,
            priority=0,
            available_at=now,
            max_attempts=1,
            retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        )
        work = WorkRegistry(c)
        identifier = work.enqueue(request)
        claim = work.claim(
            "understat-test",
            timedelta(minutes=1),
            (WorkType.NORMALIZATION,),
            work_ids=(identifier,),
        )
        assert claim is not None
        with work.publication(claim, result_hash=output_hash):
            for prepared_item in prepared:
                store.register_prepared(prepared_item)
        assert work.state(identifier) == WorkState.SUCCEEDED
        assert work.enqueue(request) == identifier
        for observation in result.observations:
            assert store.load(observation.observation_id) == observation
            assert store.publish(observation) == observation.observation_id
        count = c.execute(
            "SELECT count(*) FROM football.resource_observation_artifacts "
            "WHERE source_resource_id=%s",
            (resource,),
        ).fetchone()
        assert count == (len(result.observations),)
        provider = c.execute("SELECT id FROM football.providers WHERE code='understat'").fetchone()
        assert provider is not None
        assert not PointInTimeRepository(c).resource_observation_ids_at(
            "ResultObservationV2",
            provider[0],
            now + timedelta(seconds=1),
            football_cutoff=datetime(2025, 1, 1, tzinfo=UTC),
        )
