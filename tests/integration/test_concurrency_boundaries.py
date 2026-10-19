"""Phase 18 transaction boundaries and repeat-delivery regressions."""

import os
from pathlib import Path
from typing import Any

import psycopg
import pytest
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.sync import ProductSync

from tests.integration.test_product_forecast_worklist import _forecast_fixture


def test_pending_forecast_computes_before_canonical_and_work_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import sync as module

    url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(url) as (competition, _, _, fixture),
        psycopg.connect(url) as worker,
        psycopg.connect(url, autocommit=True) as other,
    ):
        product = ProductSync(worker, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH)
        observed = []

        def compute(**_kwargs: Any) -> None:
            # An independent writer must proceed during model computation. The
            # changed generation must be captured, or left durable for the next batch.
            other.execute("SET lock_timeout='100ms'")
            other.execute(
                "UPDATE football.product_competitions SET updated_at=clock_timestamp() "
                "WHERE competition_id=%s",
                (competition,),
            )
            other.execute(
                "SELECT 1 FROM football.product_forecast_refresh_work "
                "WHERE fixture_id=%s FOR UPDATE NOWAIT",
                (fixture,),
            )
            observed.append(fixture)

        monkeypatch.setattr(module, "forecast_from_history", compute)
        assert product.refresh_pending_forecasts()["fixtures_processed"] == 1
        worker.commit()
        assert observed == [fixture]


def test_fixture_dates_release_identity_locks_before_next_provider_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date

    from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks

    url = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(url) as worker, psycopg.connect(url) as other:
        product = ProductSync(worker, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH)
        visited = []
        other.execute("SET lock_timeout='100ms'")
        other.commit()

        def fetch(day: Any) -> tuple[int, list[Any]]:
            with other.transaction():
                acquire_locks(other, (IDENTITY_ADMISSION_LOCK,))
            acquire_locks(worker, (IDENTITY_ADMISSION_LOCK,))
            visited.append(day)
            return 0, []

        monkeypatch.setattr(product, "_store_requested_fixtures", fetch)
        monkeypatch.setattr(product, "_scheduled_history_leagues", lambda: [])
        monkeypatch.setattr(product, "_history_sync_attempts", lambda *_: {})
        days = [date(2026, 10, 18), date(2026, 10, 19)]
        assert product._sync_fixtures(days) == (0, [])
        assert visited == days


def test_forecast_change_during_preparation_stays_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import sync as module

    url = os.environ["TEST_DATABASE_URL"]
    with (
        _forecast_fixture(url) as (_, _, _, fixture),
        psycopg.connect(url) as worker,
        psycopg.connect(url, autocommit=True) as other,
    ):
        product = ProductSync(worker, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH)
        with monkeypatch.context() as patch:

            def compute(**_kwargs: Any) -> None:
                other.execute("SELECT football.enqueue_product_forecast_refresh(%s)", (fixture,))

            patch.setattr(module, "forecast_from_history", compute)
            result = product.refresh_pending_forecasts()
        worker.commit()
        assert result["fixtures_processed"] == 0 and result["fixtures_pending"] >= 1
        assert product.refresh_pending_forecasts()["fixtures_processed"] == 1
        worker.commit()


@pytest.mark.parametrize("provider", ["openfootball", "football_data_uk"])
def test_bounded_file_import_retries_after_partial_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    import json

    from football.product import football_data_uk, openfootball
    from football.product.historical_backfill import HistoricalBackfillStore
    from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks
    from psycopg.pq import TransactionStatus

    from tests.integration.test_team_identity_correction import isolated_database

    original_import = HistoricalBackfillStore.import_match
    imported = []
    mirror = tmp_path / "mirror"
    season = mirror / "2025-26"
    season.mkdir(parents=True)
    (season / "en.1.json").write_text(
        json.dumps(
            {
                "name": "English Premier League 2025/26",
                "matches": [
                    {
                        "date": f"2025-08-{day}",
                        "time": "15:00",
                        "team1": "Arsenal FC",
                        "team2": "Leeds United",
                        "score": {"ft": [2, 0]},
                    }
                    for day in (16, 23)
                ],
            }
        )
    )
    monkeypatch.setattr(openfootball, "_local_revision", lambda *_: "a" * 40)
    resource = football_data_uk.FootballDataResource(
        "https://www.football-data.co.uk/mmz4281/2526/E0.csv", "2025-2026", "England", "E0", False
    )
    monkeypatch.setattr(football_data_uk, "discover_catalog", lambda *_: [resource])
    payload = (
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG\n"
        b"E0,16/08/2025,15:00,Arsenal,Leeds,2,0\n"
        b"E0,23/08/2025,15:00,Arsenal,Leeds,2,0\n"
    )

    with isolated_database() as url, psycopg.connect(url) as worker, psycopg.connect(url) as other:
        other.execute("SET lock_timeout='100ms'")
        other.commit()

        def download(_url: str) -> bytes:
            assert worker.info.transaction_status == TransactionStatus.IDLE
            with other.transaction():
                acquire_locks(other, (IDENTITY_ADMISSION_LOCK,))
            return payload

        monkeypatch.setattr(football_data_uk, "_download", download)

        def import_match(store: Any, *args: Any) -> Any:
            assert worker.info.transaction_status == TransactionStatus.IDLE
            with other.transaction():
                acquire_locks(other, (IDENTITY_ADMISSION_LOCK,))
            if len(imported) == 1:
                raise OSError("crash after first committed result")
            result = original_import(store, *args)
            imported.append(args[0])
            return result

        def run() -> Any:
            if provider == "openfootball":
                return openfootball.run_backfill(
                    worker, mirror=mirror, data_root=tmp_path, update=False
                )
            return football_data_uk.run_backfill(worker, data_root=tmp_path)

        with monkeypatch.context() as patch:
            patch.setattr(HistoricalBackfillStore, "import_match", import_match)
            with pytest.raises(OSError, match="crash after first"):
                run()
        worker.rollback()
        assert other.execute(
            "SELECT count(*) FROM football.product_team_match_history"
        ).fetchone() == (1,)
        assert other.execute(
            "SELECT completed_at FROM football.product_history_resource_imports"
        ).fetchone() == (None,)
        other.commit()
        result = run()
        assert result["matches_inserted"] == 1
        assert other.execute(
            "SELECT count(*) FROM football.product_team_match_history"
        ).fetchone() == (2,)
        assert other.execute(
            "SELECT bool_and(completed_at IS NOT NULL) "
            "FROM football.product_history_resource_imports"
        ).fetchone() == (True,)
        other.commit()
        assert run()["resources_cached"] == 1


def test_correction_verifies_files_before_identity_coordination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import identity_admission
    from football.product.identity_correction import correct_team_identity
    from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks

    from tests.integration.test_team_identity_correction import isolated_database, seed

    original = identity_admission._retained_payload
    checked = []
    with isolated_database() as url, psycopg.connect(url) as worker, psycopg.connect(url) as other:
        request, _ = seed(worker, tmp_path)
        worker.commit()
        other.execute("SET lock_timeout='100ms'")
        other.commit()

        def payload(*args: Any) -> Any:
            with other.transaction():
                acquire_locks(other, (IDENTITY_ADMISSION_LOCK,))
            checked.append(args[1])
            return original(*args)

        monkeypatch.setattr(identity_admission, "_retained_payload", payload)
        assert correct_team_identity(worker, tmp_path, request)["disposition"] == "CROSSWALK"
        worker.commit()
        assert set(checked) == {"api_football", "football_data_org", "fotmob"}


@pytest.mark.parametrize("operation", ["openfootball", "football_data_uk", "forecast", "scope"])
def test_owned_batches_reject_borrowed_changes_without_committing(
    tmp_path: Path, operation: str
) -> None:
    from football.product import football_data_uk, openfootball

    with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as worker:
        worker.execute("CREATE TEMP TABLE caller_work(value integer)")
        worker.commit()
        worker.execute("INSERT INTO caller_work VALUES (1)")
        with pytest.raises(ValueError, match="requires an idle connection"):
            if operation == "openfootball":
                openfootball.run_backfill(worker, mirror=tmp_path, data_root=tmp_path)
            elif operation == "football_data_uk":
                football_data_uk.run_backfill(worker, data_root=tmp_path)
            elif operation == "scope":
                from football.product.operational_provider_sync import OperationalProviderSync
                from football.product.provider_history_scopes import claim_scope

                claim_scope(
                    OperationalProviderSync(worker, tmp_path, provider_code="fotmob"), None, None
                )
            else:
                ProductSync(
                    worker, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH
                ).refresh_forecasts(commit_batches=True)
        assert worker.execute("SELECT value FROM caller_work").fetchone() == (1,)
        worker.rollback()
        assert worker.execute("SELECT value FROM caller_work").fetchone() is None


def test_identity_admission_rejects_mapping_change_before_coordination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from football.product import identity_admission
    from football.product.identity_admission import RetainedEvidenceChanged, admit_provider_mappings

    from tests.integration.test_team_identity_correction import isolated_database, seed

    original_lock = identity_admission.acquire_locks
    changed = []
    with (
        isolated_database() as url,
        psycopg.connect(url) as worker,
        psycopg.connect(url, autocommit=True) as other,
    ):
        request, _ = seed(worker, tmp_path)
        worker.commit()

        def lock(*args: Any) -> None:
            if not changed:
                other.execute(
                    "UPDATE football.team_provider_mappings SET mapping_confidence=0.5 WHERE id=%s",
                    (request.target_mapping_id,),
                )
                changed.append(request.target_mapping_id)
            original_lock(*args)

        monkeypatch.setattr(identity_admission, "acquire_locks", lock)
        with pytest.raises(RetainedEvidenceChanged, match="mapping changed"):
            admit_provider_mappings(worker, tmp_path, "api_football", entity_types=("team",))
        worker.rollback()
        assert other.execute(
            "SELECT disposition FROM football.product_identity_admissions WHERE mapping_id=%s "
            "ORDER BY decided_at DESC,decision_id DESC LIMIT 1",
            (request.target_mapping_id,),
        ).fetchone() == ("REVOKED",)


def test_malformed_archive_cannot_register_successfully_parsed_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from zipfile import BadZipFile

    from football.product import football_data_uk

    from tests.integration.test_team_identity_correction import isolated_database

    resource = football_data_uk.FootballDataResource(
        "https://www.football-data.co.uk/datazip/2526/England.zip",
        "2025-2026",
        "England",
        None,
        True,
    )
    monkeypatch.setattr(football_data_uk, "discover_catalog", lambda *_: [resource])
    monkeypatch.setattr(football_data_uk, "_download", lambda *_: b"malformed archive")
    with (
        isolated_database() as url,
        psycopg.connect(url) as worker,
        psycopg.connect(url, autocommit=True) as other,
    ):
        with pytest.raises(BadZipFile):
            football_data_uk.run_backfill(worker, data_root=tmp_path)
        worker.rollback()
        assert other.execute(
            "SELECT count(*) FROM football.source_resources WHERE parse_status='parsed'"
        ).fetchone() == (0,)
        assert other.execute(
            "SELECT count(*) FROM football.product_history_resource_imports"
        ).fetchone() == (0,)
