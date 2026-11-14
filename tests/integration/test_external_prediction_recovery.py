"""Real-database external imports, correction sequences, bounded work and rollback."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from football.product.external_prediction_recovery import settle_pending_predictions
from football.product.external_predictions import (
    ImportedPrediction,
    import_predictions,
)
from football.product.public_reports import run_pending_public_reports

from tests.integration.test_live_context import FIXTURE, KICKOFF, PROVIDER, SNAPSHOT, _seed_fixture
from tests.integration.test_public_reports import PREDICTION
from tests.integration.test_team_identity_correction import isolated_database


@pytest.fixture
def report_database():
    from tests.integration.test_public_reports import report_database as shared_report_database

    for url in shared_report_database.__wrapped__():
        with psycopg.connect(url) as c:
            c.execute(
                """INSERT INTO football.match_provider_mappings
                (match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,
                 mapping_method,mapping_confidence,source_snapshot_id)
                VALUES(%s,%s,'fixture-native',clock_timestamp(),clock_timestamp(),'manual',1,%s)""",
                (FIXTURE, PROVIDER, SNAPSHOT),
            )
        yield url


def selection(**changes):
    row = ImportedPrediction(
        source_page="https://example.test/owner-supplied",
        prediction_date=KICKOFF.date(),
        original_date_text=KICKOFF.strftime("%d %b %Y"),
        competition="Test League",
        home_team="Home",
        away_team="Away",
        market="RESULT_1X2",
        selection="HOME_WIN",
        provider_code="live_context_test",
        provider_fixture_id="fixture-native",
    )
    return replace(row, **changes)


def settle(connection, **changes):
    return settle_pending_predictions(connection, datetime.now(UTC), **changes)


def test_result_corrections_return_to_an_earlier_state_without_rewriting_history(report_database):
    with psycopg.connect(report_database) as c:
        original = c.execute("SELECT to_jsonb(ep) FROM football.external_predictions ep").fetchone()
        c.commit()
        assert settle(c, limit=1) == 1
        for status, home, away in (
            ("FINISHED", 0, 3),
            ("SCHEDULED", None, None),
            ("CANCELLED", None, None),
            ("FINISHED", 2, 1),
        ):
            c.execute(
                "UPDATE football.product_fixtures SET status=%s,home_score=%s,away_score=%s "
                "WHERE fixture_id=%s",
                (status, home, away, FIXTURE),
            )
            c.commit()
            assert settle_pending_predictions(c, KICKOFF - timedelta(days=100), limit=1) == 1
        rows = c.execute(
            "SELECT settlement_state,revision_sequence,previous_result_revision_id FROM "
            "football.external_prediction_result_revisions WHERE prediction_id=%s ORDER BY "
            "revision_sequence",
            (PREDICTION,),
        ).fetchall()
        assert [row[0] for row in rows] == ["WON", "LOST", "PENDING", "VOID", "WON"]
        assert [row[1] for row in rows] == [1, 2, 3, 4, 5]
        assert rows[0][2] is None and all(row[2] for row in rows[1:])
        assert c.execute(
            "SELECT correct FROM football.external_prediction_results WHERE prediction_id=%s",
            (PREDICTION,),
        ).fetchone() == (True,)
        assert (
            c.execute("SELECT to_jsonb(ep) FROM football.external_predictions ep").fetchone()
            == original
        )
        c.commit()
        assert settle(c) == 0


def test_late_import_uses_normal_report_worker_without_provider_sync(report_database):
    row = selection()
    with psycopg.connect(report_database) as c:
        assert import_predictions(c, (row,), collected_at=KICKOFF - timedelta(hours=3)) == 1
        original = c.execute(
            "SELECT collected_at FROM football.external_predictions WHERE "
            "source_code='manual_import'"
        ).fetchone()
        c.commit()
        assert import_predictions(c, (row,), collected_at=datetime.now(UTC)) == 0
        assert (
            c.execute(
                "SELECT collected_at FROM football.external_predictions WHERE "
                "source_code='manual_import'"
            ).fetchone()
            == original
        )
        c.commit()
        result = run_pending_public_reports(
            c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64
        )
        assert result["external_settlement_revisions"] == 2
        assert c.execute(
            "SELECT result.settlement_state FROM football.external_prediction_latest_results "
            "result JOIN football.external_predictions ep USING(prediction_id) WHERE "
            "ep.source_code='manual_import'"
        ).fetchone() == ("WON",)


def test_identical_unmatched_import_can_acquire_verified_mapping_append_only(report_database):
    row = selection(
        home_team="Unmatched source label",
        provider_code="live_context_test",
        provider_fixture_id="future-native-match",
    )
    with psycopg.connect(report_database) as c:
        assert import_predictions(c, (row,), collected_at=KICKOFF - timedelta(hours=3)) == 1
        original = c.execute(
            "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE "
            "source_code='manual_import'"
        ).fetchone()
        assert original[0]["fixture_id"] is None
        mapping = uuid4()
        c.execute(
            """INSERT INTO football.match_provider_mappings
            (id,match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,
             mapping_method,mapping_confidence,source_snapshot_id)
            VALUES(%s,%s,%s,'future-native-match',clock_timestamp(),clock_timestamp(),'manual',1,%s)""",
            (mapping, FIXTURE, PROVIDER, SNAPSHOT),
        )
        c.commit()
        assert import_predictions(c, (row,), collected_at=datetime.now(UTC)) == 0
        assert c.execute(
            "SELECT effective_fixture_id,effective_match_status FROM "
            "football.external_prediction_effective WHERE source_code='manual_import'"
        ).fetchone() == (FIXTURE, "MATCHED")
        assert (
            c.execute(
                "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE "
                "source_code='manual_import'"
            ).fetchone()
            == original
        )
        assert c.execute(
            "SELECT mapping_id FROM football.external_prediction_bindings"
        ).fetchone() == (mapping,)
        c.commit()
        settle(c)
        assert (
            c.execute(
                "SELECT count(*) FROM football.external_prediction_latest_results WHERE "
                "settlement_state='WON'"
            ).fetchone()[0]
            == 2
        )


def test_bounded_concurrent_workers_and_rollback_converge(report_database):
    rows = tuple(
        selection(
            source_page=f"https://example.test/{index}",
            selection="DRAW" if index % 2 else "HOME_WIN",
        )
        for index in range(9)
    )
    with psycopg.connect(report_database) as c:
        assert import_predictions(c, rows, collected_at=KICKOFF - timedelta(hours=3)) == 9
        with c.transaction(force_rollback=True):
            assert settle(c, limit=2) == 2
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_result_revisions"
        ).fetchone() == (0,)
        c.commit()

    def batch(_):
        with psycopg.connect(report_database) as c:
            return settle(c, limit=3)

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sum(workers.map(batch, range(2))) <= 6
    with psycopg.connect(report_database) as c:
        for _ in range(5):
            settle(c, limit=3)
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_result_revisions"
        ).fetchone() == (10,)
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_refresh_work WHERE "
            "generation>completed_generation"
        ).fetchone() == (0,)
        c.commit()
        assert settle(c, limit=3) == 0


def test_wrong_retained_source_date_is_quarantined_without_changing_capture(report_database):
    row = selection(
        original_date_text=(KICKOFF - timedelta(days=1)).strftime("Predictions %d %b %Y")
    )
    with psycopg.connect(report_database) as c:
        assert (
            import_predictions(
                c, (row,), source_code="tips1960", collected_at=KICKOFF - timedelta(hours=3)
            )
            == 1
        )
        before = c.execute(
            "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE source_code='tips1960'"
        ).fetchone()
        c.commit()
        settle(c)
        assert c.execute(
            "SELECT date_status FROM football.external_prediction_effective WHERE "
            "source_code='tips1960'"
        ).fetchone() == ("MISMATCH",)
        assert c.execute(
            "SELECT settlement_state FROM football.external_prediction_latest_results result "
            "JOIN football.external_predictions ep USING(prediction_id) WHERE "
            "source_code='tips1960'"
        ).fetchone() == ("PENDING",)
        assert (
            c.execute(
                "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE "
                "source_code='tips1960'"
            ).fetchone()
            == before
        )


def test_paginated_go_reader_and_source_aggregates_share_current_settlement_policy(report_database):
    import os
    import subprocess

    from tests.integration.test_product_analytics import _revision

    r2_date = f"{KICKOFF.day}th, {KICKOFF:%a %b %Y}"
    tips_date = KICKOFF.strftime("Predictions %d %b %Y")
    with psycopg.connect(report_database) as c:
        _revision(c, 24)
        _revision(c, 6)
        c.commit()
        captured = c.execute("SELECT clock_timestamp()").fetchone()[0]
        c.commit()
        import_predictions(
            c,
            (selection(original_date_text=r2_date, selection="DRAW"),),
            source_code="r2bet",
            collected_at=captured,
        )
        import_predictions(
            c,
            (selection(original_date_text=r2_date),),
            source_code="r2bet",
            collected_at=captured + timedelta(microseconds=1),
        )
        import_predictions(
            c,
            (selection(original_date_text=tips_date),),
            source_code="tips1960",
            collected_at=captured + timedelta(microseconds=2),
        )
        import_predictions(
            c,
            (
                selection(
                    original_date_text=r2_date, market="TOTAL_GOALS", selection="TOTAL_OVER_2_5"
                ),
            ),
            source_code="r2bet",
            collected_at=KICKOFF,
        )
        import_predictions(
            c,
            tuple(
                selection(
                    home_team=f"Unknown {index}", provider_code=None, provider_fixture_id=None
                )
                for index in range(25)
            ),
            collected_at=captured,
        )
        outcome = run_pending_public_reports(
            c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64
        )
        assert outcome["failed"] == 0

    def go(name):
        result = subprocess.run(
            ["go", "test", "./internal/app", "-run", f"^{name}$", "-count=1", "-v"],
            cwd="go/api",
            env={**os.environ, "TEST_DATABASE_URL": report_database},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    go("TestExternalPredictionReadersDatabase")
    with psycopg.connect(report_database) as c:
        run_pending_public_reports(c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64)
    go("TestExternalPredictionCorrectedMetricsDatabase")


def test_native_mapping_failure_never_falls_back_to_team_names(report_database):
    with psycopg.connect(report_database) as c:
        row = selection(provider_code="live_context_test", provider_fixture_id="missing-native-id")
        assert import_predictions(c, (row,), collected_at=datetime.now(UTC)) == 1
        assert c.execute(
            "SELECT fixture_id,match_status FROM football.external_predictions WHERE "
            "source_code='manual_import'"
        ).fetchone() == (None, "UNMATCHED")


def test_collection_records_failure_and_disabled_health_separately(report_database):
    from football.product.cli import _collection_status, _persist_collections
    from football.product.external_prediction_sources import SourceCollection

    results = [
        SourceCollection(
            "slybet", "https://example.test", "PARSER_BROKEN", error="synthetic parse failure"
        ),
        SourceCollection(
            "forebet",
            "https://example.test",
            "TECHNICALLY_UNAVAILABLE",
            error="intentionally disabled",
        ),
    ]
    with psycopg.connect(report_database) as c:
        updated, count = _persist_collections(c, results, KICKOFF.date())
        assert count == 0 and _collection_status(updated) == "FAILED"
        assert c.execute(
            "SELECT source_code,attempted,status FROM "
            "football.external_prediction_collection_attempts ORDER BY source_code"
        ).fetchall() == [
            ("forebet", False, "TECHNICALLY_UNAVAILABLE"),
            ("slybet", True, "PARSER_BROKEN"),
        ]


def test_date_review_requeues_an_already_completed_comparison_generation(report_database):
    from football.product.domain import stable_id

    from tests.integration.test_public_reports import build

    row = selection(original_date_text=f"{KICKOFF.day}th, {KICKOFF:%a %b %Y}")
    with psycopg.connect(report_database) as c:
        import_predictions(c, (row,), source_code="r2bet", collected_at=datetime.now(UTC))
        from football.product.external_predictions import prediction_revision_sha256

        prediction_id = stable_id("external-prediction", prediction_revision_sha256("r2bet", row))
        before = c.execute(
            "SELECT football.public_comparison_source(%s)", (prediction_id,)
        ).fetchone()[0]
        assert before["forecast_id"] is None
    assert build(report_database, "COMPARISON", prediction_id)["published"] == 1
    with psycopg.connect(report_database) as c:
        c.execute(
            "UPDATE football.product_report_refresh_work SET "
            "completed_generation=generation WHERE report_kind='COMPARISON' AND "
            "scope_id=%s",
            (prediction_id,),
        )
        c.commit()
        settle(c)
        assert c.execute(
            "SELECT generation>completed_generation FROM "
            "football.product_report_refresh_work WHERE report_kind='COMPARISON' "
            "AND scope_id=%s",
            (prediction_id,),
        ).fetchone() == (True,)
        after = c.execute(
            "SELECT football.public_comparison_source(%s)", (prediction_id,)
        ).fetchone()[0]
        assert after["forecast_id"] is not None


def test_identical_pick_recapture_tracks_current_revision_and_preserves_first_capture(
    report_database,
):
    row = selection()
    first = datetime.now(UTC) - timedelta(minutes=10)
    with psycopg.connect(report_database) as c:
        import_predictions(c, (row,), collected_at=first)
        import_predictions(
            c, (selection(selection="AWAY_WIN"),), collected_at=first + timedelta(minutes=1)
        )
        import_predictions(c, (row,), collected_at=first + timedelta(minutes=2))
        state = c.execute(
            "SELECT selection,collected_at,last_observed_at,revision_started_at "
            "FROM football.external_prediction_current WHERE "
            "source_code='manual_import'"
        ).fetchone()
        assert state == (
            "HOME_WIN",
            first,
            first + timedelta(minutes=2),
            first + timedelta(minutes=2),
        )
        assert c.execute(
            "SELECT count(*) FROM football.external_predictions WHERE source_code='manual_import'"
        ).fetchone() == (2,)
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_captures capture "
            "JOIN football.external_predictions ep USING(prediction_id) WHERE "
            "source_code='manual_import'"
        ).fetchone() == (3,)


def test_same_time_conflicting_source_picks_never_create_consensus_or_accuracy_credit(
    report_database,
):
    from tests.integration.test_product_analytics import _revision

    date_text = f"{KICKOFF.day}th, {KICKOFF:%a %b %Y}"
    with psycopg.connect(report_database) as c:
        _revision(c, 24)
        _revision(c, 6)
        c.commit()
        # Order these captures after the database-seeded fixture without
        # depending on agreement between the host and PostgreSQL clocks.
        captured = c.execute("SELECT clock_timestamp()").fetchone()[0]
        import_predictions(
            c,
            (
                selection(source_page="https://example.test/tie-a", original_date_text=date_text),
                selection(
                    source_page="https://example.test/tie-b",
                    original_date_text=date_text,
                    selection="AWAY_WIN",
                ),
            ),
            source_code="r2bet",
            collected_at=captured,
        )
        import_predictions(
            c,
            (selection(original_date_text=KICKOFF.strftime("Predictions %d %b %Y")),),
            source_code="tips1960",
            collected_at=captured,
        )
        run_pending_public_reports(c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64)
        assert c.execute(
            "SELECT source_revision_conflict FROM "
            "football.external_prediction_current WHERE source_code='r2bet'"
        ).fetchone() == (True,)
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_current WHERE "
            "source_code='r2bet' AND NOT source_revision_conflict"
        ).fetchone() == (0,)


def test_large_current_archive_retains_bounded_api_pages(report_database):
    import os
    import subprocess

    with psycopg.connect(report_database) as c:
        c.execute("""INSERT INTO football.external_predictions
            (prediction_id,revision_sha256,source_code,source_page,prediction_date,original_date_text,
             collected_at,competition_text,home_team_text,away_team_text,market,selection,match_status)
            SELECT uuidv7(),md5(n::text)||md5(n::text),'manual_import','archive-'||n,CURRENT_DATE,
             CURRENT_DATE::text,clock_timestamp(),'Synthetic','Home '||n,'Away '||n,
             'RESULT_1X2','HOME_WIN','UNMATCHED' FROM generate_series(1,5000) n""")
    result = subprocess.run(
        [
            "go",
            "test",
            "./internal/app",
            "-run",
            "^TestExternalPrediction(ArchiveBound|ContinuousArchive)Database$",
            "-count=1",
            "-v",
        ],
        cwd="go/api",
        env=os.environ | {"TEST_DATABASE_URL": report_database},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)


def test_reviewed_capture_without_native_ids_can_bind_and_revoke_append_only(report_database):
    import os
    import subprocess
    import sys

    from football.product.external_prediction_recovery import bind_reviewed_prediction

    captured = datetime.now(UTC) - timedelta(hours=2)
    with psycopg.connect(report_database) as c:
        row = selection(
            home_team="Unresolved source label",
            prediction_date=captured.date(),
            provider_code=None,
            provider_fixture_id=None,
        )
        import_predictions(c, (row,), collected_at=captured)
        original = c.execute(
            "SELECT to_jsonb(ep) FROM football.external_predictions ep "
            "WHERE source_code='manual_import'"
        ).fetchone()[0]
        prediction = original["prediction_id"]
        mapping = uuid4()
        c.execute(
            """UPDATE football.product_fixtures SET kickoff_at=clock_timestamp()-interval '1 hour'
            WHERE fixture_id=%s""",
            (FIXTURE,),
        )
        c.execute(
            """INSERT INTO football.match_provider_mappings
            (id,match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,
             mapping_method,mapping_confidence,source_snapshot_id)
            VALUES(%s,%s,%s,'reviewed-native-match',clock_timestamp(),clock_timestamp(),'manual',1,%s)""",
            (mapping, FIXTURE, PROVIDER, SNAPSHOT),
        )
        c.commit()
        command = [
            sys.executable,
            "-m",
            "football.product.cli",
            "--database-url",
            report_database,
            "external-binding-review",
            "--prediction-id",
            prediction,
            "--mapping-id",
            str(mapping),
            "--reason",
            "synthetic retained native-ID review",
        ]
        for state in ("BOUND", "UNCHANGED"):
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=30, env=os.environ
            )
            assert result.returncode == 0, result.stderr
            assert f'"status": "{state}"' in result.stdout
        run_pending_public_reports(c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64)
        assert c.execute(
            "SELECT effective_fixture_id FROM football.external_prediction_effective "
            "WHERE prediction_id=%s",
            (prediction,),
        ).fetchone() == (FIXTURE,)
        c.commit()
        result = subprocess.run(
            [
                "go",
                "test",
                "./internal/app",
                "-run",
                "^TestReviewedExternalAccuracyDatabase$",
                "-count=1",
            ],
            cwd="go/api",
            env=os.environ | {"TEST_DATABASE_URL": report_database},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        c.execute(
            "UPDATE football.match_provider_mappings SET mapping_confidence=0 WHERE id=%s",
            (mapping,),
        )
        c.commit()
        with pytest.raises(ValueError), c.transaction():
            bind_reviewed_prediction(c, prediction, mapping, reason="revoked mapping cannot bind")
        run_pending_public_reports(c, code_commit_sha="f" * 40, dependency_lock_sha256="d" * 64)
        assert c.execute(
            "SELECT effective_fixture_id FROM football.external_prediction_effective "
            "WHERE prediction_id=%s",
            (prediction,),
        ).fetchone() == (None,)
        assert (
            c.execute(
                "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE prediction_id=%s",
                (prediction,),
            ).fetchone()[0]
            == original
        )
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_bindings WHERE prediction_id=%s",
            (prediction,),
        ).fetchone() == (2,)


def test_manual_settlement_revisits_completed_work_across_entire_history(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    with psycopg.connect(report_database) as c:
        assert settle(c) == 1
        c.execute(
            """INSERT INTO football.external_predictions
            (prediction_id,revision_sha256,source_code,source_page,prediction_date,
             original_date_text,collected_at,fixture_id,competition_text,home_team_text,
             away_team_text,market,selection,match_status)
            SELECT id,encode(sha256(convert_to(id::text,'UTF8')),'hex'), 'manual_import',
                'archive/'||id,DATE '2001-01-01','2001-01-01',TIMESTAMPTZ '2001-01-01 12:00Z',
                %s,'Test','Home','Away','RESULT_1X2','AWAY_WIN','MATCHED'
            FROM (SELECT uuidv7() AS id FROM generate_series(1,129)) rows""",
            (FIXTURE,),
        )
        c.execute(
            """UPDATE football.external_prediction_refresh_work
            SET completed_generation=generation,completed_at=clock_timestamp()"""
        )
        c.commit()

        inventory = reconcile_external_predictions(c, datetime.now(UTC), audit_only=True)
        assert inventory["counts"] == {"ALREADY_SETTLED": 1, "ELIGIBLE": 129}
        summary = reconcile_external_predictions(c, datetime.now(UTC))
        assert summary["counts"] == {"ALREADY_SETTLED": 1, "NEWLY_SETTLED": 129}
        assert summary["examined"] == 130
        retry = reconcile_external_predictions(c, datetime.now(UTC))
        assert retry["counts"] == {"ALREADY_SETTLED": 130}
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_result_revisions"
        ).fetchone() == (130,)


def test_manual_settlement_reports_conflicts_and_preserves_finalized_revision(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    with psycopg.connect(report_database) as c:
        assert settle(c) == 1
        c.execute(
            "UPDATE football.product_fixtures SET home_score=0,away_score=3 WHERE fixture_id=%s",
            (FIXTURE,),
        )
        c.commit()
        summary = reconcile_external_predictions(c, datetime.now(UTC))
        assert summary["counts"] == {"FINALIZED_NEEDS_REVIEW": 1}
        assert c.execute(
            "SELECT settlement_state FROM football.external_prediction_latest_results"
        ).fetchall() == [("WON",)]
        c.commit()
        assert settle(c) == 1  # Existing correction workflow appends the revised outcome.
        assert c.execute(
            "SELECT settlement_state FROM football.external_prediction_latest_results"
        ).fetchall() == [("LOST",)]


def test_manual_settlement_leaves_conflicting_provider_results_pending(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    with psycopg.connect(report_database) as c:
        c.execute(
            """INSERT INTO football.product_source_result_conflicts
            (canonical_match_id,existing_provider_code,existing_home_goals,existing_away_goals,
             existing_snapshot_id,incoming_provider_code,incoming_home_goals,incoming_away_goals,
             incoming_snapshot_id,conflict_key)
            VALUES(%s,'a',2,1,%s,'b',1,2,%s,%s)""",
            (FIXTURE, SNAPSHOT, SNAPSHOT, "a" * 64),
        )
        c.commit()
        assert reconcile_external_predictions(c, datetime.now(UTC))["counts"] == {
            "RESULT_CONFLICT": 1
        }
        assert c.execute(
            "SELECT settlement_state FROM football.external_prediction_latest_results"
        ).fetchall() == [("PENDING",)]


def test_manual_settlement_resumes_after_a_row_fails(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    with psycopg.connect(report_database) as c:
        assert import_predictions(c, (selection(selection="AWAY_WIN"),)) == 1
        c.execute(
            """CREATE FUNCTION football.test_block_one_settlement() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
                IF NEW.prediction_id='00000000-0000-0000-0000-000000002332' THEN
                    RAISE EXCEPTION 'synthetic failed append';
                END IF;
                RETURN NEW;
            END $$"""
        )
        c.execute(
            """CREATE TRIGGER test_block_one_settlement BEFORE INSERT
            ON football.external_prediction_result_revisions
            FOR EACH ROW EXECUTE FUNCTION football.test_block_one_settlement()"""
        )
        c.commit()
        assert reconcile_external_predictions(c, datetime.now(UTC))["counts"] == {
            "FAILED": 1,
            "NEWLY_SETTLED": 1,
        }
        c.execute(
            "DROP TRIGGER test_block_one_settlement ON "
            "football.external_prediction_result_revisions"
        )
        c.commit()
        assert reconcile_external_predictions(c, datetime.now(UTC))["counts"] == {
            "ALREADY_SETTLED": 1,
            "NEWLY_SETTLED": 1,
        }


def test_manual_and_scheduled_settlement_converge(report_database):
    from threading import Barrier

    from football.product.external_prediction_recovery import reconcile_external_predictions

    start = Barrier(2)

    def scheduled():
        with psycopg.connect(report_database) as c:
            start.wait(timeout=10)
            return settle(c)

    def manual():
        with psycopg.connect(report_database) as c:
            start.wait(timeout=10)
            return reconcile_external_predictions(c, datetime.now(UTC))["counts"]

    with ThreadPoolExecutor(max_workers=2) as workers:
        automatic = workers.submit(scheduled)
        manual_run = workers.submit(manual)
        assert (
            automatic.result(timeout=15) + manual_run.result(timeout=15).get("NEWLY_SETTLED", 0)
            == 1
        )
    with psycopg.connect(report_database) as c:
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_result_revisions"
        ).fetchone() == (1,)


def _provider_only_result(c, status, observed_at, *, home_id="101", away_id="102"):
    c.execute(
        """INSERT INTO football.product_provider_fixture_observations
        (semantic_sha256,provider_code,provider_match_id,provider_competition_id,
         provider_home_team_id,provider_away_team_id,source_snapshot_id,kickoff_at,
         canonical_status,home_score,away_score,observed_at,stale_after,last_fetched_at,
         result_score_basis)
        VALUES(%s,'live_context_test','provider-only','league',%s,%s,%s,%s,%s,
               %s,%s,%s,%s,%s,%s)""",
        (
            uuid4().hex * 2,
            home_id,
            away_id,
            SNAPSHOT,
            observed_at - timedelta(hours=3),
            status,
            2 if status == "FINISHED" else None,
            1 if status == "FINISHED" else None,
            observed_at,
            observed_at,
            observed_at,
            "REGULATION_90" if status == "FINISHED" else "UNKNOWN",
        ),
    )


def test_provider_only_late_import_and_manual_and_automatic_settlement_without_forecasts():
    from football.product.external_prediction_recovery import reconcile_external_predictions

    observed = datetime.now(UTC) - timedelta(hours=1)
    with isolated_database() as url, psycopg.connect(url) as c:
        _seed_fixture(c)
        c.execute(
            "UPDATE football.source_snapshots SET acquired_at=%s WHERE id=%s",
            (observed, SNAPSHOT),
        )
        c.commit()
        row = selection(
            prediction_date=(observed - timedelta(hours=3)).date(),
            provider_fixture_id="provider-only",
        )
        assert import_predictions(c, (row,)) == 1
        assert settle(c) == 1
        _provider_only_result(c, "FINISHED", observed)
        c.commit()
        assert settle(c) == 1  # Native observation enqueues the previously completed work item.
        assert c.execute(
            """SELECT settlement_state,evidence->>'fixture_association',
                evidence->>'native_snapshot_id' FROM football.external_prediction_latest_results"""
        ).fetchone() == ("WON", "VERIFIED_PROVIDER_ONLY", str(SNAPSHOT))
        c.commit()
        assert import_predictions(c, (replace(row, selection="AWAY_WIN"),)) == 1
        summary = reconcile_external_predictions(c, datetime.now(UTC))
        assert summary["counts"] == {"ALREADY_SETTLED": 1, "NEWLY_SETTLED": 1}
        assert summary["associations"] == {"VERIFIED_PROVIDER_ONLY": 2}
        assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (0,)
        assert c.execute("SELECT count(*) FROM football.product_fixtures").fetchone() == (1,)
        c.execute(
            """UPDATE football.product_fixtures
            SET identity_status='VERIFIED',status='FINISHED',home_score=2,away_score=1,
                result_score_basis='REGULATION_90',kickoff_at=%s
            WHERE fixture_id=%s""",
            (observed - timedelta(hours=3), FIXTURE),
        )
        c.execute(
            """INSERT INTO football.match_provider_mappings
            (match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,
             mapping_method,mapping_confidence,source_snapshot_id)
            VALUES(%s,%s,'provider-only',clock_timestamp(),clock_timestamp(),'manual',1,%s)""",
            (FIXTURE, PROVIDER, SNAPSHOT),
        )
        c.commit()
        assert settle(c) == 2
        assert c.execute(
            """SELECT count(*) FROM football.external_prediction_effective
               WHERE effective_fixture_id=%s""",
            (FIXTURE,),
        ).fetchone() == (2,)
        assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (0,)


def test_unreferenced_labels_do_not_establish_fixture_identity(report_database):
    with psycopg.connect(report_database) as c:
        assert (
            import_predictions(c, (selection(provider_code=None, provider_fixture_id=None),)) == 1
        )
        assert c.execute(
            """SELECT effective_fixture_id,effective_match_status
            FROM football.external_prediction_effective WHERE source_code='manual_import'"""
        ).fetchone() == (None, "UNMATCHED")


def test_archived_r2bet_capture_recovers_verified_native_identity(report_database, tmp_path):
    from football.product.external_prediction_history import recover_external_prediction_bindings
    from football.product.external_prediction_sources import parse_r2bet

    page = "https://r2bet.com/index.php/best_football_prediction?dt=2030-01-01"
    raw = """<section><h2>Best Picks</h2><p>1st, Tue Jan 2030</p>
    <article><div data-link="/index.php/match-details/123-free/home-vs-away">
    <p>Test League</p><p>19:00</p></div><p>Home</p><p>Away</p><p>Odds: 1.5</p>
    <p>Pick: 1</p></article></section>"""
    (tmp_path / "r2bet-2030-01-01.html").write_text(raw)
    recovered = parse_r2bet(raw, KICKOFF.date(), page)[0]
    original = replace(recovered, fixture_reference_url=None, source_kickoff_text=None)
    with psycopg.connect(report_database) as c:
        c.execute("UPDATE football.providers SET code='api_football' WHERE id=%s", (PROVIDER,))
        c.execute(
            "UPDATE football.match_provider_mappings SET provider_match_id='123' "
            "WHERE provider_id=%s",
            (PROVIDER,),
        )
        c.commit()
        assert import_predictions(c, (original,), source_code="r2bet") == 1
        preview = recover_external_prediction_bindings(c, tmp_path, audit_only=True)
        assert preview["counts"] == {"PAGES_VERIFIED": 1, "BINDING_ELIGIBLE": 1}
        apply = recover_external_prediction_bindings(c, tmp_path, audit_only=False)
        assert apply["counts"] == {"PAGES_VERIFIED": 1, "BOUND": 1}
        retry = recover_external_prediction_bindings(c, tmp_path, audit_only=False)
        assert not retry["predictions"]
        assert c.execute(
            """SELECT effective_fixture_id FROM football.external_prediction_effective
               WHERE source_code='r2bet' AND source_page=%s""",
            (page,),
        ).fetchone() == (FIXTURE,)


def test_recapture_enriches_r2bet_revision_and_holds_conflicting_reference(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    original = selection(
        source_page="https://r2bet.com/index.php/best_football_prediction?dt=2030-01-01",
        original_date_text="1st, Tue Jan 2030",
        provider_code=None,
        provider_fixture_id=None,
    )
    enriched = replace(
        original,
        fixture_reference_url="https://r2bet.com/index.php/match-details/123-free/home-vs-away",
        source_kickoff_text="19:00",
    )
    observed = KICKOFF - timedelta(hours=3)
    with psycopg.connect(report_database) as c:
        c.execute("UPDATE football.providers SET code='api_football' WHERE id=%s", (PROVIDER,))
        c.commit()
        assert import_predictions(c, (original,), source_code="r2bet", collected_at=observed) == 1
        prediction, retained = c.execute(
            "SELECT prediction_id,to_jsonb(ep) FROM football.external_predictions ep "
            "WHERE source_code='r2bet' AND source_page=%s",
            (original.source_page,),
        ).fetchone()
        c.commit()
        assert import_predictions(c, (enriched,), source_code="r2bet", collected_at=observed) == 0
        assert c.execute(
            """SELECT fixture_reference_url,source_kickoff_text,observed_at
            FROM football.external_prediction_fixture_evidence WHERE prediction_id=%s""",
            (prediction,),
        ).fetchall() == [(enriched.fixture_reference_url, "19:00", observed)]
        c.commit()
        settle(c)
        c.execute(
            "UPDATE football.match_provider_mappings SET provider_match_id='123' "
            "WHERE provider_id=%s",
            (PROVIDER,),
        )
        c.commit()
        settle(c)
        binding = c.execute(
            """SELECT binding_id,effective_fixture_id
            FROM football.external_prediction_effective WHERE prediction_id=%s""",
            (prediction,),
        ).fetchone()
        assert binding[1] == FIXTURE
        assert c.execute(
            """SELECT settlement_state FROM football.external_prediction_latest_results
            WHERE prediction_id=%s""",
            (prediction,),
        ).fetchone() == ("WON",)
        generation = c.execute(
            "SELECT generation FROM football.external_prediction_refresh_work "
            "WHERE prediction_id=%s",
            (prediction,),
        ).fetchone()
        c.commit()
        assert import_predictions(c, (enriched,), source_code="r2bet", collected_at=observed) == 0
        assert (
            c.execute(
                "SELECT generation FROM football.external_prediction_refresh_work "
                "WHERE prediction_id=%s",
                (prediction,),
            ).fetchone()
            == generation
        )
        assert c.execute(
            "SELECT to_jsonb(ep) FROM football.external_predictions ep WHERE prediction_id=%s",
            (prediction,),
        ).fetchall() == [(retained,)]
        c.commit()
        conflict = replace(
            enriched,
            fixture_reference_url="https://r2bet.com/index.php/match-details/456-free/home-vs-away",
        )
        assert import_predictions(c, (conflict,), source_code="r2bet", collected_at=observed) == 0
        audit = reconcile_external_predictions(c, datetime.now(UTC), audit_only=True)
        assert (
            next(item for item in audit["predictions"] if item["prediction_id"] == str(prediction))[
                "association"
            ]
            == "IDENTITY_CONFLICT"
        )
        assert (
            c.execute(
                """SELECT binding_id,effective_fixture_id
            FROM football.external_prediction_effective WHERE prediction_id=%s""",
                (prediction,),
            ).fetchone()
            == binding
        )


def test_concurrent_native_evidence_import_keeps_one_prediction(report_database):
    from threading import Barrier

    original = selection(provider_code=None, provider_fixture_id=None)
    enriched = selection()
    observed = KICKOFF - timedelta(hours=1)
    start = Barrier(2)

    def ingest(row):
        with psycopg.connect(report_database) as c:
            start.wait(timeout=10)
            return import_predictions(c, (row,), collected_at=observed)

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sum(workers.map(ingest, (original, enriched))) == 1
    with psycopg.connect(report_database) as c:
        assert c.execute(
            """SELECT effective_fixture_id FROM football.external_prediction_effective
            WHERE source_code='manual_import'"""
        ).fetchall() == [(FIXTURE,)]
        assert c.execute(
            """SELECT provider_code,provider_fixture_id FROM
            football.external_prediction_fixture_evidence"""
        ).fetchall() == [("live_context_test", "fixture-native")]


def test_inventory_validates_source_date_before_reconciliation(report_database):
    from football.product.external_prediction_recovery import reconcile_external_predictions

    row = selection(original_date_text="1st, Tue Jan 2030")
    with psycopg.connect(report_database) as c:
        assert import_predictions(c, (row,), source_code="r2bet") == 1
        c.read_only = True
        audit = reconcile_external_predictions(c, datetime.now(UTC), audit_only=True)
        assert audit["counts"] == {"ELIGIBLE": 2}
        assert c.execute(
            "SELECT count(*) FROM football.external_prediction_date_reviews "
            "WHERE prediction_id<>%s",
            (PREDICTION,),
        ).fetchone() == (0,)
        c.commit()
        c.read_only = False
        result = reconcile_external_predictions(c, datetime.now(UTC))
        assert result["counts"] == {"NEWLY_SETTLED": 2}
        assert {row["prediction_id"] for row in audit["predictions"]} == set(
            result["changed_prediction_ids"]
        )


def test_exact_archive_can_follow_a_reviewed_post_kickoff_fixture_replacement(report_database):
    from football.product.external_predictions import verified_r2bet_mapping
    from psycopg.types.json import Jsonb

    original, replacement, decision = uuid4(), uuid4(), uuid4()
    kickoff = datetime(2026, 10, 3, 18, tzinfo=UTC)
    reviewed_at = kickoff + timedelta(days=1)
    row = selection(
        prediction_date=kickoff.date(),
        original_date_text="3rd, Sat Oct 2026",
        provider_code=None,
        provider_fixture_id=None,
        fixture_reference_url="https://r2bet.com/index.php/match-details/123-free/home-vs-away",
        source_kickoff_text="19:00",
    )
    with psycopg.connect(report_database) as c:
        c.execute("UPDATE football.providers SET code='api_football' WHERE id=%s", (PROVIDER,))
        c.execute(
            "UPDATE football.product_fixtures SET kickoff_at=%s WHERE fixture_id=%s",
            (
                kickoff,
                FIXTURE,
            ),
        )
        c.execute(
            """INSERT INTO football.matches (id,competition_id,season_id)
            SELECT %s,competition_id,season_id FROM football.matches WHERE id=%s""",
            (original, FIXTURE),
        )
        c.execute(
            """INSERT INTO football.product_fixtures
            (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
             forecast_availability,identity_status,updated_at)
            SELECT %s,competition_id,home_team_id,away_team_id,kickoff_at,'SCHEDULED',
                forecast_availability,identity_status,updated_at
            FROM football.product_fixtures WHERE fixture_id=%s""",
            (original, FIXTURE),
        )
        c.execute(
            """INSERT INTO football.match_provider_mappings
            (id,match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,valid_from,valid_to,
             mapping_method,mapping_confidence,source_snapshot_id)
            VALUES(uuidv7(),%s,%s,'123',%s,%s,NULL,%s,'deterministic',1,%s),
                  (%s,%s,%s,'123',%s,%s,%s,NULL,'manual',1,%s)""",
            (
                original,
                PROVIDER,
                reviewed_at,
                reviewed_at,
                reviewed_at,
                SNAPSHOT,
                replacement,
                FIXTURE,
                PROVIDER,
                reviewed_at,
                reviewed_at,
                reviewed_at,
                SNAPSHOT,
            ),
        )
        c.execute(
            """INSERT INTO football.product_provider_mapping_decisions
            (decision_id,semantic_sha256,provider_code,provider_match_id,candidate_fixture_id,
             disposition,reason,evidence,source_snapshot_id,observed_at)
            VALUES(%s,%s,'api_football','123',%s,'AUTO_ACCEPTED','Reviewed fixture',%s,%s,%s)""",
            (
                decision,
                uuid4().hex * 2,
                FIXTURE,
                Jsonb({"rule": "admitted_competition_home_away_exact_kickoff_native_fixture_id"}),
                SNAPSHOT,
                reviewed_at,
            ),
        )
        c.execute(
            """INSERT INTO football.fixture_identity_resolutions
            (canonical_real_fixture_id,member_fixture_id,representative_fixture_id,
             resolution_status,resolution_reason,evidence_json,evidence_sha256,
             resolution_version,created_at)
            VALUES(%s,%s,%s,'DUPLICATE_RESOLVED','Reviewed fixture',%s,%s,'test',%s)""",
            (
                FIXTURE,
                original,
                FIXTURE,
                Jsonb(
                    {
                        "provider_mapping_decision_id": str(decision),
                        "provider": "api_football",
                        "provider_match_id": "123",
                        "source_snapshot_id": str(SNAPSHOT),
                        "original_fixture_id": str(original),
                        "reviewed_fixture_id": str(FIXTURE),
                    }
                ),
                uuid4().hex * 2,
                reviewed_at,
            ),
        )
        assert verified_r2bet_mapping(c, row) == replacement
        c.commit()
        assert import_predictions(c, (row,), source_code="r2bet", collected_at=kickoff) == 1
        assert settle(c) == 2
        assert c.execute(
            """SELECT binding.mapping_id,result.settlement_state
            FROM football.external_predictions ep
            JOIN football.external_prediction_bindings binding USING (prediction_id)
            JOIN football.external_prediction_latest_results result USING (prediction_id)
            WHERE ep.source_page=%s""",
            (row.source_page,),
        ).fetchone() == (replacement, "WON")
        c.execute(
            "UPDATE football.fixture_identity_resolutions SET active=false "
            "WHERE member_fixture_id=%s",
            (original,),
        )
        assert c.execute(
            "SELECT count(*) FROM football.external_reviewed_fixture_mappings WHERE mapping_id=%s",
            (replacement,),
        ).fetchone() == (0,)


def test_result_recovery_settles_without_internal_forecast():
    from football.product.result_recovery import finish_result_recovery

    from tests.integration.test_live_context import _seed_fixture
    from tests.integration.test_team_identity_correction import isolated_database

    with isolated_database() as url, psycopg.connect(url) as connection:
        _seed_fixture(connection)
        assert (
            import_predictions(
                connection, (selection(),), collected_at=KICKOFF - timedelta(hours=3)
            )
            == 1
        )
        connection.execute(
            """UPDATE football.product_fixtures SET status='FINISHED',home_score=2,away_score=1,
                      result_score_basis='REGULATION_90',identity_status='VERIFIED'
               WHERE fixture_id=%s""",
            (FIXTURE,),
        )
        assert connection.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (
            0,
        )
        connection.commit()

        assert finish_result_recovery(connection)["settled_external_predictions"] == 1
        assert connection.execute(
            "SELECT settlement_state FROM football.external_prediction_latest_results"
        ).fetchall() == [("WON",)]
        connection.commit()
        assert finish_result_recovery(connection)["settled_external_predictions"] == 0
        # A recovered correction re-evaluates the prediction append-only, once.
        connection.execute(
            "UPDATE football.product_fixtures SET home_score=1 WHERE fixture_id=%s", (FIXTURE,)
        )
        connection.commit()
        assert finish_result_recovery(connection)["settled_external_predictions"] == 1
        assert finish_result_recovery(connection)["settled_external_predictions"] == 0
        assert connection.execute(
            """SELECT settlement_state FROM football.external_prediction_result_revisions
               ORDER BY revision_sequence"""
        ).fetchall() == [("WON",), ("LOST",)]
