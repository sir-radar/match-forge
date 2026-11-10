"""Read-only market readiness; provider access is not predictive qualification."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from football.contracts.source import canonical_json_bytes
from football.coverage.resources import CanonicalCoverage
from football.forecasting.market_catalogue import MarketDefinition
from football.forecasting.runtime_models import ModelRegistration
from football.providers.capability_registry import RegisteredCapability
from football.providers.resource_capabilities import ResourceScope


class MarketStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    SHADOW = "SHADOW"
    ENGINEERING_READY = "ENGINEERING_READY"
    RESEARCH_REQUIRED = "RESEARCH_REQUIRED"
    DATA_COLLECTION_REQUIRED = "DATA_COLLECTION_REQUIRED"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    INSUFFICIENT_PLAYER_DATA = "INSUFFICIENT_PLAYER_DATA"
    SEMANTIC_MISMATCH = "SEMANTIC_MISMATCH"
    BLOCKED = "BLOCKED"


class SourceCompatibility(StrEnum):
    EXACT_OR_VERIFIED_EQUIVALENT = "EXACT_OR_VERIFIED_EQUIVALENT"
    TRANSFORMABLE_WITH_EVIDENCE = "TRANSFORMABLE_WITH_EVIDENCE"
    NORMALIZABLE = "NORMALIZABLE"
    RESEARCH_COMPATIBLE_ONLY = "RESEARCH_COMPATIBLE_ONLY"
    INCOMPATIBLE = "INCOMPATIBLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MarketSource:
    scope: ResourceScope
    registration: RegisteredCapability | None

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.to_dict(),
            "decision_id": str(self.registration.decision_id) if self.registration else None,
            "known_at": self.registration.known_at.isoformat() if self.registration else None,
            "capability": self.registration.capability.to_dict() if self.registration else None,
            "field_coverage": None,
            "semantic_compatibility": "UNKNOWN",
            "canonical_scope_relation": "UNASSESSED",
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class MarketQualification:
    """Evidence supplied by existing eligibility, semantic, model and promotion owners.

    This declaration is diagnostic input, not an approval. Coverage keys bind the
    exact market target and input, avoiding reuse of generic resource counts as
    proof that a particular field is present and semantically eligible.
    """

    competition_id: UUID
    season_id: UUID
    knowledge_cutoff: datetime
    parameters: tuple[tuple[str, str | int | float], ...] = ()
    history: tuple[CanonicalCoverage, ...] = ()
    compatibility: SourceCompatibility = SourceCompatibility.UNKNOWN
    semantic_version: str | None = None
    semantic_refs: tuple[str, ...] = ()
    transform_ref: str | None = None
    history_sufficient: bool | None = None
    history_policy_ref: str | None = None
    model: ModelRegistration | None = None
    evaluation_status: str = "UNASSESSED"
    evaluation_ref: str | None = None
    publication_status: str = "UNKNOWN"
    publication_ref: str | None = None
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.competition_id, UUID) or not isinstance(self.season_id, UUID):
            raise ValueError("market scope requires canonical competition and season UUIDs")
        if self.knowledge_cutoff.utcoffset() is None:
            raise ValueError("market knowledge cutoff requires a timezone")
        if not isinstance(self.compatibility, SourceCompatibility):
            raise ValueError("market compatibility requires its explicit enum")
        if self.history_sufficient is not None and type(self.history_sufficient) is not bool:
            raise ValueError("history sufficiency must be a boolean or unknown")
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "semantic_refs", tuple(self.semantic_refs))
        parameters = tuple((name, value) for name, value in self.parameters)
        _validate_parameters(parameters)
        object.__setattr__(self, "parameters", tuple(sorted(parameters)))
        _validate_claims(self)


def _validate_parameters(parameters: tuple[tuple[str, str | int | float], ...]) -> None:
    names = [name for name, _ in parameters]
    if len(names) != len(set(names)) or any(
        not isinstance(name, str) or not name for name in names
    ):
        raise ValueError("target parameters require unique named values")
    for name, value in parameters:
        if type(value) not in {str, int, float}:
            raise ValueError("target parameter must be text or a finite number; missing is omitted")
        if isinstance(value, str) and not value.strip():
            raise ValueError("target parameter cannot be blank")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("target parameter must be finite")
        if name in {"team", "player"}:
            UUID(str(value))


def market_target_sha256(
    market: MarketDefinition, parameters: tuple[tuple[str, str | int | float], ...] = ()
) -> str:
    _validate_parameters(parameters)
    if not set(dict(parameters)) <= set(market.parameters):
        raise ValueError("target parameter is not defined by this market")
    return hashlib.sha256(
        canonical_json_bytes(
            {
                "definition_sha256": market.sha256,
                "parameters": dict(parameters),
            }
        )
    ).hexdigest()


def _validate_claims(evidence: MarketQualification) -> None:
    if evidence.evaluation_status not in {"UNASSESSED", "PASS", "PASS_WITH_WARNINGS", "FAIL"}:
        raise ValueError("invalid market evaluation status")
    if evidence.publication_status not in {
        "UNKNOWN",
        "NOT_PUBLISHED",
        "SHADOW",
        "PUBLISHED",
        "SUSPENDED",
    }:
        raise ValueError("invalid current publication status")
    claims = (
        (evidence.history_sufficient is not None, evidence.history_policy_ref),
        (evidence.evaluation_status != "UNASSESSED", evidence.evaluation_ref),
        (
            evidence.publication_status in {"SHADOW", "PUBLISHED", "SUSPENDED"},
            evidence.publication_ref,
        ),
    )
    if any(claim and (not reference or not reference.strip()) for claim, reference in claims):
        raise ValueError("market claims require their existing owner evidence references")
    if evidence.compatibility != SourceCompatibility.UNKNOWN and (
        not evidence.semantic_version or not evidence.semantic_refs
    ):
        raise ValueError("semantic compatibility requires exact target version and evidence")
    if any(not ref.strip() for ref in evidence.semantic_refs):
        raise ValueError("semantic evidence references cannot be blank")


def market_input_key(
    market: MarketDefinition,
    requirement: str,
    parameters: tuple[tuple[str, str | int | float], ...] = (),
) -> str:
    if requirement not in market.requirements:
        raise ValueError("input is not required by this market")
    return (
        f"market:{market.market_id}:{market_target_sha256(market, parameters)}:input:{requirement}"
    )


def _history_by_input(
    market: MarketDefinition, evidence: MarketQualification
) -> dict[str, CanonicalCoverage]:
    expected = {
        market_input_key(market, key, evidence.parameters): key for key in market.requirements
    }
    result = {}
    for report in evidence.history:
        scope = report.scope
        if (scope.competition_id, scope.season_id) != (evidence.competition_id, evidence.season_id):
            raise ValueError("market coverage belongs to another canonical scope")
        if report.knowledge_cutoff > evidence.knowledge_cutoff:
            raise ValueError("market coverage exceeds its knowledge cutoff")
        key = expected.get(scope.resource_type)
        if key is None or key in result:
            raise ValueError("market coverage must bind one exact target/input without duplicates")
        result[key] = report
    return result


def _data_diagnosis(
    market: MarketDefinition, evidence: MarketQualification, history: dict[str, CanonicalCoverage]
) -> tuple[MarketStatus, str | None, str] | None:
    if any(
        key not in history or not history[key].qualified_units
        for key in market.requirements
        if key in {"player_identity", "membership", "participation"}
    ):
        return (
            MarketStatus.INSUFFICIENT_PLAYER_DATA,
            "PLAYER_HISTORY_UNQUALIFIED",
            "Qualify native identity, time-aware membership, participation and exposure.",
        )
    if any(key not in history or not history[key].qualified_units for key in market.requirements):
        return (
            MarketStatus.DATA_COLLECTION_REQUIRED,
            "TARGET_INPUTS_UNQUALIFIED",
            "Publish exact field/period/target coverage through existing eligibility owners.",
        )
    common = set.intersection(*(set(history[key].qualified_units) for key in market.requirements))
    if not common:
        return (
            MarketStatus.INSUFFICIENT_HISTORY,
            "NO_COMMON_ELIGIBLE_FIXTURES",
            "Qualify the component inputs on the same canonical fixtures.",
        )
    if set(dict(evidence.parameters)) != set(market.parameters):
        return (
            MarketStatus.DATA_COLLECTION_REQUIRED,
            "TARGET_PARAMETERS_UNBOUND",
            "Bind the exact player/team, line, selection and settlement-rule parameters.",
        )
    if evidence.history_sufficient is False:
        return (
            MarketStatus.INSUFFICIENT_HISTORY,
            "HISTORY_POLICY_NOT_MET",
            "Collect eligible history against the frozen policy.",
        )
    return None


def _diagnosis(
    market: MarketDefinition, evidence: MarketQualification, history: dict[str, CanonicalCoverage]
) -> tuple[MarketStatus, str | None, str]:
    if evidence.blocker or evidence.publication_status == "SUSPENDED":
        return (
            MarketStatus.BLOCKED,
            evidence.blocker or "PUBLICATION_SUSPENDED",
            "Resolve the existing owner blocker.",
        )
    if evidence.compatibility == SourceCompatibility.INCOMPATIBLE:
        return (
            MarketStatus.SEMANTIC_MISMATCH,
            "SOURCE_TARGET_MISMATCH",
            "Qualify a compatible source or an evidenced transformation.",
        )
    data_issue = _data_diagnosis(market, evidence, history)
    if data_issue is not None:
        return data_issue
    if not _semantics_match(market, evidence):
        return (
            MarketStatus.DATA_COLLECTION_REQUIRED,
            "TARGET_SEMANTICS_UNQUALIFIED",
            "Qualify source definitions, period, participation, void rules and corrections.",
        )
    if not _model_ready(market, evidence):
        return (
            MarketStatus.RESEARCH_REQUIRED,
            "MODEL_OR_EVALUATION_UNQUALIFIED",
            "Use the existing research/evaluation/promotion workflow; do not enable publication.",
        )
    if evidence.publication_status == "PUBLISHED":
        return (
            MarketStatus.SUPPORTED,
            None,
            "Preserve the existing publication scope; validate each forecast separately.",
        )
    if evidence.publication_status == "SHADOW":
        return MarketStatus.SHADOW, None, "Retain shadow execution and existing promotion gates."
    return (
        MarketStatus.ENGINEERING_READY,
        "PUBLICATION_NOT_APPROVED",
        "Obtain the existing scoped publication approval; this diagnostic grants none.",
    )


def _semantics_match(market: MarketDefinition, evidence: MarketQualification) -> bool:
    exact = evidence.compatibility == SourceCompatibility.EXACT_OR_VERIFIED_EQUIVALENT
    transformed = (
        evidence.compatibility == SourceCompatibility.TRANSFORMABLE_WITH_EVIDENCE
        and bool(evidence.transform_ref and evidence.transform_ref.strip())
    )
    research = evidence.compatibility == SourceCompatibility.RESEARCH_COMPATIBLE_ONLY
    return evidence.semantic_version == market.semantic_version and (
        exact or transformed or research
    )


def _model_ready(market: MarketDefinition, evidence: MarketQualification) -> bool:
    model = evidence.model
    if model is None or model.lifecycle_state == "RETIRED" or market.implementation is None:
        return False
    if evidence.publication_status == "PUBLISHED" and model.lifecycle_state != "CHAMPION":
        return False
    if model.training_cutoff > evidence.knowledge_cutoff:
        return False
    if evidence.compatibility == SourceCompatibility.RESEARCH_COMPATIBLE_ONLY:
        return False
    competition_ok = (
        model.eligible_competitions is None
        or evidence.competition_id in model.eligible_competitions
    )
    return (
        competition_ok
        and market.model_product in model.eligible_products
        and evidence.history_sufficient is True
        and evidence.evaluation_status in {"PASS", "PASS_WITH_WARNINGS"}
        and bool(model.evaluation_refs)
    )


def assess_market(
    market: MarketDefinition,
    evidence: MarketQualification,
    sources: tuple[MarketSource, ...] = (),
) -> dict[str, Any]:
    """Describe existing state. Never fit, activate, withdraw or issue a forecast."""
    for source in sources:
        if source.registration and source.registration.known_at > evidence.knowledge_cutoff:
            raise ValueError("provider capability exceeds market knowledge cutoff")
    if (
        evidence.semantic_version is not None
        and evidence.semantic_version != market.semantic_version
    ):
        raise ValueError("semantic qualification belongs to another target version")
    history = _history_by_input(market, evidence)
    status, blocker, action = _diagnosis(market, evidence, history)
    return {
        "market": market.to_dict(),
        "definition_sha256": market.sha256,
        "target_sha256": market_target_sha256(market, evidence.parameters),
        "target_parameters": dict(evidence.parameters),
        "scope": {
            "competition_id": str(evidence.competition_id),
            "season_id": str(evidence.season_id),
        },
        "knowledge_cutoff": evidence.knowledge_cutoff.isoformat(),
        "diagnostic_status": status.value,
        "diagnostic_blocker": blocker,
        "next_action": action,
        "qualified_historical_coverage": {
            key: history[key].to_dict() if key in history else None for key in market.requirements
        },
        "provider_sources": [source.to_dict() for source in sources],
        "source_compatibility": evidence.compatibility.value,
        "qualified_semantic_version": evidence.semantic_version,
        "semantic_evidence_refs": list(evidence.semantic_refs),
        "transformation_evidence_ref": evidence.transform_ref,
        "history_policy": {
            "sufficient": evidence.history_sufficient,
            "existing_evidence_ref": evidence.history_policy_ref,
        },
        "model": evidence.model.to_dict() if evidence.model else None,
        "implementation": market.implementation,
        "evaluation": {
            "status": evidence.evaluation_status,
            "evidence_ref": evidence.evaluation_ref,
        },
        "publication": {
            "current_status": evidence.publication_status,
            "existing_evidence_ref": evidence.publication_ref,
            "eligible_under_declared_evidence": status == MarketStatus.SUPPORTED,
            "grants_new_publication": False,
        },
        "authoritative": False,
    }
