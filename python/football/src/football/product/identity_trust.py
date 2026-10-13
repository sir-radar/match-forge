"""Shared product identity qualification; confidence is never evidence by itself."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from football.product.domain import stable_id
from football.product.identity_crosswalks import (
    COMPETITION_CROSSWALKS,
    OPERATIONAL_COMPETITION_CROSSWALKS,
    OPERATIONAL_TEAM_CROSSWALKS,
    canonical_team_provider_identity,
)

IdentityDisposition = Literal["ORIGIN_ANCHOR", "CROSSWALK", "UNRESOLVED", "CONTRADICTORY"]


@dataclass(frozen=True, slots=True)
class MappingEvidence:
    entity_type: Literal["team", "competition"]
    canonical_id: UUID
    provider: str
    provider_id: str
    method: str
    confidence: float
    country: str | None
    source_verified: bool
    source_identifier_verified: bool
    crosswalk_target: UUID | None = None
    crosswalk_context_verified: bool = False
    manual_evidence_verified: bool = False


def qualify_mapping(evidence: MappingEvidence) -> tuple[IdentityDisposition, str]:
    if not evidence.source_verified or not evidence.source_identifier_verified:
        return "UNRESOLVED", "RETAINED_SOURCE_EVIDENCE_REQUIRED"
    if evidence.confidence != 1:
        return "UNRESOLVED", "FULL_CONFIDENCE_REQUIRED"
    if evidence.method == "deterministic":
        expected = origin_id(
            evidence.entity_type, evidence.provider, evidence.provider_id, evidence.country
        )
        if expected is None:
            return "UNRESOLVED", "UNSUPPORTED_ORIGIN_ALGORITHM"
        if evidence.canonical_id != expected:
            return "CONTRADICTORY", "ORIGIN_UUID_MISMATCH"
        return "ORIGIN_ANCHOR", "VERIFIED_PROVIDER_ORIGIN"
    if evidence.method == "explicit_crosswalk":
        if evidence.crosswalk_target is None or not evidence.crosswalk_context_verified:
            return "UNRESOLVED", "VERIFIABLE_CROSSWALK_AND_CONTEXT_REQUIRED"
        if evidence.canonical_id != evidence.crosswalk_target:
            return "CONTRADICTORY", "CROSSWALK_UUID_MISMATCH"
        return "CROSSWALK", "VERIFIED_EXPLICIT_CROSSWALK"
    if evidence.method == "manual" and evidence.manual_evidence_verified:
        return "CROSSWALK", "VERIFIED_OPERATOR_REVIEW"
    return "UNRESOLVED", "REVIEW_EVIDENCE_REQUIRED"


def origin_id(
    entity_type: str,
    provider: str,
    provider_id: str,
    country: str | None,
) -> UUID | None:
    if provider in {"api_football", "football_data_org"}:
        return stable_id(entity_type, provider, provider_id)
    if provider in {"openfootball", "football_data_uk"} and country:
        return stable_id(entity_type, provider, provider_id, country)
    return None


def explicit_target(entity_type: str, provider: str, provider_id: str) -> tuple[str, str] | None:
    if entity_type == "team":
        return canonical_team_provider_identity(
            provider, provider_id
        ) or OPERATIONAL_TEAM_CROSSWALKS.get((provider, provider_id))
    target = COMPETITION_CROSSWALKS.get(provider, {}).get(provider_id)
    if target is not None:
        return target
    operational = OPERATIONAL_COMPETITION_CROSSWALKS.get((provider, provider_id))
    return (operational[0], operational[1]) if operational is not None else None
