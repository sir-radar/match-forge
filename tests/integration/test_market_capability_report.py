from __future__ import annotations

import json
import os
from io import StringIO
from uuid import uuid4

import psycopg
import pytest
from football.cli.main import run
from football.coverage.resources import CanonicalCoverage, CanonicalCoverageScope
from football.coverage.storage import CoverageRegistry, prepare_coverage
from football.forecasting.market_catalogue import market_catalogue
from football.product.market_capabilities import market_input_key
from football.product.market_capability_cli import market_capability_report
from football.providers.capability_registry import CapabilityRegistry, prepare_capability
from football.providers.resource_capabilities import ResourceCapability, ResourceScope


def test_registered_sources_and_coverage_remain_read_only_and_knowledge_scoped(tmp_path):
    counts_query = (
        "SELECT (SELECT count(*) FROM football.provider_resource_capabilities),"
        "(SELECT count(*) FROM football.canonical_resource_coverage),"
        "(SELECT count(*) FROM football.work_items),"
        "(SELECT count(*) FROM football.runtime_model_registrations)"
    )
    with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection:
        provider = "market_" + uuid4().hex
        connection.execute(
            "INSERT INTO football.providers(code,name,source_type) VALUES (%s,%s,'manual')",
            (provider, provider),
        )
        competition = connection.execute(
            "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
        ).fetchone()[0]
        season = connection.execute(
            "INSERT INTO football.seasons(competition_id) VALUES (%s) RETURNING id", (competition,)
        ).fetchone()[0]
        before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        scope = ResourceScope(
            provider=provider, resource_type="results", competition="native", season="native-season"
        )
        capability = prepare_capability(
            tmp_path,
            scope,
            ResourceCapability(
                availability="SUPPORTED", adapter_version="test", normalizer_version="test"
            ),
            decided_at=before,
            reason="Synthetic access evidence",
            evidence_refs=("test:access",),
        )
        CapabilityRegistry(connection).register(capability)
        target = next(row for row in market_catalogue() if row.market_id == "RESULT_1X2")
        fixture = uuid4()
        coverage = CanonicalCoverage(
            scope=CanonicalCoverageScope(
                competition_id=competition,
                season_id=season,
                resource_type=market_input_key(target, "regulation_score"),
            ),
            knowledge_cutoff=before,
            expected_units=None,
            qualified_support=((fixture, provider),),
            evidence_refs=("test:eligible-unit",),
        )
        CoverageRegistry(connection).register(prepare_coverage(tmp_path, coverage))
        after = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        counts = connection.execute(counts_query).fetchone()
        earlier = market_capability_report(
            connection,
            tmp_path,
            competition_id=competition,
            season_id=season,
            knowledge_cutoff=before,
        )
        current = market_capability_report(
            connection,
            tmp_path,
            competition_id=competition,
            season_id=season,
            knowledge_cutoff=after,
        )
        old = next(row for row in earlier["markets"] if row["market"]["market_id"] == "RESULT_1X2")
        new = next(row for row in current["markets"] if row["market"]["market_id"] == "RESULT_1X2")
        assert old["qualified_historical_coverage"]["regulation_score"] is None
        assert (
            new["qualified_historical_coverage"]["regulation_score"]["metrics"][
                "expected_canonical_units"
            ]
            is None
        )
        assert (
            new["qualified_historical_coverage"]["regulation_score"]["metrics"][
                "qualified_canonical_units"
            ]
            == 1
        )
        assert not any(item["scope"]["provider"] == provider for item in old["provider_sources"])
        assert any(item["scope"]["provider"] == provider for item in new["provider_sources"])
        assert new["diagnostic_status"] == "DATA_COLLECTION_REQUIRED"
        assert new["publication"]["current_status"] == "UNKNOWN"
        assert current["read_only"] == "on"
        assert not any(row["publication"]["grants_new_publication"] for row in current["markets"])
        assert connection.execute(counts_query).fetchone() == counts
        output, errors = StringIO(), StringIO()
        code = run(
            [
                "--data-root",
                str(tmp_path),
                "models",
                "market-capabilities",
                "--competition-id",
                str(competition),
                "--season-id",
                str(season),
                "--knowledge-cutoff",
                after.isoformat(),
            ],
            environ={"DATABASE_URL": os.environ["TEST_DATABASE_URL"]},
            stdout=output,
            stderr=errors,
        )
        assert code == 0 and not errors.getvalue()
        assert json.loads(output.getvalue())["contract"] == "MarketCapabilityReport"


def test_market_report_does_not_commit_a_caller_transaction(tmp_path):
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as connection,
        connection.transaction(force_rollback=True),
    ):
        stamp = connection.execute("SELECT clock_timestamp()").fetchone()[0]
        with pytest.raises(ValueError, match="idle connection"):
            market_capability_report(
                connection,
                tmp_path,
                competition_id=uuid4(),
                season_id=uuid4(),
                knowledge_cutoff=stamp,
            )
        assert connection.execute("SELECT 1").fetchone() == (1,)
