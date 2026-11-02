from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from football.providers.data_audit import audit_provider_data
from psycopg.pq import TransactionStatus


def test_provider_audit_is_read_only_and_does_not_populate_registries() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        before = connection.execute(
            "SELECT count(*) FROM football.provider_resource_capabilities"
        ).fetchone()[0]
        connection.rollback()
        report = audit_provider_data(connection)
        assert report["read_only"] == "on"
        assert connection.info.transaction_status == TransactionStatus.IDLE
        assert report["database"]
        assert report["normalizer_routes"]
        assert report["normalized_fields"] is None
        assert report["player_history"]["continuous_membership_qualified"] is None
        assert report["player_history"]["transfers_qualified"] is None
        assert "mapping_claims" in report["player_history"]
        assert "fixture_participation" in report["player_history"]
        assert (
            connection.execute(
                "SELECT count(*) FROM football.provider_resource_capabilities"
            ).fetchone()[0]
            == before
        )
        assert all(
            field["identity_qualified"] is None for field in report["observed_statistics"]["fields"]
        )


def test_provider_audit_rejects_caller_transaction_without_committing_it() -> None:
    code = "audit_" + uuid4().hex
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection:
        with connection.transaction(force_rollback=True):
            connection.execute(
                "INSERT INTO football.providers(code,name,source_type) VALUES (%s,%s,'http_api')",
                (code, code),
            )
            with pytest.raises(ValueError, match="idle connection"):
                audit_provider_data(connection)
            assert connection.execute(
                "SELECT code FROM football.providers WHERE code=%s", (code,)
            ).fetchone() == (code,)
        assert (
            connection.execute(
                "SELECT code FROM football.providers WHERE code=%s", (code,)
            ).fetchone()
            is None
        )


def test_retained_player_audit_keeps_duplicate_names_separate_and_verifies_bytes(tmp_path):
    from football.contracts.observations import ObservationError
    from football.contracts.observations_v2 import (
        EntityReferenceV2,
        ObservationVersionsV2,
        PlayerObservationV2,
    )
    from football.observations.storage import ObservationArtifactStore
    from football.providers.data_audit import _normalized_coverage
    from test_resource_observation_artifacts import _observation

    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        fixture = _observation(connection, tmp_path)
        store = ObservationArtifactStore(connection, tmp_path)
        for native in ("native-one", "native-two"):
            player = PlayerObservationV2(
                provenance=fixture.provenance,
                time=fixture.time,
                versions=ObservationVersionsV2(adapter_version="test", normalizer_version="test"),
                player=EntityReferenceV2(native),
                name="Same name",
            )
            store.publish(player)
        report = _normalized_coverage(connection, tmp_path)
        assert report["players"] == [
            {
                "provider": "api_football",
                "observed_native_players": 2,
                "native_players_with_recorded_mapping_claim": 0,
                "claimed_canonical_players": 0,
                "identity_qualified": None,
                "pit_eligible": None,
            }
        ]
        path = connection.execute(
            "SELECT artifact_path FROM football.resource_observation_artifacts "
            "WHERE observation_id=%s",
            (player.observation_id,),
        ).fetchone()[0]
        (tmp_path / path).write_bytes(b"{}")
        with pytest.raises(ObservationError, match="checksum"):
            _normalized_coverage(connection, tmp_path)
