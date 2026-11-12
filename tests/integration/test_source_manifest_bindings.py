from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.errors import CheckViolation, RaiseException

from scripts.recovery_dispositions import Approval, Correction, RecoveryDispositionError
from scripts.recovery_dispositions import record_dispositions as record_corrections
from scripts.recovery_files import registered_files
from scripts.source_manifest_bindings import Binding, SourceManifestBindingError, record_bindings
from tests.integration.legacy_rows import legacy_path_digest

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
APPROVAL = Approval("owner decision", NOW, "a" * 40)
EVIDENCE = ("evidence.json", "1" * 64)


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


def _provider(connection: Connection[Any]) -> UUID:
    code = f"provider_{uuid4().hex}"
    row = connection.execute(
        "INSERT INTO football.providers(code,name,source_type) VALUES (%s,%s,'git_repository') "
        "RETURNING id",
        (code, code),
    ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _legacy_snapshot(
    connection: Connection[Any], provider: UUID, identity: str, path: str, revision: str
) -> UUID:
    """Seed a pre-guard legacy row whose manifest checksum is the digest of its path."""
    with legacy_path_digest(connection):
        row = connection.execute(
            "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
            "acquired_at,manifest_path,manifest_sha256,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,'validated') RETURNING id",
            (provider, identity, revision, NOW, path, hashlib.sha256(path.encode()).hexdigest()),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _resource(connection: Connection[Any], snapshot: UUID, digest: str, size: int) -> UUID:
    row = connection.execute(
        "INSERT INTO football.source_resources(source_snapshot_id,provider_path,sha256,size_bytes,"
        "media_type,parse_status,validation_status,acquired_at) "
        "VALUES (%s,'fixtures.csv',%s,%s,'text/csv','parsed','valid',%s) RETURNING id",
        (snapshot, digest, size, NOW),
    ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _pair(connection: Connection[Any]) -> dict[str, Any]:
    """An http snapshot with its resource and an https sibling without one, as in production."""
    digest = uuid4().hex * 2
    path = f"football_data_uk/unknown/{digest}.csv"
    provider = _provider(connection)
    http = _legacy_snapshot(connection, provider, "http://example/fixtures.csv", path, digest)
    https = _legacy_snapshot(connection, provider, "https://example/fixtures.csv", path, digest)
    resource = _resource(connection, http, digest, 4052)
    return {"path": path, "digest": digest, "http": http, "https": https, "resource": resource}


def _binding(snapshot: UUID, item: dict[str, Any], **changes: Any) -> Binding:
    value = Binding(
        str(snapshot), item["path"], str(item["resource"]), item["digest"], 4052, *EVIDENCE
    )
    return replace(value, **changes)


def _snapshot_rows(connection: Connection[Any], ids: list[UUID]) -> list[Any]:
    return connection.execute(
        "SELECT to_jsonb(s) FROM football.source_snapshots s WHERE id=ANY(%s) ORDER BY id",
        (ids,),
    ).fetchall()


def test_bindings_record_own_and_sibling_resources_without_changing_snapshots(
    connection: Connection[Any],
) -> None:
    item = _pair(connection)
    before = _snapshot_rows(connection, [item["http"], item["https"]])
    bindings = (_binding(item["http"], item), _binding(item["https"], item))

    assert record_bindings(connection, bindings, APPROVAL) == {
        "inserted": 2,
        "verified_existing": 0,
    }
    assert record_bindings(connection, bindings, APPROVAL) == {
        "inserted": 0,
        "verified_existing": 2,
    }
    assert _snapshot_rows(connection, [item["http"], item["https"]]) == before
    with pytest.raises(SourceManifestBindingError, match="immutable history"):
        record_bindings(connection, bindings[:1], Approval("another", NOW, "a" * 40))


def test_database_rejects_unproven_bindings(connection: Connection[Any]) -> None:
    item = _pair(connection)
    other = _pair(connection)
    v1_path = f"football_data_uk/v1/{item['digest']}.csv"
    v1 = _legacy_snapshot(
        connection, _provider(connection), "v1", v1_path, "manifest-v1:" + item["digest"]
    )
    cases = [
        (_binding(item["http"], item, resource_size_bytes=4051), "differs from the resource"),
        (_binding(item["http"], item, path=other["path"]), "differs from the registration"),
        (_binding(v1, item, path=v1_path), "differs from the registration"),
        # A snapshot with its own resource cannot borrow another snapshot's resource.
        (_binding(other["http"], other, source_resource_id=str(item["resource"])), "differs"),
        (
            _binding(
                other["https"],
                other,
                source_resource_id=str(item["resource"]),
                resource_sha256=item["digest"],
            ),
            "differs from the registration",
        ),
    ]
    for binding, message in cases:
        with pytest.raises(SourceManifestBindingError, match=message):
            record_bindings(connection, (binding,), APPROVAL)


def test_resource_named_by_checksum_must_come_from_same_snapshot_lineage(
    connection: Connection[Any],
) -> None:
    item = _pair(connection)
    provider = _provider(connection)
    stranger = _legacy_snapshot(
        connection, provider, "https://elsewhere", item["path"], item["digest"]
    )
    with pytest.raises(SourceManifestBindingError, match="unrelated resource"):
        record_bindings(connection, (_binding(stranger, item),), APPROVAL)


def test_never_written_corrections_and_bindings_are_exclusive(
    connection: Connection[Any],
) -> None:
    item = _pair(connection)
    record_bindings(connection, (_binding(item["https"], item),), APPROVAL)
    with pytest.raises(RecoveryDispositionError, match="bound to a raw resource"):
        record_corrections(
            connection, (), (Correction(str(item["https"]), item["path"], *EVIDENCE),), APPROVAL
        )
    record_corrections(
        connection, (), (Correction(str(item["http"]), item["path"], *EVIDENCE),), APPROVAL
    )
    with pytest.raises(SourceManifestBindingError, match="never written"):
        record_bindings(connection, (_binding(item["http"], item),), APPROVAL)


def test_bindings_are_append_only(connection: Connection[Any]) -> None:
    item = _pair(connection)
    record_bindings(connection, (_binding(item["http"], item),), APPROVAL)
    for statement in (
        "UPDATE football.source_manifest_raw_file_bindings SET decision_reference='changed'",
        "DELETE FROM football.source_manifest_raw_file_bindings",
        "TRUNCATE football.source_manifest_raw_file_bindings",
    ):
        with pytest.raises(RaiseException, match="append-only"), connection.transaction():
            connection.execute(statement)


def test_guard_rejects_new_path_digest_snapshots_but_keeps_legacy_rows_writable(
    connection: Connection[Any],
) -> None:
    provider = _provider(connection)
    path = "football_data_uk/2010-2011/" + "c" * 64 + ".zip"
    path_digest = hashlib.sha256(path.encode()).hexdigest()
    with pytest.raises(CheckViolation, match="digest of its path"), connection.transaction():
        connection.execute(
            "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
            "acquired_at,manifest_path,manifest_sha256,status) "
            "VALUES (%s,'new','r',%s,%s,%s,'validated')",
            (provider, NOW, path, path_digest),
        )
    row = connection.execute(
        "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
        "acquired_at,manifest_path,manifest_sha256,status) "
        "VALUES (%s,'content','r',%s,%s,%s,'validated') RETURNING id",
        (provider, NOW, path, "c" * 64),
    ).fetchone()
    assert row is not None
    with pytest.raises(CheckViolation, match="digest of its path"), connection.transaction():
        connection.execute(
            "UPDATE football.source_snapshots SET manifest_sha256=%s WHERE id=%s",
            (path_digest, row[0]),
        )
    legacy = _legacy_snapshot(connection, provider, "legacy", path, "c" * 64)
    connection.execute(
        "UPDATE football.source_snapshots SET status='acquired' WHERE id=%s", (legacy,)
    )


def test_recovery_captures_bound_snapshots_with_the_resource_checksum(
    connection: Connection[Any], tmp_path: Path
) -> None:
    item = _pair(connection)
    ids = {str(item["http"]), str(item["https"])}

    def snapshot_owners() -> dict[str, dict[str, Any]]:
        unresolved: list[dict[str, Any]] = []
        refs = [r for r in registered_files(connection, tmp_path, unresolved=unresolved)]
        return {
            owner["keys"]["id"]: {**owner, "sha256": ref.sha256, "size": ref.size}
            for ref in refs
            if ref.path == item["path"]
            for owner in ref.registrations
            if owner["table"] == "source_snapshots" and owner["keys"]["id"] in ids
        }

    before = snapshot_owners()
    assert {owner["checksum_kind"] for owner in before.values()} == {"PATH_IDENTITY"}
    record_bindings(
        connection, (_binding(item["http"], item), _binding(item["https"], item)), APPROVAL
    )
    after = snapshot_owners()
    assert set(after) == ids
    for owner in after.values():
        assert owner["checksum_kind"] == "BOUND_RESOURCE"
        assert owner["source_resource_id"] == str(item["resource"])
        assert (owner["sha256"], owner["size"]) == (item["digest"], 4052)
