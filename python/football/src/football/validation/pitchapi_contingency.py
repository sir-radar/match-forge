from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import SHA256_PATTERN, canonical_json_bytes

GateStatus = Literal["PASS", "FAIL", "UNPROVED"]
CorpusRole = Literal["development", "evaluation"]


class PitchApiContingencyError(ValueError):
    """Synthetic contingency evidence violates its fail-closed contract."""


@dataclass(frozen=True, slots=True)
class PitchApiSourceSeriesEvidenceV1:
    scope_key: str
    upstream_supplier: str | None
    model_name: str | None
    model_version: str | None
    model_build: str | None
    field_semantics: str | None
    penalty_treatment: str | None
    export_cohort_id: str | None
    rebuild_backfill_policy_ref: str | None
    correction_policy_ref: str | None
    identifier_policy_ref: str | None
    knowledge_mode_compatibility_ref: str | None
    attestation_ref: str | None
    attestation_sha256: str | None
    snapshot_revision: str | None
    snapshot_sha256: str | None
    acquired_at: datetime | None
    prior_versions_retainable: bool | None
    contract: str = "PitchApiSourceSeriesEvidenceV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiSourceSeriesEvidenceV1":
            raise PitchApiContingencyError("unsupported PitchAPI source-series contract")
        if not self.scope_key:
            raise PitchApiContingencyError("source-series scope key is required")
        for field_name in ("attestation_sha256", "snapshot_sha256"):
            value = getattr(self, field_name)
            if value is not None and not SHA256_PATTERN.fullmatch(value):
                raise PitchApiContingencyError(f"{field_name} must be a SHA-256")
        if self.acquired_at is not None and (
            self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None
        ):
            raise PitchApiContingencyError("acquired_at must include a timezone")

    @property
    def missing_fields(self) -> tuple[str, ...]:
        required_strings = (
            "upstream_supplier",
            "model_name",
            "model_version",
            "model_build",
            "field_semantics",
            "penalty_treatment",
            "export_cohort_id",
            "rebuild_backfill_policy_ref",
            "correction_policy_ref",
            "identifier_policy_ref",
            "knowledge_mode_compatibility_ref",
            "attestation_ref",
            "attestation_sha256",
            "snapshot_revision",
            "snapshot_sha256",
        )
        missing = [
            name
            for name in required_strings
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip()
        ]
        if self.acquired_at is None:
            missing.append("acquired_at")
        if self.prior_versions_retainable is not True:
            missing.append("prior_versions_retainable")
        return tuple(missing)

    @property
    def series_identity(self) -> tuple[str, ...] | None:
        if self.missing_fields:
            return None
        return (
            self.upstream_supplier or "",
            self.model_name or "",
            self.model_version or "",
            self.model_build or "",
            self.field_semantics or "",
            self.penalty_treatment or "",
            self.export_cohort_id or "",
            self.rebuild_backfill_policy_ref or "",
            self.correction_policy_ref or "",
            self.identifier_policy_ref or "",
            self.knowledge_mode_compatibility_ref or "",
        )


@dataclass(frozen=True, slots=True)
class PitchApiSeriesGateReportV1:
    status: GateStatus
    series_identity_sha256: str | None
    findings: tuple[str, ...]
    contract: str = "PitchApiSeriesGateReportV1"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "status": self.status,
            "series_identity_sha256": self.series_identity_sha256,
            "findings": list(self.findings),
        }


def qualify_pitchapi_source_series(
    evidence: tuple[PitchApiSourceSeriesEvidenceV1, ...],
    required_scope_keys: tuple[str, ...],
) -> PitchApiSeriesGateReportV1:
    required = set(required_scope_keys)
    observed = [item.scope_key for item in evidence]
    findings: set[str] = set()
    if not required or len(required) != len(required_scope_keys):
        raise PitchApiContingencyError("required scope keys must be present and unique")
    if len(observed) != len(set(observed)):
        findings.add("DUPLICATE_SCOPE_EVIDENCE")
    if set(observed) != required:
        findings.add("SCOPE_EVIDENCE_MISMATCH")
    for item in evidence:
        findings.update(
            f"MISSING_{field.upper()}:{item.scope_key}" for field in item.missing_fields
        )
    if findings:
        return PitchApiSeriesGateReportV1("UNPROVED", None, tuple(sorted(findings)))
    identities = {item.series_identity for item in evidence}
    if len(identities) != 1:
        return PitchApiSeriesGateReportV1("FAIL", None, ("MIXED_XG_SERIES",))
    identity = next(iter(identities))
    if identity is None:
        raise AssertionError("complete source-series evidence has no identity")
    identity_sha256 = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
    return PitchApiSeriesGateReportV1("PASS", identity_sha256, ())


@dataclass(frozen=True, slots=True)
class EvaluationV2CorpusGroupV1:
    scope_key: str
    role: CorpusRole
    competition_ref: str
    season_ref: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    source_series_sha256: str
    target_plan_sha256: str
    cutoff_evidence_sha256: str
    match_ids: tuple[UUID, ...]
    target_ids: tuple[UUID, ...]
    point_in_time_status: GateStatus
    contract: str = "EvaluationV2CorpusGroupV1"

    def __post_init__(self) -> None:
        if self.contract != "EvaluationV2CorpusGroupV1":
            raise PitchApiContingencyError("unsupported Evaluation V2 corpus group contract")
        if self.role not in ("development", "evaluation"):
            raise PitchApiContingencyError("unsupported corpus role")
        if not self.scope_key or not self.competition_ref or not self.season_ref:
            raise PitchApiContingencyError("group identity fields are required")
        for field_name in (
            "source_snapshot_sha256",
            "source_series_sha256",
            "target_plan_sha256",
            "cutoff_evidence_sha256",
        ):
            if not SHA256_PATTERN.fullmatch(getattr(self, field_name)):
                raise PitchApiContingencyError(f"{field_name} must be a SHA-256")
        if len(self.match_ids) != len(set(self.match_ids)):
            raise PitchApiContingencyError("group match IDs must be unique")
        if len(self.target_ids) != len(set(self.target_ids)):
            raise PitchApiContingencyError("group target IDs must be unique")
        if not set(self.target_ids) <= set(self.match_ids):
            raise PitchApiContingencyError("group targets must be members of its match corpus")
        if self.point_in_time_status not in ("PASS", "FAIL", "UNPROVED"):
            raise PitchApiContingencyError("unsupported point-in-time status")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "scope_key": self.scope_key,
            "role": self.role,
            "competition_ref": self.competition_ref,
            "season_ref": self.season_ref,
            "source_snapshot_id": str(self.source_snapshot_id),
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_series_sha256": self.source_series_sha256,
            "target_plan_sha256": self.target_plan_sha256,
            "cutoff_evidence_sha256": self.cutoff_evidence_sha256,
            "match_ids": sorted(str(value) for value in self.match_ids),
            "target_ids": sorted(str(value) for value in self.target_ids),
            "point_in_time_status": self.point_in_time_status,
        }


@dataclass(frozen=True, slots=True)
class EvaluationV2CorpusGateReportV1:
    status: GateStatus
    corpus_sha256: str
    firewall_sha256: str
    evaluation_group_count: int
    evaluation_competition_count: int
    evaluation_season_count: int
    evaluation_target_count: int
    findings: tuple[str, ...]
    contract: str = "EvaluationV2CorpusGateReportV1"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "status": self.status,
            "corpus_sha256": self.corpus_sha256,
            "firewall_sha256": self.firewall_sha256,
            "evaluation_group_count": self.evaluation_group_count,
            "evaluation_competition_count": self.evaluation_competition_count,
            "evaluation_season_count": self.evaluation_season_count,
            "evaluation_target_count": self.evaluation_target_count,
            "findings": list(self.findings),
        }


def validate_evaluation_v2_corpus_firewall(
    groups: tuple[EvaluationV2CorpusGroupV1, ...],
    *,
    protected_match_ids: frozenset[UUID],
    protected_scope_refs: frozenset[tuple[str, str]],
) -> EvaluationV2CorpusGateReportV1:
    findings: set[str] = set()
    scope_keys = [group.scope_key for group in groups]
    if not groups or len(scope_keys) != len(set(scope_keys)):
        findings.add("CORPUS_SCOPE_KEYS_INVALID")
    development = tuple(group for group in groups if group.role == "development")
    evaluation = tuple(group for group in groups if group.role == "evaluation")
    competition_count = len({group.competition_ref for group in evaluation})
    season_count = len({group.season_ref for group in evaluation})
    target_count = sum(len(group.target_ids) for group in evaluation)
    findings.update(
        _corpus_minimum_findings(
            development,
            evaluation,
            competition_count,
            season_count,
            target_count,
        )
    )
    findings.update(
        _corpus_isolation_findings(
            groups,
            development,
            evaluation,
            protected_match_ids,
            protected_scope_refs,
        )
    )
    corpus_payload = [group.to_dict() for group in sorted(groups, key=lambda item: item.scope_key)]
    corpus_sha256 = hashlib.sha256(canonical_json_bytes(corpus_payload)).hexdigest()
    firewall_payload = {
        "corpus_sha256": corpus_sha256,
        "protected_match_ids": sorted(str(value) for value in protected_match_ids),
        "protected_scope_refs": sorted(
            [list(value) for value in protected_scope_refs], key=lambda value: tuple(value)
        ),
    }
    firewall_sha256 = hashlib.sha256(canonical_json_bytes(firewall_payload)).hexdigest()
    unproved_findings = {
        finding for finding in findings if finding.startswith("POINT_IN_TIME_UNPROVED")
    }
    if findings - unproved_findings:
        status: GateStatus = "FAIL"
    else:
        status = "UNPROVED" if unproved_findings else "PASS"
    return EvaluationV2CorpusGateReportV1(
        status=status,
        corpus_sha256=corpus_sha256,
        firewall_sha256=firewall_sha256,
        evaluation_group_count=len(evaluation),
        evaluation_competition_count=competition_count,
        evaluation_season_count=season_count,
        evaluation_target_count=target_count,
        findings=tuple(sorted(findings)),
    )


def _corpus_minimum_findings(
    development: tuple[EvaluationV2CorpusGroupV1, ...],
    evaluation: tuple[EvaluationV2CorpusGroupV1, ...],
    competition_count: int,
    season_count: int,
    target_count: int,
) -> set[str]:
    findings: set[str] = set()
    checks = (
        (len(development) != 1, "DEVELOPMENT_GROUP_COUNT_INVALID"),
        (len(evaluation) < 3, "EVALUATION_GROUP_COUNT_BELOW_MINIMUM"),
        (
            any(len(group.match_ids) < 120 for group in evaluation),
            "EVALUATION_GROUP_MATCH_COUNT_BELOW_MINIMUM",
        ),
        (competition_count < 2, "EVALUATION_COMPETITION_COUNT_BELOW_MINIMUM"),
        (season_count < 2, "EVALUATION_SEASON_COUNT_BELOW_MINIMUM"),
        (target_count < 500, "EVALUATION_TARGET_COUNT_BELOW_MINIMUM"),
    )
    findings.update(code for failed, code in checks if failed)
    return findings


def _corpus_isolation_findings(
    groups: tuple[EvaluationV2CorpusGroupV1, ...],
    development: tuple[EvaluationV2CorpusGroupV1, ...],
    evaluation: tuple[EvaluationV2CorpusGroupV1, ...],
    protected_match_ids: frozenset[UUID],
    protected_scope_refs: frozenset[tuple[str, str]],
) -> set[str]:
    findings: set[str] = set()
    if {group.competition_ref for group in development} & {
        group.competition_ref for group in evaluation
    }:
        findings.add("DEVELOPMENT_EVALUATION_COMPETITION_INTERSECTION")
    if {(group.competition_ref, group.season_ref) for group in groups} & protected_scope_refs:
        findings.add("PROTECTED_SCOPE_INCLUDED")
    all_seen: set[UUID] = set()
    for group in groups:
        group_ids = set(group.match_ids)
        if all_seen & group_ids:
            findings.add("CROSS_GROUP_MATCH_ID_INTERSECTION")
        all_seen.update(group_ids)
        if group_ids & protected_match_ids:
            findings.add("PROTECTED_MATCH_ID_INTERSECTION")
        if group.point_in_time_status != "PASS":
            findings.add(f"POINT_IN_TIME_{group.point_in_time_status}:{group.scope_key}")
    if len({group.source_series_sha256 for group in groups}) != 1:
        findings.add("SOURCE_SERIES_INTERSECTION_FAILED")
    return findings
