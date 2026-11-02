"""Native V4 registrations do not grant identity, model inputs or production routing."""

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from football.forecasting.contracts import PointInTimeScopeV1
from football.forecasting.dataset import ForecastingDatasetError, PointInTimeMatchDatasetProvider
from football.forecasting.runtime_models import ModelRegistration, PostgresModelRegistry
from football.product.api_football import ApiFootballClient
from football.product.domain import MODEL_ARTIFACT_PATH
from football.product.fixture_reconciliation import reconcile_product_fixtures
from football.product.historical_backfill import HistoricalBackfillStore
from football.product.historical_manifest import publish_manifest
from football.product.market_capability_cli import market_capability_report
from football.product.resolution_parity import verify_parity
from football.product.resolution_stages import qualify_stage
from football.product.sync import ProductSync
from football.providers.capability_registry import CapabilityRegistry, prepare_capability
from football.providers.normalization.cli import persist_normalization, registered_resource
from football.providers.normalization.pipeline import normalize_resource
from football.providers.resource_authority import AuthorityRegistry
from football.providers.resource_capabilities import ResourceCapability, ResourceScope
from football.temporal.repository import PointInTimeRepository
from football.work.contracts import RetryPolicy
from psycopg import sql

from tests.integration.test_concurrency_stress import _history
from tests.integration.test_team_identity_correction import isolated_database, seed
from tests.integration.test_understat_pipeline import _sample


def _protected(c):
    tables = (
        "matches",
        "teams",
        "team_provider_mappings",
        "product_identity_admissions",
        "product_provider_mapping_decisions",
        "canonical_resource_resolutions",
        "product_fixtures",
        "product_serving_fixtures",
        "fixture_read_model",
        "product_forecasts",
        "runtime_model_registrations",
        "model_promotion_events",
        "post_match_evaluations",
        "product_read_reports",
        "dataset_versions",
    )
    return {
        table: c.execute(
            sql.SQL("SELECT to_jsonb(t) FROM football.{} t ORDER BY to_jsonb(t)::text").format(
                sql.Identifier(table)
            )
        ).fetchall()
        for table in tables
    }


def _source(c, root, provider):
    import hashlib

    kind = {"espn": "scoreboard", "whoscored": "fixtures"}.get(provider, "league")
    if provider == "understat":
        kind = "results"
    known = c.execute("SELECT clock_timestamp()").fetchone()[0]
    path, resource_type, raw = _sample(provider, kind)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = publish_manifest(
        root,
        provider=provider,
        source_identity="v4-isolation/" + provider,
        source_revision=digest,
        acquired_at=known,
        resources=[(path, f"{provider}/raw/{digest}", raw)],
    )
    store = HistoricalBackfillStore(c, provider, provider, "v4-isolation", data_root=root)
    snapshot = store.ensure_snapshot(
        source_identity="v4-isolation/" + provider,
        source_revision=digest,
        acquired_at=known,
        manifest_path=manifest,
    )
    rid = store.record_resource(
        snapshot_id=snapshot,
        provider_path=path,
        payload=raw,
        media_type="text/javascript",
        acquired_at=known,
        import_pending=True,
    )
    context, retained = registered_resource(c, root, rid)
    return context, retained, resource_type


def _publish(c, root, provider):
    context, retained, resource_type = _source(c, root, provider)
    known = context.time.known_at
    rid = context.provenance.source_resource_id
    digest = context.provenance.source_sha256
    result = normalize_resource(context, resource_type, retained)
    assert result.observations and not result.findings
    persist_normalization(
        c,
        root,
        context,
        resource_type,
        result,
        worker="v4-isolation-test",
        lease=timedelta(minutes=1),
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1),
        max_attempts=1,
    )
    scope = ResourceScope(
        provider=provider,
        resource_type=resource_type,
        competition="test-native-league",
        season="2024",
    )
    capability = ResourceCapability(
        availability="PARTIAL",
        adapter_version="adapter-v1",
        normalizer_version="normalizer-v1",
        identity_quality="UNASSESSED",
    )
    CapabilityRegistry(c).register(
        prepare_capability(
            root,
            scope,
            capability,
            decided_at=known,
            reason="Development sample only",
            evidence_refs=(f"source_resource:{rid}:sha256:{digest}",),
        )
    )
    return context, result, scope


@pytest.mark.parametrize("provider", ["understat", "espn", "whoscored", "flashscore", "soccerway"])
def test_unqualified_v4_publication_cannot_change_authoritative_consumers(tmp_path, provider):
    with isolated_database() as url, psycopg.connect(url) as c:
        history, home, away = _history(c, tmp_path)
        seed(c, tmp_path)
        c.commit()
        c.autocommit = True
        with c.transaction():
            reconcile_product_fixtures(c)
        c.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model")
        product = ProductSync(c, ApiFootballClient("offline"), tmp_path, MODEL_ARTIFACT_PATH)
        earlier = c.execute("SELECT clock_timestamp()").fetchone()[0]
        targets = [(history[-1], home, away, earlier + timedelta(days=1))]
        before = _protected(c)
        assert before["product_forecasts"]  # Preserve actual published forecast values.
        history_before = product._batch_history(targets, earlier)
        assert history_before[home]  # Nonempty eligible feature history is the control.
        prepared_before = product._prepare_forecasts(earlier, None)
        context, result, scope = _publish(c, tmp_path, provider)
        known = context.time.known_at
        with c.transaction():
            reconcile_product_fixtures(c)
        c.execute("REFRESH MATERIALIZED VIEW football.fixture_read_model")
        assert _protected(c) == before
        assert product._batch_history(targets, earlier) == history_before
        assert product._batch_history(targets, known + timedelta(seconds=1)) == history_before
        assert product._prepare_forecasts(earlier, None) == prepared_before

        # Known native facts remain inspectable; that is not historical eligibility.
        pid = c.execute("SELECT id FROM football.providers WHERE code=%s", (provider,)).fetchone()[
            0
        ]
        reader = PointInTimeRepository(c)
        contract = "ResultObservationV2"
        assert any(contract == o.CONTRACT for o in result.observations)
        assert not reader.resource_observation_ids_at(contract, pid, earlier)
        assert reader.resource_observation_ids_at(contract, pid, known + timedelta(seconds=1))
        assert not reader.resource_observation_ids_at(
            contract, pid, known + timedelta(days=1), football_cutoff=known
        )  # V4 samples have no qualified event clock.

        # Capability allows only its exact acquisition scope; it cannot grant authority.
        registry = CapabilityRegistry(c)
        assert registry.plan(
            scope, adapter_version="adapter-v1", normalizer_version="normalizer-v1"
        ).allowed
        assert not registry.plan(
            scope, adapter_version="adapter-v1", normalizer_version="other"
        ).allowed
        other = ResourceScope(
            provider=provider, resource_type=scope.resource_type, competition="other", season="2024"
        )
        assert not registry.plan(
            other, adapter_version="adapter-v1", normalizer_version="normalizer-v1"
        ).allowed
        cutoff = c.execute("SELECT clock_timestamp()").fetchone()[0]
        assert AuthorityRegistry(c).at(scope, effective_at=known, knowledge_cutoff=cutoff) == ()
        report = market_capability_report(
            c, tmp_path, competition_id=uuid4(), season_id=uuid4(), knowledge_cutoff=cutoff
        )
        assert all(
            not r["publication"]["eligible_under_declared_evidence"] for r in report["markets"]
        )
        assert all(not r["publication"]["grants_new_publication"] for r in report["markets"])

        # Raw snapshot presence cannot substitute for a published dataset/source pair.
        scope_pit = PointInTimeScopeV1(
            dataset_version_id=uuid4(),
            source_snapshot_id=context.provenance.source_snapshot_id,
            feature_set_version="v1",
            football_cutoff=known,
            knowledge_cutoff=cutoff,
            knowledge_mode="bitemporal",
            quality_policy_sha256="0" * 64,
            target_set_sha256="1" * 64,
        )
        with pytest.raises(ForecastingDatasetError, match="published dataset/source pair"):
            PointInTimeMatchDatasetProvider(c).completed_history(scope_pit, uuid4(), uuid4())
        champion = ModelRegistration.from_bytes(
            Path("config/models/current-champion.json").read_bytes()
        )
        assert PostgresModelRegistry(c).get(champion.sha256, knowledge_cutoff=cutoff) is None
        with c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            parity = verify_parity(c, Path.cwd(), tmp_path, {})
        assert parity["status"] != "PASS"
        with pytest.raises(ValueError, match="complete production parity"):
            qualify_stage({"action": "SWITCH_STAGE"}, {"environment": "ISOLATED"})
        assert _protected(c) == before
