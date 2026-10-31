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
