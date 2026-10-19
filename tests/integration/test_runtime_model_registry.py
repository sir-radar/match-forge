"""Runtime declarations are immutable, forward-known and cannot promote another model."""

import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.cli.main import run
from football.forecasting.runtime_models import ModelRegistration, PostgresModelRegistry


def entry() -> ModelRegistration:
    return ModelRegistration.from_bytes(Path("config/models/current-champion.json").read_bytes())


def unique_entry() -> ModelRegistration:
    return replace(entry(), artifact_uri=f"registry-tests/{uuid4()}.json")


def test_registry_exact_retry_and_no_historical_inference() -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        store = PostgresModelRegistry(c)
        model = unique_entry()
        before = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert store.register(model) == "published"
        assert store.register(model) == "verified_existing"
        known = c.execute(
            "SELECT registered_at FROM football.runtime_model_registrations "
            "WHERE registration_sha256=%s",
            (model.sha256,),
        ).fetchone()[0]
        assert known >= before
        assert store.get(model.sha256, knowledge_cutoff=known - timedelta(microseconds=1)) is None
        assert store.get(model.sha256, knowledge_cutoff=known) == model


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE football.runtime_model_registrations SET registered_at=clock_timestamp() "
        "WHERE registration_sha256=%s",
        "DELETE FROM football.runtime_model_registrations WHERE registration_sha256=%s",
        "TRUNCATE football.runtime_model_registrations",
    ],
)
def test_registry_declarations_cannot_be_changed(statement: str) -> None:
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c, c.transaction(force_rollback=True):
        model = unique_entry()
        PostgresModelRegistry(c).register(model)
        with pytest.raises(psycopg.Error), c.transaction():
            c.execute(statement, () if statement.startswith("TRUNCATE") else (model.sha256,))
        assert (
            c.execute(
                "SELECT count(*) FROM football.runtime_model_registrations "
                "WHERE registration_sha256=%s",
                (model.sha256,),
            ).fetchone()[0]
            == 1
        )


def test_concurrent_exact_registrations_converge() -> None:
    model = unique_entry()

    def register() -> str:
        with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
            return PostgresModelRegistry(c).register(model)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: register(), range(2))) == [
            "published",
            "verified_existing",
        ]
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
        assert (
            c.execute(
                "SELECT count(*) FROM football.runtime_model_registrations "
                "WHERE registration_sha256=%s",
                (model.sha256,),
            ).fetchone()[0]
            == 1
        )


def test_failed_registration_rolls_back() -> None:
    model = unique_entry()
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
        with c.transaction(force_rollback=True):
            PostgresModelRegistry(c).register(model)
        now = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert PostgresModelRegistry(c).get(model.sha256, knowledge_cutoff=now) is None


@pytest.mark.parametrize("invalid", ["checksum", "contract", "champion"])
def test_sql_rejects_invalid_or_unapproved_champion_record(invalid: str) -> None:
    model = unique_entry()
    value = model.to_dict()
    if invalid == "contract":
        value.pop("model_id")
    if invalid == "champion":
        value["artifact_hash"] = "f" * 64
    raw = json.dumps(value).encode()
    digest = hashlib.sha256(raw).hexdigest()
    if invalid == "checksum":
        digest = "0" * 64
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c,
        c.transaction(force_rollback=True),
        pytest.raises(psycopg.errors.CheckViolation),
        c.transaction(),
    ):
        c.execute(
            """INSERT INTO football.runtime_model_registrations
                (registration_sha256,model_id,artifact_sha256,lifecycle_state,record_bytes)
                VALUES(%s,%s,%s,%s,%s)""",
            (digest, model.model_id, value["artifact_hash"], model.lifecycle_state, raw),
        )


def test_read_only_registry_lookup() -> None:
    model = unique_entry()
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
        PostgresModelRegistry(c).register(model)
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
        c.execute("SET TRANSACTION READ ONLY")
        now = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert PostgresModelRegistry(c).get(model.sha256, knowledge_cutoff=now) == model


def test_registry_cli_registers_original_champion_without_activation() -> None:
    output = io.StringIO()
    errors = io.StringIO()
    environment = {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
    result = run(
        ["models", "registry-register", "--registration", "config/models/current-champion.json"],
        environ=environment,
        stdout=output,
        stderr=errors,
    )
    assert result == 0, errors.getvalue()
    response = json.loads(output.getvalue())
    assert response["registration_sha256"] == entry().sha256
    assert response["activated"] is False
    output = io.StringIO()
    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
        now = c.execute("SELECT clock_timestamp()").fetchone()[0]
    result = run(
        [
            "models",
            "registry-show",
            "--registration-sha256",
            entry().sha256,
            "--knowledge-cutoff",
            now.isoformat(),
        ],
        environ=environment,
        stdout=output,
        stderr=errors,
    )
    assert result == 0, errors.getvalue()
    assert ModelRegistration.from_bytes(output.getvalue().encode()) == entry()
