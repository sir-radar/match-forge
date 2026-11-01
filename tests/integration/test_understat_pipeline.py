from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from football.observations.storage import ObservationArtifactStore
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.pipeline import normalize_resource
from football.temporal.repository import PointInTimeRepository
from football.work.contracts import RetryPolicy, WorkRequest, WorkState, WorkType
from football.work.storage import WorkRegistry


@pytest.mark.parametrize("provider", ["understat", "espn"])
def test_public_source_manifest_normalization_fenced_publication_and_retry(
    tmp_path: Path, provider: str
) -> None:
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
    path = "getLeagueData/EPL/2024"
    resource_type = "results"
    if provider == "espn":
        path = "eng.1/scoreboard?dates=20240816"
        resource_type = "scoreboard"
        raw = json.dumps(
            {
                "leagues": [{"id": "700", "slug": "eng.1", "name": "League"}],
                "events": [
                    {
                        "id": "42",
                        "season": {"year": 2024},
                        "competitions": [
                            {
                                "id": "42",
                                "date": "2024-08-16T19:00Z",
                                "timeValid": True,
                                "status": {
                                    "type": {
                                        "name": "STATUS_FULL_TIME",
                                        "state": "post",
                                        "completed": True,
                                    }
                                },
                                "competitors": [
                                    {
                                        "id": "1",
                                        "homeAway": "home",
                                        "team": {"id": "1", "displayName": "Home"},
                                        "score": "1",
                                    },
                                    {
                                        "id": "2",
                                        "homeAway": "away",
                                        "team": {"id": "2", "displayName": "Away"},
                                        "score": "0",
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    now = datetime(2026, 11, 1, tzinfo=UTC)
    identity = "https://example.test/" + provider + "/" + path
    manifest = publish_manifest(
        tmp_path,
        provider=provider,
        source_identity=identity,
        source_revision=digest,
        acquired_at=now,
        resources=[(path, f"{provider}/raw/{digest}", raw)],
    )
    # The storage harness owns this disposable DB; control calls require idle connections.
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as c:
        owner = HistoricalBackfillStore(
            c,
            provider,
            provider.title(),
            provider + "-" + resource_type + "-v1",
            data_root=tmp_path,
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
        result = normalize_resource(context, resource_type, retained)
        assert not result.findings
        store = ObservationArtifactStore(c, tmp_path)
        prepared = [store.prepare(o) for o in result.observations]
        output_hash = hashlib.sha256(
            json.dumps([o.sha256 for o in result.observations]).encode()
        ).hexdigest()
        request = WorkRequest(
            work_type=WorkType.NORMALIZATION,
            semantic_key=f"{provider}-test:{digest}",
            input_hash=digest,
            priority=0,
            available_at=now,
            max_attempts=1,
            retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        )
        work = WorkRegistry(c)
        identifier = work.enqueue(request)
        claim = work.claim(
            provider + "-test",
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
        provider_row = c.execute(
            "SELECT id FROM football.providers WHERE code=%s", (provider,)
        ).fetchone()
        assert provider_row is not None
        assert not PointInTimeRepository(c).resource_observation_ids_at(
            "ResultObservationV2",
            provider_row[0],
            now + timedelta(seconds=1),
            football_cutoff=datetime(2025, 1, 1, tzinfo=UTC),
        )
