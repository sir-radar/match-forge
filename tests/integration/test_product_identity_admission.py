import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from football.product.crosswalk_resolution import MappingRecord, _revise_mapping
from football.product.football_data_uk import parse_csv_resource
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.product.history_coverage import history_coverage
from football.product.identity_admission import admit_provider_mappings
from football.product.identity_audit import audit_report
from football.product.operational_provider_sync import OperationalProviderSync, SyncCounts
from football.providers.pitchapi import (
    PitchApiFixture,
    PitchApiResponse,
    normalize_pitchapi_matches,
)
from psycopg import Connection

from tests.integration.test_product_historical_backfill import DATABASE_URL


def _history(connection: Connection[Any], root: Path, *, exact: bool = False) -> None:
    acquired_at = datetime(2026, 9, 1, tzinfo=UTC)
    raw = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/08/2026,Home,Away,2,1\n"
    if exact:
        raw = b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/08/2026,15:00,Home,Away,2,1\n"
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


def test_history_qualification_lock_count_is_constant_at_scale() -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        connection.execute(
            "SELECT football.record_product_history_decision(gen_random_uuid()) "
            "FROM generate_series(1, 10000)"
        )
        locks = connection.execute(
            "SELECT count(*) FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'"
        ).fetchone()
        assert locks == (1,)


def test_scoped_history_preserves_admission_and_revocation_cutoffs(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        fixture = connection.execute(
            "SELECT fixture_id FROM football.product_team_match_history"
        ).fetchone()
        assert fixture is not None
        keys = [fixture[0], fixture[0], uuid4()]
        before = _cutoff(connection)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        admitted = _cutoff(connection)
        connection.execute("UPDATE football.team_provider_mappings SET mapping_confidence=0.5")
        revoked = _cutoff(connection)
        for cutoff, expected_count in ((before, 0), (admitted, 1), (revoked, 0)):
            scoped = connection.execute(
                "SELECT * FROM football.product_eligible_fixture_history_at(%s,%s::uuid[])",
                (cutoff, keys),
            ).fetchall()
            assert len(scoped) == expected_count
            assert (
                scoped
                == connection.execute(
                    "SELECT * FROM football.product_eligible_history_at(%s) WHERE fixture_id=%s",
                    (cutoff, fixture[0]),
                ).fetchall()
            )


@pytest.mark.parametrize("scope", ["", "  ", "Unknown", " World ", " unknown "])
def test_canonical_competition_rejects_geography_placeholders(tmp_path: Path, scope: str) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        with pytest.raises(psycopg.errors.CheckViolation), connection.transaction():
            connection.execute(
                "UPDATE football.product_competitions SET geographic_scope=%s", (scope,)
            )


def test_historical_replay_cannot_replace_conflicting_canonical_geography(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        competition = connection.execute(
            "SELECT competition_id FROM football.product_team_match_history"
        ).fetchone()
        assert competition is not None
        match = parse_csv_resource(
            b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/08/2026,Home,Away,2,1\n",
            source_path="test/season.csv",
            season="2026",
            country_hint="England",
        )[0]
        store = HistoricalBackfillStore(
            connection, "football_data_uk", "Football Data", "test-v1", data_root=tmp_path
        )
        with pytest.raises(ValueError, match="conflicting canonical competition geography"):
            store._ensure_geography(competition[0], replace(match, country="France"))
        assert connection.execute(
            "SELECT geographic_scope FROM football.product_competitions WHERE competition_id=%s",
            (competition[0],),
        ).fetchone() == ("England",)


def test_review_candidate_materializes_qualified_history_without_admitting_source(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path, exact=True)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        history = connection.execute(
            "SELECT fixture_id,kickoff_at,source_snapshot_id "
            "FROM football.product_team_match_history"
        ).fetchone()
        assert history is not None
        source = PitchApiFixture(
            "m_Revw01",
            "l_Revw01",
            "t_Home01",
            "t_Away01",
            "Home",
            "Away",
            history[1],
            "FINISHED",
            "Full Time",
            2,
            1,
            None,
            None,
            None,
            None,
            datetime.now(UTC),
            "Premier League",
            "REGULATION_90",
        )
        sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
        payload = {
            "data": {
                "matches": [
                    {
                        "id": "m_Revw01",
                        "league": {"id": "l_Revw01", "name": "Premier League"},
                        "home_team": {"id": "t_Home01", "name": "Home"},
                        "away_team": {"id": "t_Away01", "name": "Away"},
                        "time_utc": source.kickoff_at.isoformat(),
                        "status": "finished",
                        "score_home": 2,
                        "score_away": 1,
                    }
                ]
            }
        }
        raw = json.dumps(payload).encode()
        snapshot = sync._record_response(
            "review-candidate",
            PitchApiResponse(
                "test", source.observed_at, hashlib.sha256(raw).hexdigest(), raw, payload["data"]
            ),
        )
        assert sync._reconcile_exact_fixture(source, snapshot) is None
        assert connection.execute(
            "SELECT identity_status FROM football.product_fixtures WHERE fixture_id=%s",
            (history[0],),
        ).fetchone() == ("VERIFIED",)
        assert connection.execute(
            "SELECT disposition FROM football.product_provider_mapping_decisions "
            "WHERE provider_match_id='m_Revw01'"
        ).fetchone() == ("REVIEW_REQUIRED",)
        assert (
            sync._season_qualification(snapshot, [source], SyncCounts(unmatched=1))["status"]
            == "BLOCKED_IDENTITY"
        )


def test_season_with_only_unqualified_future_fixtures_cannot_complete(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        now = datetime.now(UTC)
        payload = {
            "data": {
                "leagues": [{"id": "l_Futu01", "country_code": "ENG"}],
                "matches": [
                    {
                        "id": "m_Futu01",
                        "league": {"id": "l_Futu01", "name": "Test League"},
                        "home_team": {"id": "t_FutuH1", "name": "Home"},
                        "away_team": {"id": "t_FutuA1", "name": "Away"},
                        "time_utc": (now + timedelta(days=1)).isoformat(),
                        "status": "scheduled",
                    }
                ],
            }
        }
        raw = json.dumps(payload).encode()
        response = PitchApiResponse(
            "test", now, hashlib.sha256(raw).hexdigest(), raw, payload["data"]
        )
        sync = OperationalProviderSync(connection, tmp_path, provider_code="pitchapi")
        snapshot = sync._record_response("league-l_Futu01-2026", response)
        rows = normalize_pitchapi_matches(response)
        assert len(rows) == 1
        fixture = sync._create_provider_scoped_fixture(rows[0], snapshot, season_label="2026")
        assert fixture is not None
        sync._store_observation(rows[0], snapshot, fixture)
        assert sync._season_qualification(snapshot, rows, SyncCounts(matched=1))["status"] == (
            "BLOCKED_IDENTITY"
        )


def test_history_diagnostics_replay_admission_cutoff_after_revocation(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        fixture = uuid4()
        connection.execute(
            """INSERT INTO football.matches (id,competition_id,season_id)
               SELECT %s,competition_id,season_id FROM football.matches LIMIT 1""",
            (fixture,),
        )
        connection.execute(
            """INSERT INTO football.product_fixtures (
                 fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
                 forecast_availability,updated_at)
               SELECT %s,competition_id,home_team_id,away_team_id,now()+interval '1 day',
                      'SCHEDULED','NOT_ENOUGH_HISTORY',now()
               FROM football.product_team_match_history LIMIT 1""",
            (fixture,),
        )
        before = _cutoff(connection)
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        admitted = _cutoff(connection)
        connection.execute("UPDATE football.team_provider_mappings SET mapping_confidence=0.5")
        revoked = _cutoff(connection)
        counts = []
        for cutoff in (before, admitted, revoked):
            report = history_coverage(connection, cutoff)
            row = next(f for f in report["upcoming_fixtures"] if f["fixture_id"] == str(fixture))
            counts.append((row["home_history"], row["away_history"], row["qualified_h2h"]))
            assert row["reason"] == "HOME_HISTORY_BELOW_CHAMPION_MINIMUM"
        assert counts == [(0, 0, 0), (1, 1, 1), (0, 0, 0)]


def test_proven_origin_method_repair_appends_mapping_without_backdating(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.transaction(force_rollback=True):
        _history(connection, tmp_path)
        connection.execute(
            "UPDATE football.competition_provider_mappings SET mapping_method='explicit_crosswalk' "
            "WHERE provider_competition_id='E0' AND valid_to IS NULL"
        )
        before = _cutoff(connection)
        row = connection.execute(
            """SELECT m.id,m.competition_id,m.provider_id,p.code,m.provider_competition_id,
                      m.mapping_method,m.source_snapshot_id,m.first_seen_at,m.last_seen_at,
                      c.name,c.country FROM football.competition_provider_mappings m
               JOIN football.providers p ON p.id=m.provider_id
               JOIN football.product_competitions c USING(competition_id)
               WHERE p.code='football_data_uk' AND m.provider_competition_id='E0'
                 AND m.valid_to IS NULL"""
        ).fetchone()
        assert row is not None
        mapping = MappingRecord(*row)
        _revise_mapping(
            connection, "competition", mapping, _cutoff(connection), mapping_method="deterministic"
        )
        assert connection.execute(
            "SELECT mapping_method,valid_to IS NULL FROM football.competition_provider_mappings "
            "WHERE provider_competition_id='E0' ORDER BY created_at,id"
        ).fetchall() == [("explicit_crosswalk", False), ("deterministic", True)]
        admit_provider_mappings(connection, tmp_path, "football_data_uk")
        assert len(_eligible(connection, _cutoff(connection))) == 1
        assert _eligible(connection, before) == []


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
        assert report["mapping_classifications"]["REVOKED"] >= 1
        assert report["currently_admitted_mapping_count"] >= 2
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
            """UPDATE football.source_snapshots SET source_identity = %s,
               source_revision = 'legacy',
               manifest_path = %s, manifest_sha256 = %s
               WHERE source_identity = 'test/season.csv'
                 AND source_revision LIKE 'manifest-v1:test:%%'""",
            (
                f"legacy/{uuid4()}",
                legacy_path,
                hashlib.sha256(legacy_path.encode()).hexdigest(),
            ),
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
        assert report["manifest_classifications"]["LEGACY_MANIFEST_UNVERIFIED"] >= 3
        assert report["legacy_manifest_unverified_snapshots"]["football_data_uk"] >= 1
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
