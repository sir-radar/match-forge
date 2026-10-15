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
from football.product.operational_provider_sync import (
    OperationalProviderSync,
    SyncCounts,
    _fotmob_season_rows,
)
from football.providers.fotmob import FotmobResponse
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


def _review_pair(connection: Connection[Any], root: Path) -> tuple[Any, ...]:
    _history(connection, root, exact=True)
    admit_provider_mappings(connection, root, "football_data_uk")
    fixture, kickoff = connection.execute(
        "SELECT fixture_id,kickoff_at FROM football.product_team_match_history"
    ).fetchone()
    sync = OperationalProviderSync(connection, root, provider_code="fotmob")
    sync._materialize_history_fixture(fixture, datetime.now(UTC))
    payload = {
        "details": {
            "id": 47,
            "name": "English Premier League",
            "selectedSeason": "2026/2027",
            "country": "ENG",
        },
        "fixtures": {
            "allMatches": [
                {
                    "id": "47001",
                    "home": {"id": "471", "name": "Home"},
                    "away": {"id": "472", "name": "Away"},
                    "status": {
                        "utcTime": kickoff.isoformat(),
                        "finished": True,
                        "started": True,
                        "cancelled": False,
                        "scoreStr": "2 - 1",
                        "reason": {"short": "FT"},
                    },
                }
            ]
        },
    }
    raw = json.dumps(payload).encode()
    response = FotmobResponse(
        "league", datetime.now(UTC), hashlib.sha256(raw).hexdigest(), raw, payload
    )
    snapshot = sync._record_response("league-47-2026/2027", response)
    row = _fotmob_season_rows(response, "47", "2026/2027")[0]
    sync._store_observation(row, snapshot, None)
    return sync, fixture, snapshot, row


def test_competition_review_does_not_admit_teams_or_complete_the_source_season(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        before = _cutoff(c)
        sync.apply_reviewed_mapping(
            row.provider_match_id, fixture, source_snapshot_id=snapshot, competition_only=True
        )
        assert c.execute(
            "SELECT count(*) FROM football.team_provider_mappings m "
            "JOIN football.providers p ON p.id=m.provider_id WHERE p.code='fotmob'"
        ).fetchone() == (0,)
        assert (
            sync._season_qualification(snapshot, [row], SyncCounts(matched=1))["status"]
            == "BLOCKED_IDENTITY"
        )
        assert len(_eligible(c, before)) == 1
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        assert (
            sync._season_qualification(snapshot, [row], SyncCounts(matched=1))["status"]
            == "COMPLETED"
        )
        events = c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
        reviews = c.execute(
            "SELECT count(*) FROM football.product_provider_mapping_decisions"
        ).fetchone()
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        assert (
            c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
            == events
        )
        assert (
            c.execute("SELECT count(*) FROM football.product_provider_mapping_decisions").fetchone()
            == reviews
        )
        assert len(_eligible(c, before)) == 1


def test_qualified_source_replaces_only_unqualified_equal_score_history(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        old_source = c.execute(
            "SELECT source_snapshot_id FROM football.product_team_match_history"
        ).fetchone()[0]
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        assert c.execute(
            "SELECT source_snapshot_id FROM football.product_team_match_history"
        ).fetchone() == (old_source,)
        unqualified = OperationalProviderSync(c, tmp_path, provider_code="pitchapi")
        payload = {"data": {"matches": [{"id": "m_Oldsrc", "home": {"id": "t_Oldsrc"}}]}}
        raw = json.dumps(payload).encode()
        prior = unqualified._record_response(
            "old-result",
            PitchApiResponse(
                "test", datetime.now(UTC), hashlib.sha256(raw).hexdigest(), raw, payload
            ),
        )
        c.execute(
            "UPDATE football.product_team_match_history SET source_provider_code='pitchapi',"
            "source_snapshot_id=%s",
            (prior,),
        )
        denied = _cutoff(c)
        assert _eligible(c, denied) == []
        assert sync._insert_qualified_history(row, fixture, snapshot) == 1
        assert len(_eligible(c, _cutoff(c))) == 1
        assert _eligible(c, denied) == []
        assert sync._insert_qualified_history(row, fixture, snapshot) == 0
        assert c.execute("SELECT count(*) FROM football.product_team_match_history").fetchone() == (
            1,
        )


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
        now = connection.execute("SELECT clock_timestamp()").fetchone()[0]
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


def test_duplicate_team_aliases_emit_one_conservative_history_decision(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        _history(c, tmp_path)
        admit_provider_mappings(c, tmp_path, "football_data_uk")
        admitted = _cutoff(c)
        fixture = c.execute(
            "SELECT fixture_id FROM football.product_team_match_history "
            "WHERE source_provider_code='football_data_uk' "
            "AND kickoff_at::date='2026-08-01' AND home_goals=2 AND away_goals=1"
        ).fetchone()[0]
        c.execute(
            """INSERT INTO football.team_provider_mappings (
                 team_id,provider_id,provider_team_id,first_seen_at,last_seen_at,
                 mapping_method,mapping_confidence,source_snapshot_id)
               SELECT mapping.team_id,mapping.provider_id,'unproven alias',
                      mapping.first_seen_at,mapping.last_seen_at,
                      'explicit_crosswalk',1,mapping.source_snapshot_id
               FROM football.team_provider_mappings mapping
               JOIN football.product_team_match_history history
                 ON history.home_team_id=mapping.team_id
               JOIN football.providers provider ON provider.id=mapping.provider_id
               WHERE history.fixture_id=%s AND provider.code='football_data_uk'
                 AND mapping.valid_to IS NULL""",
            (fixture,),
        )
        before = c.execute(
            "SELECT count(*) FROM football.product_match_history_decisions"
        ).fetchone()
        c.execute("SELECT football.record_product_history_decision(%s)", (fixture,))
        after = c.execute(
            "SELECT count(*) FROM football.product_match_history_decisions"
        ).fetchone()
        c.execute("SELECT football.record_product_history_decision(%s)", (fixture,))
        assert (
            c.execute("SELECT count(*) FROM football.product_match_history_decisions").fetchone()
            == after
        )
        assert after[0] - before[0] <= 1
        assert _eligible(c, _cutoff(c)) == []
        assert len(_eligible(c, admitted)) == 1


def test_replayed_identical_facts_use_original_observation_lineage(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        # A second immutable acquisition may contain exactly the same facts.
        payload = json.loads(
            (
                sync.data_root
                / c.execute(
                    "SELECT manifest_path FROM football.source_snapshots WHERE id=%s", (snapshot,)
                ).fetchone()[0]
            ).read_text()
        )
        raw = json.dumps(payload).encode()
        response = FotmobResponse(
            "league", datetime.now(UTC), hashlib.sha256(raw).hexdigest(), raw, payload
        )
        newer = sync._record_response("league-catalogue-47", response)
        assert newer != snapshot
        before = c.execute(
            "SELECT count(*) FROM football.product_provider_fixture_observations"
        ).fetchone()
        sync._store_observation(row, newer, fixture)
        assert (
            c.execute(
                "SELECT count(*) FROM football.product_provider_fixture_observations"
            ).fetchone()
            == before
        )
        assert (
            sync._season_qualification(newer, [row], SyncCounts(matched=1))["status"] == "COMPLETED"
        )
        wrong = replace(row, provider_home_team_id="wrong")
        assert (
            sync._season_qualification(newer, [wrong], SyncCounts(matched=1))["status"]
            == "BLOCKED_IDENTITY"
        )


def test_review_reconciles_all_retained_members_before_history_and_retries(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        member = uuid4()
        c.execute(
            """INSERT INTO football.matches (id,competition_id,season_id)
               SELECT %s,competition_id,season_id FROM football.matches WHERE id=%s""",
            (member, fixture),
        )
        c.execute(
            """INSERT INTO football.product_fixtures (
                 fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
                 home_score,away_score,identity_status,forecast_availability,updated_at)
               SELECT %s,competition_id,home_team_id,away_team_id,kickoff_at,status,
                      home_score,away_score,'PROVISIONAL','SOURCE_DATA_INCOMPLETE',updated_at
               FROM football.product_fixtures WHERE fixture_id=%s""",
            (member, fixture),
        )
        # Reproduce a legacy member whose stored history conflicts with its new representative.
        c.execute(
            """INSERT INTO football.product_team_match_history (
                 fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,
                 away_goals,source_provider_code,source_snapshot_id,source_kickoff_precision)
               SELECT %s,competition_id,home_team_id,away_team_id,kickoff_at+interval '1 minute',
                      home_goals,away_goals,'fotmob',%s,source_kickoff_precision
               FROM football.product_team_match_history WHERE fixture_id=%s""",
            (member, snapshot, fixture),
        )
        c.execute(
            "UPDATE football.product_team_match_history SET kickoff_at=%s WHERE fixture_id=%s",
            (row.kickoff_at, member),
        )
        sync._store_observation(row, snapshot, member)
        sync.apply_reviewed_mapping(
            row.provider_match_id, fixture, source_snapshot_id=snapshot, competition_only=True
        )
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        resolutions = c.execute(
            "SELECT count(*) FROM football.fixture_identity_resolutions"
        ).fetchone()
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        assert (
            c.execute("SELECT count(*) FROM football.fixture_identity_resolutions").fetchone()
            == resolutions
        )
        assert c.execute(
            """SELECT representative_fixture_id FROM football.fixture_identity_resolutions
               WHERE member_fixture_id=%s AND active""",
            (member,),
        ).fetchone() == (fixture,)
        assert c.execute("SELECT count(*) FROM football.product_team_match_history").fetchone() == (
            2,
        )
        assert len(_eligible(c, _cutoff(c))) == 1


def test_team_review_uses_qualified_date_only_result_without_changing_history_time(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        midnight = row.kickoff_at.replace(hour=0, minute=0, second=0, microsecond=0)
        c.execute(
            """UPDATE football.product_team_match_history SET kickoff_at=%s,
               source_kickoff_precision='DATE_ONLY' WHERE fixture_id=%s""",
            (midnight, fixture),
        )
        c.execute(
            "UPDATE football.product_fixtures SET kickoff_at=%s WHERE fixture_id=%s",
            (midnight, fixture),
        )
        sync.apply_reviewed_mapping(
            row.provider_match_id,
            fixture,
            source_snapshot_id=snapshot,
        )
        assert c.execute(
            """SELECT kickoff_at,source_kickoff_precision
               FROM football.product_team_match_history WHERE fixture_id=%s""",
            (fixture,),
        ).fetchone() == (midnight, "DATE_ONLY")
        with pytest.raises(ValueError, match="kickoff"):
            sync._validate_reviewed_context(
                replace(row, kickoff_at=row.kickoff_at + timedelta(days=1)),
                (
                    fixture,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "FINISHED",
                    2,
                    1,
                    midnight,
                    "VERIFIED",
                    "DATE_ONLY",
                ),
            )


def test_admitted_native_ids_release_only_the_old_single_member_identity_quarantine(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        admitted = _cutoff(c)
        c.execute(
            """INSERT INTO football.fixture_identity_resolutions (
                 canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
                 resolution_status,resolution_reason,evidence_json,evidence_sha256,
                 resolution_version,active,created_at)
               VALUES (%s,%s,%s,'AMBIGUOUS_QUARANTINED','PROVISIONAL_PROVIDER_IDENTITY',
                       jsonb_build_object('member_fixture_ids',jsonb_build_array(%s::text)),
                       %s,'test-old-quarantine',true,clock_timestamp())""",
            (fixture, fixture, fixture, fixture, "a" * 64),
        )
        blocked = _cutoff(c)
        assert _eligible(c, blocked) == []
        sync._reconcile_retained_members(row, fixture, snapshot)
        assert len(_eligible(c, _cutoff(c))) == 1
        assert _eligible(c, blocked) == []
        assert len(_eligible(c, admitted)) == 1
        events = c.execute("SELECT count(*) FROM football.fixture_identity_resolutions").fetchone()
        sync._reconcile_retained_members(row, fixture, snapshot)
        assert (
            c.execute("SELECT count(*) FROM football.fixture_identity_resolutions").fetchone()
            == events
        )
        c.execute(
            """UPDATE football.fixture_identity_resolutions SET active=false
               WHERE member_fixture_id=%s""",
            (fixture,),
        )
        c.execute(
            """INSERT INTO football.fixture_identity_resolutions (
                 canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
                 resolution_status,resolution_reason,evidence_json,evidence_sha256,
                 resolution_version,active,created_at)
               VALUES (%s,%s,%s,'AMBIGUOUS_QUARANTINED','CONFLICTING_PROVIDER_RESULTS',
                       jsonb_build_object('member_fixture_ids',jsonb_build_array(%s::text)),
                       %s,'test-real-conflict',true,clock_timestamp())""",
            (fixture, fixture, fixture, fixture, "b" * 64),
        )
        sync._reconcile_retained_members(row, fixture, snapshot)
        assert _eligible(c, _cutoff(c)) == []


def test_scope_cannot_claim_another_sources_conflicting_result_as_qualified(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        conflict = replace(row, home_score=3)
        sync._store_observation(conflict, snapshot, fixture)
        report = sync._season_qualification(snapshot, [conflict], SyncCounts(matched=1))
        assert report["status"] == "BLOCKED_RESULT_CONFLICT"
        assert report["qualified_results"] == 0
        assert (
            sync._season_qualification(uuid4(), [row], SyncCounts(matched=1))["status"]
            == "BLOCKED_IDENTITY"
        )


def test_season_qualification_uses_database_knowledge_clock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import football.product.operational_provider_sync as operational

    class BehindClock(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return datetime.now(UTC) - timedelta(days=1)

    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        sync, fixture, snapshot, row = _review_pair(c, tmp_path)
        sync.apply_reviewed_mapping(row.provider_match_id, fixture, source_snapshot_id=snapshot)
        monkeypatch.setattr(operational, "datetime", BehindClock)
        report = sync._season_qualification(snapshot, [row], SyncCounts(matched=1))
        assert report["status"] == "COMPLETED" and report["qualified_results"] == 1
