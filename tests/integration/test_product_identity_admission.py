from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.football_data_uk import parse_csv_resource
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.product.identity_admission import admit_provider_mappings
from football.product.identity_audit import audit_report
from psycopg import Connection

from tests.integration.test_product_historical_backfill import DATABASE_URL


def _history(connection: Connection[Any], root: Path) -> None:
    acquired_at = datetime(2026, 9, 1, tzinfo=UTC)
    raw = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/08/2026,Home,Away,2,1\n"
    manifest = publish_manifest(
        root,
        provider="football_data_uk",
        source_identity="test/season.csv",
        source_revision="test",
        acquired_at=acquired_at,
        resources=[("test/season.csv", "raw/season.csv", raw)],
    )
    store = HistoricalBackfillStore(
        connection, "football_data_uk", "Football Data", "test-v1", data_root=root
    )
    snapshot = store.ensure_snapshot(
        source_identity="test/season.csv",
        source_revision="test",
        acquired_at=acquired_at,
        manifest_path=manifest,
    )
    store.record_resource(
        snapshot_id=snapshot,
        provider_path="test/season.csv",
        payload=raw,
        media_type="text/csv",
        acquired_at=acquired_at,
    )
    match = parse_csv_resource(
        raw, source_path="test/season.csv", season="2026", country_hint="England"
    )[0]
    assert store.import_match(match, snapshot, acquired_at) == "inserted"


def _cutoff(connection: Connection[Any]) -> datetime:
    row = connection.execute("SELECT clock_timestamp()").fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def _eligible(connection: Connection[Any], cutoff: datetime) -> list[tuple[Any, ...]]:
    return connection.execute(
        "SELECT fixture_id, home_goals, away_goals FROM football.product_eligible_history_at(%s)",
        (cutoff,),
    ).fetchall()


def test_admissions_promotions_revocations_are_prospective_and_idempotent(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        before = _cutoff(connection)
        assert _eligible(connection, before) == []
        decisions = admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert [decision["disposition"] for decision in decisions] == ["ORIGIN_ANCHOR"] * 3
        admitted = _cutoff(connection)
        original = _eligible(connection, admitted)
        assert len(original) == 1
        assert _eligible(connection, before) == []
        count = connection.execute(
            "SELECT count(*) FROM football.product_identity_admissions"
        ).fetchone()
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert (
            connection.execute(
                "SELECT count(*) FROM football.product_identity_admissions"
            ).fetchone()
            == count
        )
        connection.execute("UPDATE football.team_provider_mappings SET mapping_confidence = 0.5")
        revoked = _cutoff(connection)
        assert _eligible(connection, revoked) == []
        assert _eligible(connection, admitted) == original
        connection.execute("UPDATE football.team_provider_mappings SET mapping_confidence = 1")
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        promoted = _cutoff(connection)
        assert _eligible(connection, promoted) == original
        assert _eligible(connection, revoked) == []
        assert _eligible(connection, admitted) == original
        assert _eligible(connection, before) == []
        connection.execute("UPDATE football.source_snapshots SET status = 'quarantined'")
        assert _eligible(connection, _cutoff(connection)) == []
        assert _eligible(connection, promoted) == original
        assert connection.execute(
            """SELECT DISTINCT source_observed_at FROM football.product_identity_admissions
               WHERE disposition = 'ORIGIN_ANCHOR'"""
        ).fetchall() == [(datetime(2026, 9, 1, tzinfo=UTC),)]
        with pytest.raises(psycopg.Error, match="append-only"), connection.transaction():
            connection.execute(
                """UPDATE football.product_identity_admissions
                   SET decided_at = decided_at - interval '1 year'"""
            )
        with pytest.raises(psycopg.Error, match="append-only"), connection.transaction():
            connection.execute("DELETE FROM football.product_match_history_decisions")


def test_tampering_and_unproven_identifiers_do_not_gain_eligibility(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        admitted = _cutoff(connection)
        original = _eligible(connection, admitted)
        assert len(original) == 1
        (tmp_path / "raw/season.csv").write_bytes(b"tampered")
        decisions = admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert {decision["disposition"] for decision in decisions} == {"UNRESOLVED"}
        assert _eligible(connection, _cutoff(connection)) == []
        assert _eligible(connection, admitted) == original
        row = connection.execute(
            "SELECT min(decided_at) FROM football.product_identity_admissions"
        ).fetchone()
        assert row is not None and row[0] > datetime.now(UTC) - timedelta(minutes=1)


def test_operator_revocation_survives_automatic_readmission(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        admitted = _cutoff(connection)
        original = _eligible(connection, admitted)
        connection.execute(
            """INSERT INTO football.product_identity_admissions (
                   entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
                   disposition, reason, source_snapshot_id, source_observed_at,
                   evidence, evidence_sha256, decided_at)
               SELECT entity_type, mapping_id, canonical_id, provider_code, provider_entity_id,
                      'REVOKED', 'OPERATOR_REVOKED', source_snapshot_id, source_observed_at,
                      evidence, evidence_sha256, '2000-01-01'::timestamptz
               FROM football.product_identity_admissions WHERE entity_type = 'team' LIMIT 1"""
        )
        revoked = _cutoff(connection)
        count = connection.execute(
            "SELECT count(*) FROM football.product_identity_admissions"
        ).fetchone()
        decisions = admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert any(decision["disposition"] == "REVOKED" for decision in decisions)
        assert _eligible(connection, _cutoff(connection)) == []
        assert _eligible(connection, admitted) == original
        assert _eligible(connection, revoked) == []
        report = audit_report(connection, tmp_path)
        assert report["mapping_classifications"] == {"ORIGIN_ANCHOR": 2, "REVOKED": 1}
        assert report["currently_admitted_mapping_count"] == 2
        assert report["status"] == "FAIL"
        assert (
            connection.execute(
                "SELECT count(*) FROM football.product_identity_admissions"
            ).fetchone()
            == count
        )
        assert connection.execute(
            "SELECT min(decided_at) FROM football.product_identity_admissions"
        ).fetchone()[0] > datetime.now(UTC) - timedelta(minutes=1)


def test_legacy_registration_remains_unverified_and_unchanged(tmp_path: Path) -> None:
    import hashlib

    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        legacy_path = "raw/season.csv"
        connection.execute(
            """UPDATE football.source_snapshots SET source_revision = 'legacy',
               manifest_path = %s, manifest_sha256 = %s""",
            (legacy_path, hashlib.sha256(legacy_path.encode()).hexdigest()),
        )
        registration = connection.execute(
            "SELECT to_jsonb(s) FROM football.source_snapshots s"
        ).fetchall()
        before = _cutoff(connection)
        decisions = admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert {d["disposition"] for d in decisions} == {"ORIGIN_ANCHOR"}
        assert {d["evidence"]["manifest_classification"] for d in decisions} == {
            "LEGACY_MANIFEST_UNVERIFIED"
        }
        assert _eligible(connection, before) == []
        assert len(_eligible(connection, _cutoff(connection))) == 1
        report = audit_report(connection, tmp_path)
        assert report["manifest_classifications"] == {"LEGACY_MANIFEST_UNVERIFIED": 3}
        assert report["legacy_manifest_unverified_snapshots"] == {"football_data_uk": 1}
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert (
            connection.execute("SELECT to_jsonb(s) FROM football.source_snapshots s").fetchall()
            == registration
        )
        (tmp_path / legacy_path).write_bytes(b"tampered")
        decisions = admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert {d["disposition"] for d in decisions} == {"UNRESOLVED"}
        assert _eligible(connection, _cutoff(connection)) == []
        assert (
            connection.execute("SELECT to_jsonb(s) FROM football.source_snapshots s").fetchall()
            == registration
        )
