from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football.ingestion import ResolutionDecisionV1

FootballDataUkTeamResolutionStatusV1 = Literal["RESOLVED", "REVIEW_REQUIRED", "QUARANTINED"]


class FootballDataUkTeamResolutionError(ValueError):
    """A Football-Data team label lacks a safe reviewed canonical resolution."""


@dataclass(frozen=True, slots=True)
class FootballDataUkTeamCrosswalkV1:
    provider_team_label: str
    canonical_team_id: str
    evidence_refs: tuple[str, ...]
    version: str
    contract: str = "FootballDataUkTeamCrosswalkV1"

    def __post_init__(self) -> None:
        if self.contract != "FootballDataUkTeamCrosswalkV1":
            raise FootballDataUkTeamResolutionError("unsupported team crosswalk contract")
        if not self.provider_team_label or not self.canonical_team_id or not self.version:
            raise FootballDataUkTeamResolutionError("team crosswalk identity is required")
        if not self.evidence_refs or any(not ref for ref in self.evidence_refs):
            raise FootballDataUkTeamResolutionError("team crosswalk evidence is required")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise FootballDataUkTeamResolutionError("team crosswalk evidence must be unique")


class FootballDataUkTeamCrosswalkRegistryV1:
    def __init__(
        self,
        crosswalks: tuple[FootballDataUkTeamCrosswalkV1, ...],
        *,
        version: str = "FootballDataUkStatsBombTeamCrosswalkV1",
    ) -> None:
        if not version:
            raise FootballDataUkTeamResolutionError("team crosswalk version is required")
        labels = [crosswalk.provider_team_label for crosswalk in crosswalks]
        if len(labels) != len(set(labels)):
            raise FootballDataUkTeamResolutionError("team crosswalk labels must be unique")
        if any(crosswalk.version != version for crosswalk in crosswalks):
            raise FootballDataUkTeamResolutionError("team crosswalk versions must match registry")
        self.version = version
        self._by_label = {crosswalk.provider_team_label: crosswalk for crosswalk in crosswalks}

    def get(self, provider_team_label: str) -> FootballDataUkTeamCrosswalkV1 | None:
        return self._by_label.get(provider_team_label)


@dataclass(frozen=True, slots=True)
class FootballDataUkTeamResolutionV1:
    status: FootballDataUkTeamResolutionStatusV1
    provider_team_label: str
    candidate_canonical_ids: tuple[str, ...]
    selected_canonical_team_id: str | None
    decision: ResolutionDecisionV1 | None
    reason: str


def resolve_football_data_uk_team(
    *,
    provider_team_label: str,
    candidate_canonical_ids: tuple[str, ...],
    registry: FootballDataUkTeamCrosswalkRegistryV1,
    source_evidence_ref: str,
    decision_id: str,
    created_at: datetime,
) -> FootballDataUkTeamResolutionV1:
    """Resolve only a reviewed exact provider-label mapping; never infer from names."""

    _validate_resolution_input(
        provider_team_label, candidate_canonical_ids, source_evidence_ref, decision_id
    )
    crosswalk = registry.get(provider_team_label)
    if crosswalk and candidate_canonical_ids == (crosswalk.canonical_team_id,):
        decision = ResolutionDecisionV1(
            decision_id=decision_id,
            subject_type="team",
            provider_id="football_data_uk",
            provider_entity_id=provider_team_label,
            evidence_refs=(source_evidence_ref, *crosswalk.evidence_refs),
            candidate_canonical_ids=candidate_canonical_ids,
            rule_version=registry.version,
            confidence=1.0,
            status="MANUALLY_APPROVED",
            selected_canonical_id=crosswalk.canonical_team_id,
            actor="phase1b-football-data-crosswalk",
            reason="explicit reviewed Football-Data team crosswalk",
            created_at=created_at,
        )
        return FootballDataUkTeamResolutionV1(
            status="RESOLVED",
            provider_team_label=provider_team_label,
            candidate_canonical_ids=candidate_canonical_ids,
            selected_canonical_team_id=crosswalk.canonical_team_id,
            decision=decision,
            reason="explicit reviewed crosswalk matches one context candidate",
        )
    if not candidate_canonical_ids:
        return FootballDataUkTeamResolutionV1(
            status="QUARANTINED",
            provider_team_label=provider_team_label,
            candidate_canonical_ids=(),
            selected_canonical_team_id=None,
            decision=None,
            reason="no context-qualified canonical team candidate",
        )
    decision = ResolutionDecisionV1(
        decision_id=decision_id,
        subject_type="team",
        provider_id="football_data_uk",
        provider_entity_id=provider_team_label,
        evidence_refs=(source_evidence_ref,),
        candidate_canonical_ids=candidate_canonical_ids,
        rule_version=registry.version,
        confidence=0.0,
        status="REVIEW_REQUIRED",
        selected_canonical_id=None,
        actor="phase1b-football-data-crosswalk",
        reason="no reviewed exact crosswalk establishes a safe canonical team",
        created_at=created_at,
    )
    return FootballDataUkTeamResolutionV1(
        status="REVIEW_REQUIRED",
        provider_team_label=provider_team_label,
        candidate_canonical_ids=candidate_canonical_ids,
        selected_canonical_team_id=None,
        decision=decision,
        reason="candidate teams require explicit reviewed crosswalk",
    )


def _validate_resolution_input(
    provider_team_label: str,
    candidate_canonical_ids: tuple[str, ...],
    source_evidence_ref: str,
    decision_id: str,
) -> None:
    if not provider_team_label or not source_evidence_ref or not decision_id:
        raise FootballDataUkTeamResolutionError(
            "team resolution identity and evidence are required"
        )
    if any(not candidate for candidate in candidate_canonical_ids):
        raise FootballDataUkTeamResolutionError("canonical team candidates must not be empty")
    if len(candidate_canonical_ids) != len(set(candidate_canonical_ids)):
        raise FootballDataUkTeamResolutionError("canonical team candidates must be unique")
