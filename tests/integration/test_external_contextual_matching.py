"""Real-database contextual association, settlement, review and preservation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import psycopg
import pytest
from football.product.external_prediction_association import (
    refresh_contextual_association,
    review_contextual_association,
)
from football.product.external_prediction_recovery import (
    backfill_contextual_associations,
    settle_pending_predictions,
)
from football.product.external_predictions import ImportedPrediction, import_predictions
from psycopg.errors import RaiseException
from psycopg.rows import dict_row

from tests.integration.test_live_context import (
    AWAY,
    COMPETITION,
    FIXTURE,
    HOME,
    KICKOFF,
    SEASON,
    _seed_fixture,
)
from tests.integration.test_team_identity_correction import isolated_database

TWIN = UUID(int=8190)
REVIEWER = "owner:" + "a" * 16
PROTECTED = (
    "product_fixtures",
    "match_provider_mappings",
    "fixture_identity_resolutions",
    "product_team_aliases",
    "product_teams",
    "product_forecasts",
    "product_match_history_decisions",
    "external_prediction_bindings",
)


@pytest.fixture
def database():
    with isolated_database() as url:
        with psycopg.connect(url) as c:
            _seed_fixture(c)
            c.execute(
                "UPDATE football.product_fixtures SET identity_status='VERIFIED' "
                "WHERE fixture_id=%s",
                (FIXTURE,),
            )
        yield url


def pick(**changes) -> ImportedPrediction:
    values = {
        "source_page": "https://example.test/contextual",
        "prediction_date": KICKOFF.date(),
        "original_date_text": KICKOFF.strftime("%d %b %Y"),
        "competition": "Test League",
        "home_team": "Home",
        "away_team": "Away",
        "market": "RESULT_1X2",
        "selection": "HOME_WIN",
    }
    values.update(changes)
    return ImportedPrediction(**values)


def imported(url: str, row: ImportedPrediction, collected_at: datetime) -> UUID:
    with psycopg.connect(url) as c:
        import_predictions(c, (row,), collected_at=collected_at)
        return c.execute(
            "SELECT prediction_id FROM football.external_predictions WHERE home_team_text=%s "
            "AND prediction_date=%s AND collected_at=%s",
            (row.home_team, row.prediction_date, collected_at),
        ).fetchone()[0]


def settle(url: str) -> int:
    with psycopg.connect(url) as c:
        return settle_pending_predictions(c, datetime.now(UTC))


def finish(url: str, home: int, away: int) -> None:
    with psycopg.connect(url) as c:
        c.execute(
            "UPDATE football.product_fixtures SET status='FINISHED',home_score=%s,away_score=%s,"
            "result_score_basis='REGULATION_90' WHERE fixture_id=%s",
            (home, away, FIXTURE),
        )


def decisions(url: str, prediction: UUID) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as c:
        return c.execute(
            "SELECT * FROM football.external_prediction_context_matches WHERE prediction_id=%s "
            "ORDER BY decided_at,context_match_id",
            (prediction,),
        ).fetchall()


def results(url: str, prediction: UUID) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as c:
        return c.execute(
            "SELECT settlement_state,evidence FROM football.external_prediction_result_revisions "
            "WHERE prediction_id=%s ORDER BY revision_sequence",
            (prediction,),
        ).fetchall()


def protected(url: str) -> dict[str, str]:
    with psycopg.connect(url) as c:
        return {
            table: c.execute(
                f"SELECT md5(coalesce(string_agg(t::text,'|' ORDER BY t::text),'')) "  # noqa: S608
                f"FROM football.{table} t"
            ).fetchone()[0]
            for table in PROTECTED
        }


def add_twin(url: str, *, identity: str, kickoff: datetime = KICKOFF) -> None:
    with psycopg.connect(url) as c:
        c.execute(
            "INSERT INTO football.matches (id, competition_id, season_id) VALUES (%s,%s,%s)",
            (TWIN, COMPETITION, SEASON),
        )
        c.execute(
            """INSERT INTO football.product_fixtures (fixture_id,competition_id,home_team_id,
            away_team_id,kickoff_at,status,forecast_availability,updated_at,identity_status)
            VALUES (%s,%s,%s,%s,%s,'SCHEDULED','NOT_ENOUGH_HISTORY',clock_timestamp(),%s)""",
            (TWIN, COMPETITION, HOME, AWAY, kickoff, identity),
        )


def test_contextual_match_settles_without_native_id_or_internal_forecast(database):
    before = protected(database)
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    finish(database, 2, 1)
    assert settle(database) == 1
    [decision] = decisions(database, prediction)
    assert (decision["classification"], decision["reason"], decision["fixture_id"]) == (
        "CONTEXTUAL_MATCH",
        "UNIQUE_SAME_DAY",
        FIXTURE,
    )
    assert decision["basis"] == "POLICY"
    [result] = results(database, prediction)
    assert result["settlement_state"] == "WON"
    assert result["evidence"]["fixture_association"] == "CONTEXTUAL_MATCH"
    assert result["evidence"]["association_basis"] == "CONTEXTUAL_POLICY"
    assert result["evidence"]["evaluation"] == "PROSPECTIVE"
    with psycopg.connect(database) as c:
        assert c.execute(
            "SELECT effective_match_status,effective_fixture_id FROM "
            "football.external_prediction_effective WHERE prediction_id=%s",
            (prediction,),
        ).fetchone() == ("CONTEXTUAL", FIXTURE)
        assert c.execute("SELECT count(*) FROM football.product_forecasts").fetchone() == (0,)
    after = protected(database)
    # The fixture row itself changed only because the test finished the match.
    assert {k: v for k, v in after.items() if k != "product_fixtures"} == {
        k: v for k, v in before.items() if k != "product_fixtures"
    }
    with psycopg.connect(database) as c:
        c.execute("SELECT football.enqueue_external_prediction_refresh(%s)", (prediction,))
    assert settle(database) == 0
    assert len(decisions(database, prediction)) == 1


def test_capture_after_kickoff_is_retrospective_and_correction_appends(database):
    prediction = imported(database, pick(), KICKOFF + timedelta(hours=1))
    finish(database, 0, 1)
    settle(database)
    finish(database, 3, 1)
    settle(database)
    states = results(database, prediction)
    assert [r["settlement_state"] for r in states] == ["LOST", "WON"]
    assert {r["evidence"]["evaluation"] for r in states} == {"RETROSPECTIVE"}


def test_new_twin_fixture_reopens_and_revokes_dependent_settlement(database):
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    finish(database, 2, 1)
    settle(database)
    add_twin(database, identity="VERIFIED")
    settle(database)
    history = decisions(database, prediction)
    assert [d["classification"] for d in history] == ["CONTEXTUAL_MATCH", "NEEDS_REVIEW"]
    assert history[1]["reason"] == "MULTIPLE_CANDIDATES"
    assert history[1]["previous_context_match_id"] == history[0]["context_match_id"]
    assert set(history[1]["candidate_fixture_ids"]) == {FIXTURE, TWIN}
    assert [r["settlement_state"] for r in results(database, prediction)] == ["WON", "PENDING"]


def test_provisional_copy_at_the_same_kickoff_keeps_the_verified_record(database):
    add_twin(database, identity="PROVISIONAL")
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    settle(database)
    [decision] = decisions(database, prediction)
    assert (decision["reason"], decision["fixture_id"]) == ("UNIQUE_VERIFIED_TWIN", FIXTURE)


def test_owner_review_is_durable_and_retry_reapplies_policy(database):
    add_twin(database, identity="VERIFIED", kickoff=KICKOFF + timedelta(hours=2))
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    finish(database, 1, 1)
    settle(database)
    assert decisions(database, prediction)[-1]["classification"] == "NEEDS_REVIEW"
    with psycopg.connect(database, row_factory=dict_row) as c:
        c.execute("SELECT football.authorize_worker_publication()")
        with pytest.raises(ValueError, match="retained candidate"):
            review_contextual_association(
                c, prediction, UUID(int=1), reason="not a candidate", reviewer=REVIEWER
            )
        assert review_contextual_association(
            c, prediction, FIXTURE, reason="kickoff confirmed on source page", reviewer=REVIEWER
        )
    settle(database)
    latest = decisions(database, prediction)[-1]
    assert (latest["basis"], latest["fixture_id"]) == ("REVIEW", FIXTURE)
    [*_, result] = results(database, prediction)
    assert result["settlement_state"] == "LOST"
    assert result["evidence"]["association_basis"] == "CONTEXTUAL_REVIEW"
    # The review was recorded before this fixture's kickoff, so it stays prospective.
    assert result["evidence"]["evaluation"] == "PROSPECTIVE"
    with psycopg.connect(database, row_factory=dict_row) as c:
        c.execute("SELECT football.authorize_worker_publication()")
        assert not refresh_contextual_association(c, prediction)
        assert review_contextual_association(
            c, prediction, None, reason="wrong fixture", reviewer=REVIEWER
        )
    settle(database)
    assert results(database, prediction)[-1]["settlement_state"] == "PENDING"
    with psycopg.connect(database, row_factory=dict_row) as c:
        c.execute("SELECT football.authorize_worker_publication()")
        assert refresh_contextual_association(c, prediction, retry=True)
    assert decisions(database, prediction)[-1]["basis"] == "POLICY"


def test_verified_binding_is_never_replaced(database):
    with psycopg.connect(database) as c:
        c.execute(
            """INSERT INTO football.external_predictions
            (prediction_id,revision_sha256,source_code,source_page,prediction_date,
             original_date_text,collected_at,fixture_id,competition_text,home_team_text,
             away_team_text,market,selection,match_status)
            VALUES(%s,%s,'manual_import','x',%s,'x',%s,%s,'Test League','Home','Away',
             'RESULT_1X2','HOME_WIN','MATCHED')""",
            (UUID(int=8191), "c" * 64, KICKOFF.date(), KICKOFF - timedelta(days=1), FIXTURE),
        )
    with psycopg.connect(database, row_factory=dict_row) as c:
        c.execute("SELECT football.authorize_worker_publication()")
        assert not refresh_contextual_association(c, UUID(int=8191))
    assert decisions(database, UUID(int=8191)) == []


def test_contextual_match_cannot_name_a_quarantined_fixture(database):
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    with psycopg.connect(database) as c:
        c.execute("UPDATE football.product_fixtures SET identity_status='QUARANTINED'")
        c.execute("SELECT football.authorize_worker_publication()")
        with pytest.raises(RaiseException, match="unquarantined representative"):
            c.execute(
                """INSERT INTO football.external_prediction_context_matches
                (prediction_id,policy_version,basis,classification,reason,fixture_id,
                 candidate_fixture_ids,evidence,evidence_sha256)
                VALUES(%s,'V','POLICY','CONTEXTUAL_MATCH','X',%s,'{}','{}',%s)""",
                (prediction, FIXTURE, "d" * 64),
            )


def test_decisions_are_append_only(database):
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))
    settle(database)
    with psycopg.connect(database) as c, pytest.raises(psycopg.Error):
        c.execute("UPDATE football.external_prediction_context_matches SET reason='X'")
    assert len(decisions(database, prediction)) == 1


def test_concurrent_runs_publish_one_decision_chain(database):
    prediction = imported(database, pick(), KICKOFF - timedelta(hours=5))

    def run(_: int) -> dict:
        with psycopg.connect(database) as c:
            return backfill_contextual_associations(c, datetime.now(UTC), limit=10)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, range(3)))
    assert len(decisions(database, prediction)) == 1
    with psycopg.connect(database) as c:
        again = backfill_contextual_associations(c, datetime.now(UTC), limit=10)
    assert (again["processed"], again["remaining"]) == (0, 0)


def test_unmatched_prediction_records_its_reason(database):
    prediction = imported(
        database,
        pick(home_team="Nobody", away_team="Elsewhere", prediction_date=date(2030, 1, 1)),
        KICKOFF - timedelta(hours=5),
    )
    settle(database)
    [decision] = decisions(database, prediction)
    assert (decision["classification"], decision["reason"]) == (
        "UNMATCHED",
        "NO_CORRESPONDING_FIXTURE",
    )
    assert results(database, prediction)[-1]["evidence"]["fixture_association"] == (
        "FIXTURE_IDENTITY"
    )
