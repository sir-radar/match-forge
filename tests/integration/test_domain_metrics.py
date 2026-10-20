"""Domain exposition reads existing owners without acquiring work or calling providers."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from football.coverage.resources import CanonicalCoverage, CanonicalCoverageScope, ProviderCoverage
from football.coverage.storage import CoverageRegistry, prepare_coverage
from football.observability.domain_metrics import render_domain_metrics
from football.product.cli import main
from football.providers.resource_capabilities import ResourceScope
from psycopg.rows import dict_row

from tests.integration.test_live_context import COMPETITION, FIXTURE, SEASON
from tests.integration.test_postmatch import _run
from tests.integration.test_postmatch import monitored_database as monitored_database


def metrics(url, kickoff, **changes):
    with psycopg.connect(url, row_factory=dict_row) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        return render_domain_metrics(
            connection,
            **{
                "competitions": (COMPETITION,),
                "window_start": kickoff - timedelta(days=2),
                "window_end": kickoff + timedelta(days=4),
                "providers": ("api_football",),
                **changes,
            },
        )


def provider(connection):
    connection.execute(
        "INSERT INTO football.providers(code,name,source_type) VALUES "
        "('api_football','Metrics provider','http_api') ON CONFLICT DO NOTHING"
    )
    return connection.execute(
        "SELECT id FROM football.providers WHERE code='api_football'"
    ).fetchone()[0]


def test_readonly_export_keeps_unknowns_and_excludes_high_cardinality(monitored_database):
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        before = connection.execute(
            "SELECT (SELECT count(*) FROM football.work_items),"
            "(SELECT count(*) FROM football.post_match_evaluations)"
        ).fetchone()
    output = metrics(url, kickoff)
    assert "postmatch_log_loss NaN\n" in output
    assert "postmatch_samples 0\n" in output
    assert "feature_snapshot_samples 0\n" in output
    assert 'provider_coverage_ratio{provider="api_football",resource="results"} NaN\n' in output
    assert 'canonical_coverage_known_scopes{resource="results"} 0\n' in output
    assert "unresolved_team_identities 2\n" in output
    for forbidden in (
        "fixture_id=",
        "competition_id=",
        "season=",
        "work_id=",
        str(FIXTURE),
        "provider_match_id=",
    ):
        assert forbidden not in output
    with psycopg.connect(url) as connection:
        assert (
            connection.execute(
                "SELECT (SELECT count(*) FROM football.work_items),"
                "(SELECT count(*) FROM football.post_match_evaluations)"
            ).fetchone()
            == before
        )


def test_postmatch_metrics_follow_latest_correction_without_double_counting(monitored_database):
    url, kickoff = monitored_database
    assert _run(url, kickoff)["published"] == 1
    first = metrics(url, kickoff)
    assert "postmatch_samples 1\n" in first and "postmatch_coverage 1\n" in first
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET home_score=0,away_score=1,"
            "updated_at=clock_timestamp()"
        )
    assert _run(url, kickoff)["published"] == 1
    second = metrics(url, kickoff)
    assert "postmatch_samples 1\n" in second and "postmatch_coverage 1\n" in second
    assert next(
        line for line in first.splitlines() if line.startswith("postmatch_log_loss ")
    ) != next(line for line in second.splitlines() if line.startswith("postmatch_log_loss "))


def test_provider_measurements_use_reservations_jobs_and_real_acquisitions(monitored_database):
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        identity = provider(connection)
        connection.execute(
            "INSERT INTO football.provider_request_budgets(provider_code,window_date,"
            "requests_used) "
            "VALUES('api_football',current_date,3)"
        )
        sync = uuid4()
        connection.execute(
            "INSERT INTO football.provider_sync_runs(id,provider_id,policy_version,status,run_key) "
            "VALUES(%s,%s,'metrics-test','failed',%s)",
            (sync, identity, "a" * 64),
        )
        connection.execute(
            "INSERT INTO football.acquisition_jobs(sync_run_id,provider_id,resource_key,scope_key,"
            "resource_identity,resource_revision,status) VALUES(%s,%s,'fixtures',"
            "'private-native-scope',"
            "'private-native-fixture','v1','failed')",
            (sync, identity),
        )
        for kind, age in [
            ("REAL_PROVIDER", timedelta(minutes=5)),
            ("CONTRACT_FIXTURE", timedelta(minutes=1)),
            ("REAL_PROVIDER", timedelta(hours=-1)),
        ]:
            connection.execute(
                "INSERT INTO football.source_snapshots(provider_id,source_identity,source_revision,"
                "acquired_at,manifest_path,manifest_sha256,status,source_kind,fixture_id) "
                "VALUES(%s,%s,'v1',clock_timestamp()-%s,'tests/metrics.json',%s,'validated',%s,%s)",
                (
                    identity,
                    str(uuid4()),
                    age,
                    "b" * 64,
                    kind,
                    None if kind == "REAL_PROVIDER" else "metrics-fixture",
                ),
            )
    output = metrics(url, kickoff)
    assert 'provider_request_reservations{provider="api_football"} 3\n' in output
    assert 'provider_acquisition_failures{provider="api_football"} 1\n' in output
    age = float(
        next(
            line for line in output.splitlines() if line.startswith("provider_freshness_seconds{")
        ).split()[-1]
    )
    assert 300 <= age < 360
    assert "private-native" not in output
    assert "provider_requests_total" not in output and "provider_failures_total" not in output


def test_coverage_uses_latest_scope_reports_and_exposes_unknown_denominators(
    monitored_database, tmp_path: Path
):
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        provider(connection)
        known = connection.execute("SELECT transaction_timestamp()").fetchone()[0]
        registry = CoverageRegistry(connection)
        for days, qualified in [(2, ("one",)), (1, ("one", "two")), (3, ())]:
            report = ProviderCoverage(
                scope=ResourceScope(
                    provider="api_football",
                    resource_type="results",
                    competition="private-competition",
                    season="private-season",
                ),
                knowledge_cutoff=known - timedelta(days=days),
                expected_units=("one", "two"),
                observed_units=("one", "two"),
                qualified_units=qualified,
                evidence_refs=("explicit-eligible-universe",),
            )
            registry.register(prepare_coverage(tmp_path, report))
        report = ProviderCoverage(
            scope=ResourceScope(
                provider="api_football",
                resource_type="results",
                competition="another-scope",
                season=None,
            ),
            knowledge_cutoff=known,
            expected_units=None,
            observed_units=(),
            qualified_units=(),
            evidence_refs=("unknown-universe",),
        )
        registry.register(prepare_coverage(tmp_path, report))
        report = CanonicalCoverage(
            scope=CanonicalCoverageScope(
                competition_id=COMPETITION, season_id=SEASON, resource_type="results"
            ),
            knowledge_cutoff=known,
            expected_units=(FIXTURE, uuid4()),
            qualified_support=((FIXTURE, "api_football"),),
            evidence_refs=("canonical-qualification",),
        )
        registry.register(prepare_coverage(tmp_path, report))
        report = ProviderCoverage(
            scope=ResourceScope(
                provider="api_football",
                resource_type="private-resource-name",
                competition=None,
                season=None,
            ),
            knowledge_cutoff=known,
            expected_units=None,
            observed_units=(),
            qualified_units=(),
            evidence_refs=("unknown-resource",),
        )
        registry.register(prepare_coverage(tmp_path, report))
    output = metrics(url, kickoff)
    assert 'provider_coverage_ratio{provider="api_football",resource="results"} 1\n' in output
    assert 'provider_coverage_scopes{provider="api_football",resource="results"} 2\n' in output
    assert (
        'provider_coverage_known_scopes{provider="api_football",resource="results"} 1\n' in output
    )
    assert 'canonical_coverage_ratio{resource="results"} 0.5\n' in output
    assert 'provider_coverage_scopes{provider="api_football",resource="OTHER"} 1\n' in output
    assert "private-" not in output and "another-scope" not in output


def test_forecast_availability_and_identity_use_current_serving_state(monitored_database):
    url, kickoff = monitored_database
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET status='SCHEDULED',home_score=NULL,"
            "away_score=NULL,"
            "kickoff_at=clock_timestamp()+interval '1 day',"
            "forecast_availability='FORECAST_AVAILABLE' "
            "WHERE fixture_id=%s",
            (FIXTURE,),
        )
    assert "forecastable_fixtures 1\n" in metrics(url, kickoff)
    with psycopg.connect(url) as connection:
        connection.execute(
            "UPDATE football.product_fixtures SET identity_status='QUARANTINED' "
            "WHERE fixture_id=%s",
            (FIXTURE,),
        )
    output = metrics(url, kickoff)
    assert "forecastable_fixtures 0\n" in output and "unresolved_fixture_identities 1\n" in output


def test_operator_cli_is_readonly_and_rejects_unbounded_provider_labels(monitored_database, capsys):
    url, kickoff = monitored_database
    scope = [
        "--database-url",
        url,
        "domain-metrics",
        "--competition",
        str(COMPETITION),
        "--window-start",
        (kickoff - timedelta(days=1)).isoformat(),
        "--window-end",
        (kickoff + timedelta(days=1)).isoformat(),
    ]
    assert main(scope) == 0
    captured = capsys.readouterr()
    assert "postmatch_samples 0\n" in captured.out and not captured.err
    assert main([*scope, "--provider", "private-provider-id"]) == 1
    assert "unique registered adapter provider codes" in capsys.readouterr().err


def test_duplicate_metric_counts_members_and_keeps_representatives(monitored_database):
    url, kickoff = monitored_database
    duplicate, real = uuid4(), uuid4()
    with psycopg.connect(url) as connection:
        connection.execute(
            "INSERT INTO football.matches(id,competition_id,season_id) VALUES(%s,%s,%s)",
            (duplicate, COMPETITION, SEASON),
        )
        connection.execute(
            "INSERT INTO football.product_fixtures(fixture_id,competition_id,"
            "home_team_id,away_team_id,kickoff_at,status,home_score,away_score,"
            "forecast_availability,updated_at) SELECT %s,competition_id,home_team_id,away_team_id,"
            "kickoff_at,status,home_score,away_score,forecast_availability,updated_at "
            "FROM football.product_fixtures WHERE fixture_id=%s",
            (duplicate, FIXTURE),
        )
        for member in (FIXTURE, duplicate):
            connection.execute(
                "INSERT INTO football.fixture_identity_resolutions("
                "canonical_real_fixture_id,member_fixture_id,representative_fixture_id,"
                "resolution_status,selected_competition_id,resolution_reason,evidence_json,"
                "evidence_sha256,resolution_version,created_at) "
                "VALUES(%s,%s,%s,'DUPLICATE_RESOLVED',%s,'metrics test','{}',%s,'metrics',"
                "clock_timestamp())",
                (real, member, FIXTURE, COMPETITION, "c" * 64),
            )
    output = metrics(url, kickoff)
    assert "canonical_fixture_duplicates 1\n" in output
    assert "unresolved_fixture_identities 0\n" in output


def test_cli_reads_only_explicit_schema_and_checksum_bound_feature_exports(
    monitored_database, tmp_path, capsys
):
    from football.contracts.source import canonical_json_bytes
    from football.forecasting.features import FixtureFeatureSnapshotV1
    from football.forecasting.model_contracts import CompetitionContext
    from football.forecasting.snapshot import build_forecast_snapshot

    from tests.integration.test_live_context import AWAY, HOME

    url, kickoff = monitored_database
    feature = FixtureFeatureSnapshotV1(
        build_forecast_snapshot(
            fixture_id=FIXTURE,
            competition_id=COMPETITION,
            competition_context=CompetitionContext.LEAGUE,
            season_label="2026",
            kickoff_at=kickoff,
            home_team_id=HOME,
            away_team_id=AWAY,
            football_cutoff=kickoff - timedelta(hours=25),
            knowledge_cutoff=kickoff - timedelta(hours=25),
            knowledge_mode="bitemporal",
            history=(),
        )
    )
    path = tmp_path / "explicit-feature.json"
    path.write_bytes(canonical_json_bytes(feature.to_dict()))
    scope = [
        "--database-url",
        url,
        "domain-metrics",
        "--competition",
        str(COMPETITION),
        "--window-start",
        (kickoff - timedelta(days=1)).isoformat(),
        "--window-end",
        (kickoff + timedelta(days=1)).isoformat(),
        "--feature-snapshot",
        feature.sha256,
        str(path),
    ]
    assert main(scope) == 0
    captured = capsys.readouterr()
    assert "feature_snapshot_samples 1\n" in captured.out and not captured.err
    changed = feature.to_dict()
    changed["quality"] = []
    path.write_bytes(canonical_json_bytes(changed))
    assert main(scope) == 1
    captured = capsys.readouterr()
    assert not captured.out and "feature snapshot checksum mismatch" in captured.err
