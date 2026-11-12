from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import Connection
from psycopg.errors import CheckViolation, RaiseException

from scripts.capture_architecture_v2_baseline import ROOT
from scripts.recovery_dispositions import (
    Approval,
    Correction,
    RecoveryDispositionError,
    Retirement,
    record_dispositions,
)
from scripts.recovery_scope import inventory
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


def _snapshot(
    connection: Connection[Any],
    identity: str,
    path: str,
    digest: str,
    *,
    provider: str | None = None,
    revision: str = "b" * 40,
) -> UUID:
    code = provider or f"provider_{uuid4().hex}"
    provider_id = connection.execute(
        "INSERT INTO football.providers(code,name,source_type) VALUES (%s,%s,'git_repository') "
        "ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name RETURNING id",
        (code, code),
    ).fetchone()
    assert provider_id is not None
    # Seed a pre-guard legacy row when asked; new path-digest registrations are rejected.
    legacy = digest == hashlib.sha256(path.encode()).hexdigest()
    with legacy_path_digest(connection) if legacy else nullcontext():
        row = connection.execute(
            "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
            "git_sha,acquired_at,manifest_path,manifest_sha256,status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'acquired') RETURNING id",
            (
                provider_id[0],
                identity,
                revision,
                None if revision.startswith("manifest-v1:") else revision,
                NOW,
                path,
                digest,
            ),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _resource(
    connection: Connection[Any], snapshot_id: UUID, path: str, digest: str, size: int
) -> UUID:
    row = connection.execute(
        "INSERT INTO football.source_resources(source_snapshot_id,provider_path,sha256,size_bytes,"
        "media_type,parse_status,validation_status,acquired_at) "
        "VALUES (%s,%s,%s,%s,'application/json','parsed','valid',%s) RETURNING id",
        (snapshot_id, path, digest, size, NOW),
    ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def _synthetic(connection: Connection[Any]) -> tuple[Retirement, Retirement]:
    suffix = uuid4().hex
    snapshot = _snapshot(
        connection, f"example/open-data/{suffix}", f"manifests/{suffix}.json", "a" * 64
    )
    resource = _resource(connection, snapshot, f"data/{suffix}.json", "c" * 64, 2)
    return (
        Retirement(
            "source_snapshots", str(snapshot), f"manifests/{suffix}.json", "a" * 64, *EVIDENCE
        ),
        Retirement("source_resources", str(resource), f"data/{suffix}.json", "c" * 64, *EVIDENCE),
    )


def _registrations(connection: Connection[Any], ids: list[str]) -> list[Any]:
    return connection.execute(
        "SELECT to_jsonb(s) FROM football.source_snapshots s WHERE id::text=ANY(%s) "
        "UNION ALL SELECT to_jsonb(r) FROM football.source_resources r WHERE id::text=ANY(%s) "
        "ORDER BY 1",
        (ids, ids),
    ).fetchall()


def _owners(items: list[dict[str, Any]]) -> set[str]:
    owners = set()
    for item in items:
        for owner in item.get("registrations") or [item.get("registration")]:
            owners.add(str(owner["keys"]["id"]))
    return owners


def test_dispositions_shrink_recovery_scope_without_changing_registrations(
    connection: Connection[Any], tmp_path: Path
) -> None:
    retirements = _synthetic(connection)
    git_sha = uuid4().hex + "0" * 8
    manifest = f"openfootball/{git_sha}/catalog.json"
    payload = b'{"matches":[]}'
    openfootball = _snapshot(
        connection,
        "https://github.com/openfootball/football.json.git",
        manifest,
        hashlib.sha256(manifest.encode()).hexdigest(),
        provider="openfootball",
        revision=git_sha,
    )
    present = _resource(
        connection, openfootball, "2025-26/en.1.json", hashlib.sha256(payload).hexdigest(), 14
    )
    (tmp_path / "openfootball" / git_sha / "2025-26").mkdir(parents=True)
    (tmp_path / "openfootball" / git_sha / "2025-26/en.1.json").write_bytes(payload)
    ours = {item.registration_id for item in retirements} | {str(openfootball)}
    before_rows = _registrations(connection, [*ours, str(present)])
    before = inventory(connection, tmp_path, ROOT, {})
    assert _owners(before["unavailable"]) & ours == ours
    assert not _owners(before["excluded"]) & ours

    counts = record_dispositions(
        connection, retirements, (Correction(str(openfootball), manifest, *EVIDENCE),), APPROVAL
    )
    after = inventory(connection, tmp_path, ROOT, {})

    assert counts == {"inserted": 3, "verified_existing": 0}
    assert not _owners(after["unavailable"]) & ours
    assert _owners(after["excluded"]) & ours == ours
    assert len(after["unavailable"]) == len(before["unavailable"]) - 3
    assert any(str(present) in str(ref.registrations) for ref in after["references"])
    assert _registrations(connection, [*ours, str(present)]) == before_rows
    assert {disposition for item in after["excluded"] for disposition in item["dispositions"]} >= {
        "SYNTHETIC_TEST_LINEAGE",
        "MANIFEST_NEVER_WRITTEN_PATH_DIGEST",
    }

    retry = record_dispositions(
        connection, retirements, (Correction(str(openfootball), manifest, *EVIDENCE),), APPROVAL
    )
    assert retry == {"inserted": 0, "verified_existing": 3}
    with pytest.raises(RecoveryDispositionError, match="immutable history"):
        record_dispositions(
            connection,
            retirements[:1],
            (),
            Approval("another decision", NOW, "a" * 40),
        )


def test_database_rejects_unproven_dispositions(connection: Connection[Any]) -> None:
    snapshot, _resource_retirement = _synthetic(connection)
    real = _snapshot(connection, "provider/real", "manifests/real.json", "d" * 64)
    v1 = _snapshot(
        connection,
        "provider/v1",
        "manifests/v1.json",
        hashlib.sha256(b"manifests/v1.json").hexdigest(),
        revision="manifest-v1:" + "d" * 64,
    )
    cases = [
        (
            (
                Retirement(
                    "source_snapshots", str(real), "manifests/real.json", "d" * 64, *EVIDENCE
                ),
            ),
            (),
            "lineage",
        ),
        ((replace(snapshot, sha256="b" * 64),), (), "differs"),
        (
            (Retirement("dataset_files", str(uuid4()), "x.parquet", "b" * 64, *EVIDENCE),),
            (),
            "not registered",
        ),
        ((), (Correction(snapshot.registration_id, snapshot.path, *EVIDENCE),), "differs"),
        ((), (Correction(str(v1), "manifests/v1.json", *EVIDENCE),), "differs"),
    ]
    for retirements, corrections, message in cases:
        with pytest.raises(RecoveryDispositionError, match=message):
            record_dispositions(connection, retirements, corrections, APPROVAL)
    with pytest.raises(CheckViolation, match="path_digest"), connection.transaction():
        connection.execute(
            "INSERT INTO football.source_manifest_corrections(source_snapshot_id,correction,"
            "registered_path,registered_sha256,evidence_reference,evidence_sha256,"
            "decision_reference,recorded_at,code_commit_sha) "
            "VALUES (%s,'MANIFEST_NEVER_WRITTEN_PATH_DIGEST',%s,%s,'e',%s,'d',%s,%s)",
            (real, "manifests/real.json", "d" * 64, "1" * 64, NOW, "a" * 40),
        )


def test_dispositions_are_append_only(connection: Connection[Any]) -> None:
    record_dispositions(connection, _synthetic(connection), (), APPROVAL)
    for statement in (
        "UPDATE football.recovery_scope_retirements SET decision_reference='changed'",
        "DELETE FROM football.recovery_scope_retirements",
        "TRUNCATE football.recovery_scope_retirements",
        "TRUNCATE football.source_manifest_corrections",
    ):
        with pytest.raises(RaiseException, match="append-only"), connection.transaction():
            connection.execute(statement)


def _model_input(connection: Connection[Any], model: UUID, dataset: UUID, snapshot: UUID) -> None:
    connection.execute(
        "INSERT INTO football.model_artifact_inputs(model_artifact_id,dataset_version_id,"
        "source_snapshot_id,feature_set_version,football_cutoff,knowledge_cutoff,"
        "quality_policy_sha256,target_set_sha256,knowledge_mode) "
        "VALUES (%s,%s,%s,'v1',%s,%s,%s,%s,'v1')",
        (model, dataset, snapshot, NOW, NOW, "6" * 64, "7" * 64),
    )


def _seed_model_lineage(connection: Connection[Any], snapshots: list[UUID]) -> dict[str, UUID]:
    """Seed derived rows directly; publication triggers are bypassed only for seeding."""
    connection.execute("SET LOCAL session_replication_role = replica")
    ids: dict[str, UUID] = {}
    for index, snapshot in enumerate(snapshots):
        dataset, model = uuid4(), uuid4()
        connection.execute(
            "INSERT INTO football.dataset_versions(id,source_snapshot_id,dataset_name,layer,"
            "identity_hash,schema_version,schema_sha256,normalizer_version,manifest_path,"
            "manifest_sha256,status,published_at) VALUES "
            "(%s,%s,'events','normalized',%s,'v1',%s,'v1',%s,%s,'published',%s)",
            (dataset, snapshot, uuid4().hex * 2, "2" * 64, f"d/{dataset}.json", "3" * 64, NOW),
        )
        connection.execute(
            "INSERT INTO football.model_artifacts(id,model_family,fit_spec_sha256,"
            "logical_model_state_sha256,schema_version,algorithm_version,serializer_version,"
            "manifest_path,manifest_sha256,status,published_at) VALUES "
            "(%s,'TEAM_ELO',%s,%s,'v1','v1','v1',%s,%s,'published',%s)",
            (model, uuid4().hex * 2, "4" * 64, f"m/{model}.json", "5" * 64, NOW),
        )
        _model_input(connection, model, dataset, snapshot)
        ids[f"dataset_{index}"], ids[f"model_{index}"] = dataset, model
    connection.execute("SET LOCAL session_replication_role = origin")
    return ids


def test_derived_lineage_must_reach_only_synthetic_snapshots(connection: Connection[Any]) -> None:
    synthetic = UUID(_synthetic(connection)[0].registration_id)
    real = _snapshot(connection, "provider/real", f"manifests/{uuid4().hex}.json", "d" * 64)
    ids = _seed_model_lineage(connection, [synthetic, real])
    connection.execute("SET LOCAL session_replication_role = replica")
    file_id, artifact_file_id = uuid4(), uuid4()
    connection.execute(
        "INSERT INTO football.dataset_files(id,dataset_version_id,relative_path,physical_sha256,"
        "logical_sha256,row_count,size_bytes,schema_sha256) "
        "VALUES (%s,%s,'n/first.parquet',%s,%s,1,1,%s)",
        (file_id, ids["dataset_0"], "5" * 64, "8" * 64, "2" * 64),
    )
    connection.execute(
        "INSERT INTO football.model_artifact_files(id,model_artifact_id,relative_path,media_type,"
        "physical_sha256,size_bytes) VALUES (%s,%s,'state.json','application/json',%s,1)",
        (artifact_file_id, ids["model_0"], "9" * 64),
    )
    _model_input(connection, ids["model_1"], ids["dataset_0"], synthetic)  # mixed lineage
    evaluation = connection.execute(
        "INSERT INTO football.sprint2_evaluation_runs(policy_version,dataset_version_id,"
        "source_snapshot_id,target_set_sha256,report_path,report_sha256,status,completed_at,"
        "competition_rules_id,competition_rules_sha256,outcome_scope) "
        "VALUES ('v1',%s,%s,%s,'e/report.json',%s,'FAIL',%s,'rules',%s,'REGULATION_TIME') "
        "RETURNING id",
        (ids["dataset_0"], synthetic, "7" * 64, "a" * 64, NOW, "b" * 64),
    ).fetchone()
    assert evaluation is not None
    connection.execute("SET LOCAL session_replication_role = origin")

    def dataset(name: str) -> Retirement:
        return Retirement(
            "dataset_versions", str(ids[name]), f"d/{ids[name]}.json", "3" * 64, *EVIDENCE
        )

    def model(name: str) -> Retirement:
        return Retirement(
            "model_artifacts", str(ids[name]), f"m/{ids[name]}.json", "5" * 64, *EVIDENCE
        )

    accepted = (
        dataset("dataset_0"),
        Retirement("dataset_files", str(file_id), "n/first.parquet", "5" * 64, *EVIDENCE),
        model("model_0"),
        Retirement(
            "model_artifact_files", str(artifact_file_id), "state.json", "9" * 64, *EVIDENCE
        ),
    )
    rejected = (dataset("dataset_1"), model("model_1"))
    evaluation_retirement = Retirement(
        "sprint2_evaluation_runs", str(evaluation[0]), "e/report.json", "a" * 64, *EVIDENCE
    )
    assert record_dispositions(connection, accepted, (), APPROVAL)["inserted"] == 4
    for retirement in (*rejected, evaluation_retirement):
        with pytest.raises(RecoveryDispositionError, match="lineage"):
            record_dispositions(connection, (retirement,), (), APPROVAL)
    connection.execute(
        "INSERT INTO football.artifact_retirement_events(object_kind,object_id,retirement_scope,"
        "reason,evidence_reference,recorded_at,code_commit_sha) VALUES ('EVALUATION',%s,"
        "'TEST_ONLY_HARD_GATE_EXCLUSION','SYNTHETIC_TEST_LINEAGE','test',%s,%s)",
        (evaluation[0], NOW, "a" * 40),
    )
    assert record_dispositions(connection, (evaluation_retirement,), (), APPROVAL) == {
        "inserted": 1,
        "verified_existing": 0,
    }
