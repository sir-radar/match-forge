"""Linked team corrections preserve source rows and prior knowledge cutoffs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from football.product.domain import stable_id
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.identity_admission import (
    admit_provider_mappings,
    classify_mapping,
    mapping_rows,
)
from football.product.identity_correction import (
    TeamIdentityCorrection,
    correct_team_identity,
    qualify_team_correction,
    revoke_team_correction,
)
from football.product.operational_provider_sync import OperationalProviderSync
from psycopg import Connection
from psycopg.conninfo import make_conninfo
from psycopg.sql import SQL, Identifier
from psycopg.types.json import Jsonb

from tests.integration.historical_source_fixture import test_snapshot as snapshot
from tests.integration.test_product_identity_upgrade import _migrate

DATABASE_URL = os.environ["TEST_DATABASE_URL"]
KICKOFF = datetime(2026, 8, 25, 14, tzinfo=UTC)
ACQUIRED = KICKOFF + timedelta(hours=4)


def seed(
    connection: Connection[Any], root: Path
) -> tuple[TeamIdentityCorrection, TeamIdentityCorrection]:
    payloads = {
        "football_data_org": {
            "matches": [
                {
                    "id": 560611,
                    "utcDate": KICKOFF.isoformat(),
                    "area": {"name": "England"},
                    "competition": {"id": 2021, "code": "PL", "name": "Premier League"},
                    "season": {"id": 2502, "startDate": "2026-08-21", "endDate": "2027-05-30"},
                    "homeTeam": {"id": 402, "name": "Brentford FC"},
                    "awayTeam": {"id": 64, "name": "Liverpool FC"},
                }
            ]
        },
        "api_football": {
            "response": [
                {
                    "fixture": {"id": 1557418},
                    "league": {"id": 39, "country": "England", "season": 2026},
                    "teams": {
                        "home": {"id": 55, "name": "Brentford"},
                        "away": {"id": 40, "name": "Liverpool"},
                    },
                }
            ]
        },
        "fotmob": {
            "details": {"id": 47, "country": "ENG"},
            "selectedSeason": "2026/2027",
            "matches": [
                {
                    "id": "5795476",
                    "home": {"id": "9937", "name": "Brentford"},
                    "away": {"id": "8650", "name": "Liverpool"},
                    "status": {"utcTime": KICKOFF.isoformat()},
                }
            ],
        },
    }
    snapshots = {}
    for provider, payload in payloads.items():
        store = HistoricalBackfillStore(connection, provider, provider, "correction-test")
        snapshots[provider] = snapshot(
            store,
            root,
            source_identity=f"correction/{provider}",
            source_revision="test",
            acquired_at=ACQUIRED,
            manifest_path=f"raw/{provider}.json",
            payload=json.dumps(payload).encode(),
        )
    competition = stable_id("competition", "api_football", "39")
    connection.execute("INSERT INTO football.competitions (id) VALUES (%s)", (competition,))
    connection.execute(
        """INSERT INTO football.product_competitions
           (competition_id,name,country,continent,competition_type,season_label,
            availability_status,source_roles,updated_at)
           VALUES (%s,'Premier League','England','Europe','LEAGUE','2026',
                   'NOT_ENOUGH_HISTORY','{}',%s)""",
        (competition, ACQUIRED),
    )
    ids = {}
    for provider, teams in [
        ("football_data_org", [("402", "Brentford FC"), ("64", "Liverpool FC")]),
        ("api_football", [("55", "Brentford"), ("40", "Liverpool")]),
        ("fotmob", [("9937", "Brentford"), ("8650", "Liverpool")]),
    ]:
        for identifier, name in teams:
            target = "55" if identifier == "9937" else "40"
            canonical = (
                stable_id("team", "api_football", target)
                if provider == "fotmob"
                else stable_id("team", provider, identifier)
            )
            connection.execute(
                """INSERT INTO football.teams (id,entity_kind) VALUES (%s,'club')
                ON CONFLICT DO NOTHING""",
                (canonical,),
            )
            connection.execute(
                """INSERT INTO football.product_teams (team_id,name,country,updated_at)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (canonical, name, None if provider == "football_data_org" else "England", ACQUIRED),
            )
            method = "deterministic" if provider == "api_football" else "explicit_crosswalk"
            ids[(provider, identifier)] = connection.execute(
                """INSERT INTO football.team_provider_mappings
                   (team_id,provider_id,provider_team_id,first_seen_at,last_seen_at,
                    mapping_method,mapping_confidence,source_snapshot_id)
                   SELECT %s,id,%s,%s,%s,%s,1,%s FROM football.providers WHERE code=%s
                   RETURNING id""",
                (canonical, identifier, ACQUIRED, ACQUIRED, method, snapshots[provider], provider),
            ).fetchone()[0]
        league = {"football_data_org": "PL", "api_football": "39", "fotmob": "47"}[provider]
        connection.execute(
            """INSERT INTO football.competition_provider_mappings
               (competition_id,provider_id,provider_competition_id,first_seen_at,last_seen_at,
                mapping_method,mapping_confidence,source_snapshot_id)
               SELECT %s,id,%s,%s,%s,%s,1,%s FROM football.providers WHERE code=%s""",
            (competition, league, ACQUIRED, ACQUIRED, method, snapshots[provider], provider),
        )
    season = uuid4()
    fixture = uuid4()
    connection.execute(
        """INSERT INTO football.seasons (id,competition_id,start_date,end_date)
           VALUES (%s,%s,'2026-08-21','2027-05-30')""",
        (season, competition),
    )
    connection.execute(
        "INSERT INTO football.matches (id,competition_id,season_id) VALUES (%s,%s,%s)",
        (fixture, competition, season),
    )
    home = stable_id("team", "football_data_org", "402")
    away = stable_id("team", "football_data_org", "64")
    connection.execute(
        """INSERT INTO football.product_fixtures
           (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
            home_score,away_score,forecast_availability,updated_at,result_score_basis)
           VALUES (%s,%s,%s,%s,%s,'FINISHED',2,1,'NOT_ENOUGH_HISTORY',%s,'REGULATION_90')""",
        (fixture, competition, home, away, KICKOFF, ACQUIRED),
    )
    registration = connection.execute(
        """INSERT INTO football.match_provider_mappings
           (match_id,provider_id,provider_match_id,first_seen_at,last_seen_at,mapping_method,
            mapping_confidence,source_snapshot_id)
           SELECT %s,id,'560611',%s,%s,'deterministic',1,%s FROM football.providers
           WHERE code='football_data_org' RETURNING id""",
        (fixture, ACQUIRED, ACQUIRED, snapshots["football_data_org"]),
    ).fetchone()[0]
    original = connection.execute(
        """INSERT INTO football.product_provider_mapping_decisions
           (semantic_sha256,provider_code,provider_match_id,candidate_fixture_id,disposition,reason,
            evidence,source_snapshot_id,observed_at)
           VALUES (%s,'fotmob','5795476',%s,'CONTRADICTORY',
                   'verified team_provider_mappings contradicts exact-name candidate',%s,%s,%s)
           RETURNING decision_id""",
        (
            "a" * 64,
            fixture,
            Jsonb({"provider_home_team": "Brentford", "provider_away_team": "Liverpool"}),
            snapshots["fotmob"],
            ACQUIRED,
        ),
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO football.product_team_match_history
           (fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,home_goals,away_goals,
            source_provider_code,source_snapshot_id,source_kickoff_precision)
           VALUES (%s,%s,%s,%s,%s,2,1,'football_data_org',%s,'EXACT')""",
        (fixture, competition, home, away, KICKOFF, snapshots["football_data_org"]),
    )
    connection.execute(
        """INSERT INTO football.product_provider_resource_observations
           (semantic_sha256,provider_code,provider_match_id,canonical_fixture_id,resource_type,
            availability_status,source_snapshot_id,source_checksum,observed_at,known_at,
            point_in_time_eligibility,payload,last_fetched_at)
           VALUES (%s,'football_data_org','560611',%s,'MATCH_DETAILS','AVAILABLE',
                   %s,%s,%s,NULL,'UNKNOWN','{}',%s)""",
        ("b" * 64, fixture, snapshots["football_data_org"], "c" * 64, ACQUIRED, ACQUIRED),
    )
    connection.execute(
        """INSERT INTO football.product_forecasts
           (forecast_id,semantic_sha256,fixture_id,model_label,model_algorithm_version,
            model_artifact_sha256,created_at,football_cutoff,knowledge_cutoff,knowledge_mode,
            expected_home_goals,expected_away_goals,probabilities,score_matrix,payload_sha256,
            publication_mode,forecast_horizon,predictive_input_snapshot_sha256,
            context_snapshot_sha256,revision_reason_codes,new_information_ids)
           VALUES (%s,%s,%s,'MVP_FORECAST','test-only',%s,%s,%s,%s,'bitemporal',
                   1.2,1.1,'{}','[]',%s,'MVP_OWNER_AUTHORIZED','24H',%s,%s,
                   '["INITIAL_FORECAST"]','[]')""",
        (
            uuid4(),
            "e" * 64,
            fixture,
            "f" * 64,
            KICKOFF - timedelta(hours=24),
            KICKOFF - timedelta(hours=24),
            KICKOFF - timedelta(hours=24),
            "1" * 64,
            "2" * 64,
            "3" * 64,
        ),
    )
    admit_provider_mappings(connection, root, "api_football")
    admit_provider_mappings(connection, root, "football_data_org")
    return (
        TeamIdentityCorrection(
            ids[("football_data_org", "402")],
            ids[("api_football", "55")],
            original,
            registration,
            "HOME",
        ),
        TeamIdentityCorrection(
            ids[("football_data_org", "64")],
            ids[("api_football", "40")],
            original,
            registration,
            "AWAY",
        ),
    )


def retained(connection: Connection[Any]) -> dict[str, Any]:
    tables = [
        "team_provider_mappings",
        "product_provider_mapping_decisions",
        "product_provider_resource_observations",
        "match_provider_mappings",
        "product_fixtures",
        "source_snapshots",
        "source_resources",
        "product_forecasts",
        "product_model_artifacts",
    ]
    return {
        table: connection.execute(
            f"SELECT to_jsonb(t) FROM football.{table} t ORDER BY to_jsonb(t)::text"
        ).fetchall()
        for table in tables
    }


def identity(
    connection: Connection[Any], request: TeamIdentityCorrection, cutoff: datetime
) -> UUID | None:
    return connection.execute(
        "SELECT football.product_team_identity_at(%s,%s)", (request.source_mapping_id, cutoff)
    ).fetchone()[0]  # type: ignore[no-any-return]


def history(connection: Connection[Any], cutoff: datetime) -> list[tuple[Any, ...]]:
    return connection.execute(
        "SELECT * FROM football.product_eligible_history_at(%s) ORDER BY fixture_id", (cutoff,)
    ).fetchall()


def test_linked_corrections_are_independent_prospective_revocable_and_preserve_evidence(
    tmp_path: Path,
) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        brentford, liverpool = seed(c, tmp_path)
        before = retained(c)
        file_digests = {
            path: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in tmp_path.rglob("*")
            if path.is_file()
        }
        assert len(before["product_forecasts"]) == 1
        t0 = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert identity(c, brentford, t0) is None
        assert history(c, t0) == []
        first = correct_team_identity(c, tmp_path, brentford)
        assert first["corrects_decision_id"] == str(brentford.original_decision_id)
        assert identity(c, brentford, first["decided_at"] - timedelta(microseconds=1)) is None
        assert identity(c, brentford, first["decided_at"]) == stable_id(
            "team", "api_football", "55"
        )
        assert identity(c, liverpool, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None
        assert correct_team_identity(c, tmp_path, brentford)["decision_id"] == first["decision_id"]
        correct_team_identity(c, tmp_path, liverpool)
        t1 = c.execute("SELECT clock_timestamp()").fetchone()[0]
        frozen = history(c, t1)
        assert len(frozen) == 1
        assert frozen[0][2:4] == (
            stable_id("team", "api_football", "55"),
            stable_id("team", "api_football", "40"),
        )
        fixture = frozen[0][0]
        assert (
            c.execute(
                "SELECT home_team_id,away_team_id FROM football.product_effective_fixtures "
                "WHERE fixture_id=%s",
                (fixture,),
            ).fetchone()
            == frozen[0][2:4]
        )
        assert c.execute(
            """SELECT football.product_fixture_team_at(fixture_id,home_team_id,%s),
                      football.product_fixture_team_at(fixture_id,away_team_id,%s)
               FROM football.product_fixtures WHERE fixture_id=%s""",
            (t0, t0, fixture),
        ).fetchone() == (
            stable_id("team", "football_data_org", "402"),
            stable_id("team", "football_data_org", "64"),
        )
        sync = OperationalProviderSync(c, tmp_path, provider_code="football_data_org")
        assert sync._mapped_or_scoped_team("402") == stable_id("team", "api_football", "55")
        assert sync._mapped_or_scoped_team("64") == stable_id("team", "api_football", "40")
        assert {
            classify_mapping(c, "team", row, tmp_path)["disposition"]
            for row in mapping_rows(c, "team", "football_data_org")
        } == {"CROSSWALK"}
        count = c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
        admit_provider_mappings(c, tmp_path, "football_data_org")
        assert (
            c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
            == count
        )
        revoke_team_correction(c, UUID(first["decision_id"]), "OPERATOR_REVOKED")
        t2 = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert identity(c, brentford, t2) is None
        assert identity(c, liverpool, t2) == stable_id("team", "api_football", "40")
        assert history(c, t2) == []
        assert history(c, t0) == [] and history(c, t1) == frozen
        assert correct_team_identity(c, tmp_path, brentford)["disposition"] == "REVOKED"
        admit_provider_mappings(c, tmp_path, "football_data_org")
        assert identity(c, brentford, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None
        assert retained(c) == before
        assert {
            path: hashlib.sha256(path.read_bytes()).hexdigest() for path in file_digests
        } == file_digests


@pytest.mark.parametrize(
    "bad", ["orientation", "target", "missing", "confidence", "extra_conflict"]
)
def test_invalid_pair_fails_without_admitting_other_pair(tmp_path: Path, bad: str) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        brentford, liverpool = seed(c, tmp_path)
        request = brentford
        if bad == "orientation":
            request = replace(request, orientation="AWAY")
        if bad == "target":
            request = replace(request, target_mapping_id=liverpool.target_mapping_id)
        if bad == "missing":
            (tmp_path / "raw/football_data_org.json").write_bytes(b"tampered")
        if bad == "confidence":
            c.execute(
                "UPDATE football.team_provider_mappings SET mapping_confidence=.9 WHERE id=%s",
                (brentford.source_mapping_id,),
            )
        if bad == "extra_conflict":
            c.execute(
                """INSERT INTO football.product_provider_mapping_decisions
                (semantic_sha256,provider_code,provider_match_id,candidate_fixture_id,
                 disposition,reason,evidence,source_snapshot_id,observed_at)
                SELECT %s,provider_code,provider_match_id,candidate_fixture_id,
                       disposition,'different evidence',evidence,source_snapshot_id,observed_at
                FROM football.product_provider_mapping_decisions WHERE decision_id=%s""",
                ("d" * 64, brentford.original_decision_id),
            )
        assert qualify_team_correction(c, tmp_path, request)["status"] == "UNRESOLVED"
        count = c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
        with pytest.raises(ValueError):
            correct_team_identity(c, tmp_path, request)
        assert (
            c.execute("SELECT count(*) FROM football.product_identity_admissions").fetchone()
            == count
        )
        if bad in {"orientation", "target", "confidence"}:
            assert correct_team_identity(c, tmp_path, liverpool)["disposition"] == "CROSSWALK"


def test_liverpool_can_fail_without_blocking_brentford(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        brentford, liverpool = seed(c, tmp_path)
        c.execute(
            "UPDATE football.team_provider_mappings SET mapping_confidence=.5 WHERE id=%s",
            (liverpool.source_mapping_id,),
        )
        assert qualify_team_correction(c, tmp_path, liverpool)["status"] == "UNRESOLVED"
        assert correct_team_identity(c, tmp_path, brentford)["disposition"] == "CROSSWALK"
        assert identity(c, liverpool, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None


@pytest.mark.parametrize("bad", ["provider", "uuid", "original"])
def test_wrong_identity_or_decision_is_rejected(tmp_path: Path, bad: str) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        brentford, liverpool = seed(c, tmp_path)
        request = brentford
        if bad == "provider":
            request = replace(request, source_mapping_id=brentford.target_mapping_id)
        elif bad == "original":
            request = replace(request, original_decision_id=uuid4())
        else:
            c.execute(
                "UPDATE football.team_provider_mappings SET team_id=%s WHERE id=%s",
                (stable_id("team", "api_football", "40"), brentford.target_mapping_id),
            )
        assert qualify_team_correction(c, tmp_path, request)["status"] == "UNRESOLVED"
        with pytest.raises(ValueError):
            correct_team_identity(c, tmp_path, request)


@contextmanager
def isolated_database(version: str | None = None) -> Iterator[str]:
    name = "football_correction_" + uuid4().hex
    url = make_conninfo(DATABASE_URL, dbname=name)
    with psycopg.connect(make_conninfo(DATABASE_URL, dbname="postgres"), autocommit=True) as admin:
        admin.execute(SQL("CREATE DATABASE {}").format(Identifier(name)))
        try:
            _migrate(url, "up-to", version) if version else _migrate(url, "up")
            yield url
        finally:
            admin.execute(SQL("DROP DATABASE {} WITH (FORCE)").format(Identifier(name)))


def test_concurrent_identical_requests_return_one_decision(tmp_path: Path) -> None:
    with isolated_database() as url:
        with psycopg.connect(url) as c:
            request, _ = seed(c, tmp_path)

        def run() -> str:
            with psycopg.connect(url) as c:
                return str(correct_team_identity(c, tmp_path, request)["decision_id"])

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: run(), range(2)))
        assert results[0] == results[1]
        with psycopg.connect(url) as c:
            assert c.execute(
                "SELECT count(*) FROM football.product_identity_admissions "
                "WHERE corrects_decision_id IS NOT NULL"
            ).fetchone() == (1,)


def test_concurrent_incompatible_target_cannot_mutate_other_pair(tmp_path: Path) -> None:
    with isolated_database() as url:
        with psycopg.connect(url) as c:
            brentford, liverpool = seed(c, tmp_path)

        def run(request: TeamIdentityCorrection) -> str:
            with psycopg.connect(url) as c:
                try:
                    return str(correct_team_identity(c, tmp_path, request)["disposition"])
                except ValueError:
                    return "UNRESOLVED"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    run,
                    [brentford, replace(brentford, target_mapping_id=liverpool.target_mapping_id)],
                )
            )
        assert sorted(results) == ["CROSSWALK", "UNRESOLVED"]
        with psycopg.connect(url) as c:
            assert (
                identity(c, liverpool, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None
            )


def test_transaction_failure_rolls_back_admission_and_history(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        request, _ = seed(c, tmp_path)
        before = retained(c)
        decisions = c.execute(
            "SELECT to_jsonb(a) FROM football.product_identity_admissions a ORDER BY decision_id"
        ).fetchall()
        histories = c.execute(
            "SELECT to_jsonb(h) FROM football.product_match_history_decisions h "
            "ORDER BY decision_id"
        ).fetchall()
        c.execute("""CREATE FUNCTION football.test_correction_failure() RETURNS trigger
                     LANGUAGE plpgsql AS $$
                     BEGIN RAISE EXCEPTION 'injected correction failure'; END; $$""")
        c.execute("""CREATE TRIGGER zz_test_correction_failure
                     AFTER INSERT ON football.product_identity_admissions
                     FOR EACH ROW WHEN (NEW.corrects_decision_id IS NOT NULL)
                     EXECUTE FUNCTION football.test_correction_failure()""")
        with pytest.raises(psycopg.Error, match="injected correction failure"):
            correct_team_identity(c, tmp_path, request)
        assert (
            c.execute(
                "SELECT to_jsonb(a) FROM football.product_identity_admissions a "
                "ORDER BY decision_id"
            ).fetchall()
            == decisions
        )
        assert (
            c.execute(
                "SELECT to_jsonb(h) FROM football.product_match_history_decisions h "
                "ORDER BY decision_id"
            ).fetchall()
            == histories
        )
        assert retained(c) == before


@pytest.mark.parametrize(
    "change",
    ["target_mapping", "source_snapshot", "new_conflict", "file_tampering", "target_revocation"],
)
def test_later_invalidations_preserve_earlier_correction(tmp_path: Path, change: str) -> None:
    with psycopg.connect(DATABASE_URL) as c, c.transaction(force_rollback=True):
        request, _ = seed(c, tmp_path)
        first = correct_team_identity(c, tmp_path, request)
        t1 = c.execute("SELECT clock_timestamp()").fetchone()[0]
        expected = identity(c, request, t1)
        assert expected is not None
        if change == "target_mapping":
            c.execute(
                "UPDATE football.team_provider_mappings SET mapping_confidence=.5 WHERE id=%s",
                (request.target_mapping_id,),
            )
        elif change == "source_snapshot":
            c.execute(
                """UPDATE football.source_snapshots SET status='quarantined'
                         WHERE id=(SELECT source_snapshot_id FROM football.team_provider_mappings
                                   WHERE id=%s)""",
                (request.source_mapping_id,),
            )
        elif change == "new_conflict":
            c.execute(
                """INSERT INTO football.product_provider_mapping_decisions
                         (semantic_sha256,provider_code,provider_match_id,candidate_fixture_id,
                          disposition,reason,evidence,source_snapshot_id,observed_at)
                         SELECT %s,provider_code,provider_match_id,candidate_fixture_id,
                                disposition,'new conflict',evidence,source_snapshot_id,observed_at
                         FROM football.product_provider_mapping_decisions WHERE decision_id=%s""",
                ("d" * 64, request.original_decision_id),
            )
        elif change == "file_tampering":
            (tmp_path / "raw/football_data_org.json").write_bytes(b"tampered")
            with pytest.raises(ValueError):
                correct_team_identity(c, tmp_path, request)
            admit_provider_mappings(c, tmp_path, "football_data_org")
        else:
            c.execute(
                """INSERT INTO football.product_identity_admissions
                         (entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
                          disposition,reason,
                          source_snapshot_id,source_observed_at,evidence,evidence_sha256)
                         SELECT entity_type,mapping_id,canonical_id,provider_code,
                                provider_entity_id,
                                'REVOKED','OPERATOR_REVOKED',
                                source_snapshot_id,source_observed_at,evidence,evidence_sha256
                         FROM football.product_identity_admissions
                         WHERE mapping_id=%s AND disposition='ORIGIN_ANCHOR'""",
                (request.target_mapping_id,),
            )
        t2 = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert identity(c, request, t2) is None
        assert identity(c, request, t1) == expected
        assert c.execute(
            "SELECT corrects_decision_id FROM football.product_identity_admissions "
            "WHERE decision_id=%s",
            (UUID(first["decision_id"]),),
        ).fetchone() == (request.original_decision_id,)


def test_populated_upgrade_preserves_prior_r2_decisions_and_does_not_admit(tmp_path: Path) -> None:
    with isolated_database("202610130600") as url:
        with psycopg.connect(url) as c:
            request, other = seed(c, tmp_path)
            before = retained(c)
            t0 = c.execute("SELECT clock_timestamp()").fetchone()[0]
            admissions = c.execute(
                "SELECT to_jsonb(a) FROM football.product_identity_admissions a "
                "ORDER BY decision_id"
            ).fetchall()
            histories = c.execute(
                "SELECT to_jsonb(h) FROM football.product_match_history_decisions h "
                "ORDER BY decision_id"
            ).fetchall()
        _migrate(url, "up")
        _migrate(url, "up")
        with psycopg.connect(url) as c:
            assert retained(c) == before
            assert (
                c.execute(
                    "SELECT to_jsonb(a)-'corrects_decision_id'-'target_mapping_id' "
                    "FROM football.product_identity_admissions a ORDER BY decision_id"
                ).fetchall()
                == admissions
            )
            assert (
                c.execute(
                    "SELECT to_jsonb(h) FROM football.product_match_history_decisions h "
                    "ORDER BY decision_id"
                ).fetchall()
                == histories
            )
            assert history(c, t0) == []
            assert identity(c, request, c.execute("SELECT clock_timestamp()").fetchone()[0]) is None
            correct_team_identity(c, tmp_path, request)
            correct_team_identity(c, tmp_path, other)
            assert len(history(c, c.execute("SELECT clock_timestamp()").fetchone()[0])) == 1
            assert history(c, t0) == []
        down = subprocess.run(
            ["goose", "-dir", "infrastructure/migrations", "postgres", url, "down"],
            capture_output=True,
            text=True,
        )
        assert down.returncode != 0 and "forward-only" in down.stderr
