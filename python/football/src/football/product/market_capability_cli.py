"""Inspect market evidence through existing registries, without publication."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.pq import TransactionStatus

from football.coverage.resources import CanonicalCoverage, CanonicalCoverageScope
from football.coverage.storage import CoverageRegistry, load_coverage
from football.forecasting.market_catalogue import INPUTS, market_catalogue
from football.forecasting.runtime_models import ModelRegistration
from football.product.market_capabilities import (
    MarketQualification,
    MarketSource,
    assess_market,
    market_input_key,
)
from football.providers.capability_registry import CapabilityRegistry
from football.providers.resource_capabilities import ResourceScope


def market_capability_report(
    connection: Connection[Any],
    root: Path,
    *,
    competition_id: UUID,
    season_id: UUID,
    knowledge_cutoff: datetime,
    model: ModelRegistration | None = None,
) -> dict[str, Any]:
    """One read-only snapshot; native source scopes never imply a canonical join.

    This reports unbound market families. Exact target parameters and semantic,
    history, evaluation and publication owner decisions still need qualification.
    Existing forecast publication is not inferred, enabled or withdrawn here.
    """
    if connection.info.transaction_status != TransactionStatus.IDLE:
        raise ValueError("market report requires an idle connection")
    base = MarketQualification(
        competition_id=competition_id, season_id=season_id, knowledge_cutoff=knowledge_cutoff
    )
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        scopes = connection.execute(
            """SELECT DISTINCT p.code,r.resource_type,
            r.competition_key,r.season_key FROM football.provider_resource_capabilities r
            JOIN football.providers p ON p.id=r.provider_id WHERE r.known_at<=%s
            ORDER BY 1,2,3,4""",
            (knowledge_cutoff,),
        ).fetchall()
        native_scopes = tuple(
            ResourceScope(
                provider=provider,
                resource_type=resource,
                competition=competition,
                season=season,
            )
            for provider, resource, competition, season in scopes
        )
        registry = CapabilityRegistry(connection)
        sources = tuple(
            MarketSource(scope, registry.at(scope, knowledge_cutoff)) for scope in native_scopes
        )
        rows = []
        coverage = CoverageRegistry(connection)
        for market in market_catalogue():
            history = []
            for requirement in market.requirements:
                record = coverage.canonical_at(
                    CanonicalCoverageScope(
                        competition_id=competition_id,
                        season_id=season_id,
                        resource_type=market_input_key(market, requirement),
                    ),
                    knowledge_cutoff,
                )
                if record is not None:
                    history.append(CanonicalCoverage.from_dict(load_coverage(root, record)))
            resources = {
                resource for key in market.requirements for resource in INPUTS[key].resources
            }
            applicable = tuple(
                source for source in sources if source.scope.resource_type in resources
            )
            eligible_model = (
                model
                if model is not None and market.model_product in model.eligible_products
                else None
            )
            rows.append(
                assess_market(
                    market, replace(base, history=tuple(history), model=eligible_model), applicable
                )
            )
        snapshot = connection.execute(
            "SELECT current_database(),transaction_timestamp(),"
            "current_setting('transaction_read_only')"
        ).fetchone()
        assert snapshot is not None
    return {
        "contract": "MarketCapabilityReport",
        "contract_version": "1",
        "database": snapshot[0],
        "recorded_at": snapshot[1].isoformat(),
        "read_only": snapshot[2],
        "competition_id": str(competition_id),
        "season_id": str(season_id),
        "knowledge_cutoff": knowledge_cutoff.isoformat(),
        "markets": rows,
        "limitations": [
            "Market families are unbound; qualification must bind exact target parameters "
            "and semantic versions.",
            "Provider scope/access is reported separately from field, canonical identity "
            "and target qualification.",
            "Unknown publication status does not withdraw or approve any existing forecast route.",
            "No provider request, new probability, model fit, promotion "
            "or operating mutation is performed.",
        ],
    }


def market_capability_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Bounded operator projection of the existing diagnostic report, not forecasts."""
    markets = []
    providers = {}
    for row in report["markets"]:
        model = row["model"]
        markets.append(
            {
                "market_id": row["market"]["market_id"],
                "group": row["market"]["group"],
                "semantic_version": row["market"]["semantic_contract"]["version"],
                "definition_sha256": row["definition_sha256"],
                "status": row["diagnostic_status"],
                "unavailable_reason": row["diagnostic_blocker"],
                "next_action": row["next_action"],
                "source_compatibility": row["source_compatibility"],
                "unqualified_inputs": [
                    key
                    for key, value in row["qualified_historical_coverage"].items()
                    if value is None
                ],
                "model_id": model["model_id"] if model else None,
                "model_version": model["version"] if model else None,
                "model_artifact_sha256": model["artifact_hash"] if model else None,
                "model_role": model["lifecycle_state"] if model else None,
                "evaluation_status": row["evaluation"]["status"],
                "publication_status": row["publication"]["current_status"],
                "publication_eligible": row["publication"]["eligible_under_declared_evidence"],
            }
        )
        for source in row["provider_sources"]:
            scope = source["scope"]
            key = (
                scope["provider"],
                scope["resource_type"],
                (source["capability"] or {}).get("availability", "UNKNOWN"),
            )
            providers[key] = dict(zip(("provider", "resource", "availability"), key, strict=True))
    return {
        "contract": "MarketCapabilitySummary",
        "contract_version": "1",
        **{
            key: report[key]
            for key in (
                "competition_id",
                "season_id",
                "knowledge_cutoff",
                "recorded_at",
                "read_only",
                "limitations",
            )
        },
        "authoritative": False,
        "markets": markets,
        "provider_candidates": [providers[key] for key in sorted(providers)],
        "monitoring_scope": "EXISTING_PUBLISHED_GOAL_FORECASTS_ONLY",
        "new_market_settlement": "NOT_IMPLEMENTED",
        "automatic_promotion": False,
    }
