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

from tests.integration.test_live_context import FIXTURE, KICKOFF, PROVIDER, SNAPSHOT
from tests.integration.test_public_reports import PREDICTION
from tests.integration.test_public_reports import report_database as report_database


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
            tuple(selection(home_team=f"Unknown {index}") for index in range(25)),
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
            "^TestExternalPredictionArchiveBoundDatabase$",
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
        row = selection(home_team="Unresolved source label", prediction_date=captured.date())
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
