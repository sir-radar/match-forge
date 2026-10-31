from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.contracts.observation_schema import observation_schema_sha256
from football.contracts.observations import observation_from_bytes
from football.contracts.observations_v2 import EntityReferenceV2
from football.contracts.observations_v3 import (
    ObservationVersionsV3,
    TeamRatingObservationV3,
    TeamStatisticObservationV3,
)
from football.observations.storage import ObservationArtifactStore
from football.temporal.repository import PointInTimeRepository
from test_resource_observation_artifacts import _observation


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        yield c


def test_rich_schema_round_trip_retry_preserves_prior_artifacts(connection, tmp_path: Path):
    old = _observation(connection, tmp_path)
    payload = old.to_dict()
    payload["contract"] = "FixtureObservationV2"
    payload["versions"]["observation_contract_version"] = "2"
    prior = observation_from_bytes(json.dumps(payload).encode())
    store = ObservationArtifactStore(connection, tmp_path)
    original_id = store.publish(prior)
    original_bytes = prior.to_bytes()
    original_schema = observation_schema_sha256("2")
    item = TeamStatisticObservationV3(
        provenance=old.provenance,
        time=old.time,
        versions=ObservationVersionsV3(adapter_version="test", normalizer_version="rich-test"),
        fixture=EntityReferenceV2("42"),
        team=EntityReferenceV2("1"),
        period="FULL_MATCH",
        offsides=0,
        expected_goals_on_target=0.5,
    )
    identifier = store.publish(item)
    assert store.publish(item) == identifier
    assert store.load(identifier) == item
    assert store.load(original_id).to_bytes() == original_bytes
    assert connection.execute(
        "SELECT schema_sha256 FROM football.observation_contract_schemas "
        "WHERE contract_name=%s AND observation_contract_version='2'",
        (prior.CONTRACT,),
    ).fetchone() == (original_schema,)


def test_calendar_rating_never_substitutes_for_unknown_event_time(connection, tmp_path: Path):
    old = _observation(connection, tmp_path)
    item = TeamRatingObservationV3(
        provenance=old.provenance,
        time=replace(old.time, event_time=None),
        versions=ObservationVersionsV3(adapter_version="test", normalizer_version="rating-test"),
        team=EntityReferenceV2("1"),
        rating_date=date(2020, 1, 1),
        rating=1500,
        rating_system="test-source-rating",
    )
    identifier = ObservationArtifactStore(connection, tmp_path).publish(item)
    provider = connection.execute(
        "SELECT id FROM football.providers WHERE code=%s", (item.provenance.provider,)
    ).fetchone()[0]
    cutoff = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    history = PointInTimeRepository(connection)
    assert identifier in history.resource_observation_ids_at(item.CONTRACT, provider, cutoff)
    assert not history.resource_observation_ids_at(
        item.CONTRACT,
        provider,
        cutoff,
        football_cutoff=old.time.observed_at + timedelta(days=1),
    )
