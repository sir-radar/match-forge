from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from football.contracts.source import canonical_json_bytes

CompetitionFormatV1 = Literal["LEAGUE", "GROUP", "KNOCKOUT", "PLAYOFF"]
TieStructureV1 = Literal["SINGLE_MATCH", "TWO_LEG", "ROUND_ROBIN"]
OutcomeScopeV1 = Literal["REGULATION_TIME", "INCLUDING_EXTRA_TIME", "INCLUDING_SHOOTOUT"]
ExtraTimePolicyV1 = Literal["NEVER", "POSSIBLE", "REQUIRED"]
ShootoutPolicyV1 = Literal["NEVER", "POSSIBLE", "REQUIRED"]
NeutralVenuePolicyV1 = Literal["NOT_APPLICABLE", "ALLOWED", "REQUIRED"]


class CompetitionRulesError(ValueError):
    """Competition rules violate their versioned outcome contract."""


@dataclass(frozen=True, slots=True)
class CompetitionRulesV1:
    """Versioned competition semantics used by canonical outcomes and forecasts."""

    rules_id: str
    competition_ref: str
    competition_format: CompetitionFormatV1
    tie_structure: TieStructureV1
    outcome_scope: OutcomeScopeV1
    extra_time_policy: ExtraTimePolicyV1
    shootout_policy: ShootoutPolicyV1
    neutral_venue_policy: NeutralVenuePolicyV1
    policy_version: str
    source_refs: tuple[str, ...]
    contract: str = "CompetitionRulesV1"

    def __post_init__(self) -> None:
        if self.contract != "CompetitionRulesV1":
            raise CompetitionRulesError("unsupported competition rules contract")
        if not self.rules_id or not self.competition_ref or not self.policy_version:
            raise CompetitionRulesError("competition rules identity and policy are required")
        if not self.source_refs or any(not value for value in self.source_refs):
            raise CompetitionRulesError("competition rules require source references")
        if len(self.source_refs) != len(set(self.source_refs)):
            raise CompetitionRulesError("competition rule source references must be unique")
        _validate_rule_values(self)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "rules_id": self.rules_id,
            "competition_ref": self.competition_ref,
            "competition_format": self.competition_format,
            "tie_structure": self.tie_structure,
            "outcome_scope": self.outcome_scope,
            "extra_time_policy": self.extra_time_policy,
            "shootout_policy": self.shootout_policy,
            "neutral_venue_policy": self.neutral_venue_policy,
            "policy_version": self.policy_version,
            "source_refs": list(self.source_refs),
        }


def _validate_rule_values(rules: CompetitionRulesV1) -> None:
    if rules.competition_format not in {"LEAGUE", "GROUP", "KNOCKOUT", "PLAYOFF"}:
        raise CompetitionRulesError("competition format is unsupported")
    if rules.tie_structure not in {"SINGLE_MATCH", "TWO_LEG", "ROUND_ROBIN"}:
        raise CompetitionRulesError("tie structure is unsupported")
    if rules.outcome_scope not in {
        "REGULATION_TIME",
        "INCLUDING_EXTRA_TIME",
        "INCLUDING_SHOOTOUT",
    }:
        raise CompetitionRulesError("outcome scope is unsupported")
    if rules.extra_time_policy not in {"NEVER", "POSSIBLE", "REQUIRED"}:
        raise CompetitionRulesError("extra-time policy is unsupported")
    if rules.shootout_policy not in {"NEVER", "POSSIBLE", "REQUIRED"}:
        raise CompetitionRulesError("shootout policy is unsupported")
    if rules.neutral_venue_policy not in {"NOT_APPLICABLE", "ALLOWED", "REQUIRED"}:
        raise CompetitionRulesError("neutral-venue policy is unsupported")
