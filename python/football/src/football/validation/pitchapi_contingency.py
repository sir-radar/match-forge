from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from football.contracts.source import SHA256_PATTERN, canonical_json_bytes

GateStatus = Literal["PASS", "FAIL", "UNPROVED"]
CorpusRole = Literal["development", "evaluation"]
PitchApiEntityType = Literal["team", "match"]
PitchApiMappingAction = Literal["initial", "stable", "migration", "remap"]
PitchApiCorrectionClassification = Literal[
    "INITIAL", "NO_CHANGE", "PROVIDER_CORRECTION", "IDENTIFIER_MIGRATION", "MIXED"
]
PITCHAPI_RETROSPECTIVE_EVALUATION_V1 = "PITCHAPI_RETROSPECTIVE_EVALUATION_V1"
PITCHAPI_SNAPSHOT_V1 = "PITCHAPI_SNAPSHOT_V1"
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SNAPSHOT_PROTOCOL_PATTERN = re.compile(r"^PITCHAPI_SNAPSHOT_V([1-9][0-9]*)$")


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


@dataclass(frozen=True, slots=True)
class PitchApiObservationalSeriesEvidenceV1:
    scope_key: str
    acquisition_cohort_id: UUID
    snapshot_sha256: str
    field_semantics_sha256: str
    compatibility_policy_sha256: str
    compatibility_report_sha256: str
    compatibility_status: GateStatus
    provider: str = "PITCHAPI"
    xg_field: str = "shot.xg"
    contract: str = "PitchApiObservationalSeriesEvidenceV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiObservationalSeriesEvidenceV1":
            raise PitchApiContingencyError("unsupported observational source-series contract")
        if not self.scope_key or self.provider != "PITCHAPI" or not self.xg_field:
            raise PitchApiContingencyError("observational source-series identity is invalid")
        for field_name in (
            "snapshot_sha256",
            "field_semantics_sha256",
            "compatibility_policy_sha256",
            "compatibility_report_sha256",
        ):
            if not SHA256_PATTERN.fullmatch(getattr(self, field_name)):
                raise PitchApiContingencyError(f"{field_name} must be a SHA-256")


def qualify_pitchapi_observational_series(
    evidence: tuple[PitchApiObservationalSeriesEvidenceV1, ...],
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
        if item.compatibility_status != "PASS":
            findings.add(f"COMPATIBILITY_{item.compatibility_status}:{item.scope_key}")
    if findings:
        unproved = {finding for finding in findings if "UNPROVED" in finding}
        status: GateStatus = "FAIL" if findings - unproved else "UNPROVED"
        return PitchApiSeriesGateReportV1(status, None, tuple(sorted(findings)))
    identities = {
        (
            str(item.acquisition_cohort_id),
            item.provider,
            item.xg_field,
            item.field_semantics_sha256,
            item.compatibility_policy_sha256,
        )
        for item in evidence
    }
    if len(identities) != 1:
        return PitchApiSeriesGateReportV1("FAIL", None, ("MIXED_OBSERVATIONAL_SOURCE_SERIES",))
    identity_sha256 = hashlib.sha256(canonical_json_bytes(next(iter(identities)))).hexdigest()
    return PitchApiSeriesGateReportV1("PASS", identity_sha256, ())


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
class PitchApiRetrospectivePolicyV1:
    development_group_count: int
    minimum_evaluation_groups: int
    minimum_evaluation_competitions: int
    minimum_evaluation_seasons: int
    minimum_nominal_matches_per_evaluation_group: int
    minimum_evaluation_targets: int
    require_development_competition_independence: bool
    evaluation_protocol_id: str = PITCHAPI_RETROSPECTIVE_EVALUATION_V1
    contract: str = "PitchApiRetrospectivePolicyV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiRetrospectivePolicyV1":
            raise PitchApiContingencyError("unsupported PitchAPI retrospective policy contract")
        if self.evaluation_protocol_id != PITCHAPI_RETROSPECTIVE_EVALUATION_V1:
            raise PitchApiContingencyError("unsupported PitchAPI retrospective protocol")
        for field_name in (
            "development_group_count",
            "minimum_evaluation_groups",
            "minimum_evaluation_competitions",
            "minimum_evaluation_seasons",
            "minimum_nominal_matches_per_evaluation_group",
            "minimum_evaluation_targets",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PitchApiContingencyError(f"{field_name} must be a positive integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_protocol_id": self.evaluation_protocol_id,
            "development_group_count": self.development_group_count,
            "minimum_evaluation_groups": self.minimum_evaluation_groups,
            "minimum_evaluation_competitions": self.minimum_evaluation_competitions,
            "minimum_evaluation_seasons": self.minimum_evaluation_seasons,
            "minimum_nominal_matches_per_evaluation_group": (
                self.minimum_nominal_matches_per_evaluation_group
            ),
            "minimum_evaluation_targets": self.minimum_evaluation_targets,
            "require_development_competition_independence": (
                self.require_development_competition_independence
            ),
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class PitchApiSnapshotResourceIdentityV1:
    resource_ref: str
    raw_sha256: str
    normalized_sha256: str
    contract: str = "PitchApiSnapshotResourceIdentityV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiSnapshotResourceIdentityV1" or not self.resource_ref:
            raise PitchApiContingencyError("unsupported or unnamed snapshot resource identity")
        if not SHA256_PATTERN.fullmatch(self.raw_sha256) or not SHA256_PATTERN.fullmatch(
            self.normalized_sha256
        ):
            raise PitchApiContingencyError("snapshot resource identity contains an invalid SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {
            "contract": self.contract,
            "resource_ref": self.resource_ref,
            "raw_sha256": self.raw_sha256,
            "normalized_sha256": self.normalized_sha256,
        }


@dataclass(frozen=True, slots=True)
class PitchApiSnapshotIdentityV1:
    snapshot_id: UUID
    acquired_at: datetime
    resources: tuple[PitchApiSnapshotResourceIdentityV1, ...]
    canonical_mapping_sha256: str
    adapter_version: str
    configuration_sha256: str
    code_git_sha: str
    predecessor_snapshot_sha256: str | None = None
    snapshot_protocol_id: str = PITCHAPI_SNAPSHOT_V1
    contract: str = "PitchApiSnapshotIdentityV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiSnapshotIdentityV1":
            raise PitchApiContingencyError("unsupported PitchAPI snapshot contract")
        if _SNAPSHOT_PROTOCOL_PATTERN.fullmatch(self.snapshot_protocol_id) is None:
            raise PitchApiContingencyError("unsupported PitchAPI snapshot protocol")
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise PitchApiContingencyError("snapshot acquired_at must include a timezone")
        resource_refs = [resource.resource_ref for resource in self.resources]
        if not resource_refs or len(resource_refs) != len(set(resource_refs)):
            raise PitchApiContingencyError(
                "snapshot resource references must be present and unique"
            )
        hash_values: tuple[str, ...] = (
            self.canonical_mapping_sha256,
            self.configuration_sha256,
        )
        if self.predecessor_snapshot_sha256 is not None:
            hash_values = (*hash_values, self.predecessor_snapshot_sha256)
        if any(not SHA256_PATTERN.fullmatch(value) for value in hash_values):
            raise PitchApiContingencyError("snapshot identity contains an invalid SHA-256")
        if not self.adapter_version or not _GIT_SHA_PATTERN.fullmatch(self.code_git_sha):
            raise PitchApiContingencyError("snapshot adapter version and code Git SHA are required")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "snapshot_protocol_id": self.snapshot_protocol_id,
            "snapshot_id": str(self.snapshot_id),
            "acquired_at": self.acquired_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "resources": [
                resource.to_dict()
                for resource in sorted(self.resources, key=lambda item: item.resource_ref)
            ],
            "canonical_mapping_sha256": self.canonical_mapping_sha256,
            "adapter_version": self.adapter_version,
            "configuration_sha256": self.configuration_sha256,
            "code_git_sha": self.code_git_sha,
            "predecessor_snapshot_sha256": self.predecessor_snapshot_sha256,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class PitchApiSnapshotRevisionV1:
    snapshot: PitchApiSnapshotIdentityV1
    normalized_difference_sha256: str
    detected_provider_id_changes: tuple[str, ...]
    correction_classification: PitchApiCorrectionClassification
    contract: str = "PitchApiSnapshotRevisionV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiSnapshotRevisionV1":
            raise PitchApiContingencyError("unsupported PitchAPI snapshot revision contract")
        if not SHA256_PATTERN.fullmatch(self.normalized_difference_sha256):
            raise PitchApiContingencyError("normalized difference must be a SHA-256")
        if len(self.detected_provider_id_changes) != len(set(self.detected_provider_id_changes)):
            raise PitchApiContingencyError("provider ID changes must be unique")
        if self.correction_classification not in (
            "INITIAL",
            "NO_CHANGE",
            "PROVIDER_CORRECTION",
            "IDENTIFIER_MIGRATION",
            "MIXED",
        ):
            raise PitchApiContingencyError("unsupported correction classification")


def validate_pitchapi_snapshot_revision_chain(
    revisions: tuple[PitchApiSnapshotRevisionV1, ...],
) -> None:
    if not revisions:
        raise PitchApiContingencyError("snapshot revision chain must not be empty")
    snapshot_ids = [revision.snapshot.snapshot_id for revision in revisions]
    snapshot_hashes = [revision.snapshot.sha256 for revision in revisions]
    if len(snapshot_ids) != len(set(snapshot_ids)) or len(snapshot_hashes) != len(
        set(snapshot_hashes)
    ):
        raise PitchApiContingencyError("snapshot revisions must be immutable and unique")
    for index, revision in enumerate(revisions):
        match = _SNAPSHOT_PROTOCOL_PATTERN.fullmatch(revision.snapshot.snapshot_protocol_id)
        if match is None or int(match.group(1)) != index + 1:
            raise PitchApiContingencyError("snapshot protocol versions must be consecutive")
        expected_predecessor = None if index == 0 else snapshot_hashes[index - 1]
        if revision.snapshot.predecessor_snapshot_sha256 != expected_predecessor:
            raise PitchApiContingencyError("snapshot predecessor hash chain is invalid")
        if index == 0 and revision.correction_classification != "INITIAL":
            raise PitchApiContingencyError("first snapshot revision must be INITIAL")
        if index > 0 and revision.correction_classification == "INITIAL":
            raise PitchApiContingencyError("later snapshot revision cannot be INITIAL")
        if index > 0 and revision.snapshot.acquired_at <= revisions[index - 1].snapshot.acquired_at:
            raise PitchApiContingencyError("snapshot acquisition times must increase")


@dataclass(frozen=True, slots=True)
class PitchApiAliasMappingV1:
    snapshot_id: UUID
    entity_type: PitchApiEntityType
    provider_entity_id: str
    canonical_id: UUID
    mapping_action: PitchApiMappingAction
    mapping_evidence_sha256: str
    predecessor_mapping_sha256: str | None = None
    replaces_provider_entity_id: str | None = None
    contract: str = "PitchApiAliasMappingV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiAliasMappingV1":
            raise PitchApiContingencyError("unsupported PitchAPI alias mapping contract")
        if self.entity_type not in ("team", "match") or not self.provider_entity_id.strip():
            raise PitchApiContingencyError("alias type and provider entity ID are required")
        if self.mapping_action not in ("initial", "stable", "migration", "remap"):
            raise PitchApiContingencyError("unsupported alias mapping action")
        for value in (self.mapping_evidence_sha256, self.predecessor_mapping_sha256):
            if value is not None and not SHA256_PATTERN.fullmatch(value):
                raise PitchApiContingencyError("alias mapping contains an invalid SHA-256")
        if (
            self.mapping_action in ("migration", "remap")
            and self.predecessor_mapping_sha256 is None
        ):
            raise PitchApiContingencyError("migration and remap require predecessor evidence")
        if self.mapping_action == "migration" and not self.replaces_provider_entity_id:
            raise PitchApiContingencyError("migration requires the replaced provider ID")

    @property
    def sha256(self) -> str:
        payload = {
            "contract": self.contract,
            "snapshot_id": str(self.snapshot_id),
            "entity_type": self.entity_type,
            "provider_entity_id": self.provider_entity_id,
            "canonical_id": str(self.canonical_id),
            "mapping_action": self.mapping_action,
            "mapping_evidence_sha256": self.mapping_evidence_sha256,
            "predecessor_mapping_sha256": self.predecessor_mapping_sha256,
            "replaces_provider_entity_id": self.replaces_provider_entity_id,
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def validate_pitchapi_alias_history(
    mappings: tuple[PitchApiAliasMappingV1, ...],
    *,
    snapshot_order: tuple[UUID, ...],
) -> None:
    if not mappings or not snapshot_order or len(snapshot_order) != len(set(snapshot_order)):
        raise PitchApiContingencyError("alias history and unique snapshot order are required")
    positions = {snapshot_id: index for index, snapshot_id in enumerate(snapshot_order)}
    seen_in_snapshot: set[tuple[UUID, PitchApiEntityType, str]] = set()
    latest_by_alias: dict[tuple[PitchApiEntityType, str], PitchApiAliasMappingV1] = {}
    latest_by_canonical: dict[tuple[PitchApiEntityType, UUID], PitchApiAliasMappingV1] = {}
    ordered = sorted(mappings, key=lambda item: positions.get(item.snapshot_id, -1))
    for mapping in ordered:
        if mapping.snapshot_id not in positions:
            raise PitchApiContingencyError("alias mapping references an unknown snapshot")
        snapshot_key = (mapping.snapshot_id, mapping.entity_type, mapping.provider_entity_id)
        if snapshot_key in seen_in_snapshot:
            raise PitchApiContingencyError("duplicate provider alias in snapshot")
        seen_in_snapshot.add(snapshot_key)
        alias_key = (mapping.entity_type, mapping.provider_entity_id)
        prior_alias = latest_by_alias.get(alias_key)
        prior_canonical = latest_by_canonical.get((mapping.entity_type, mapping.canonical_id))
        if (
            prior_alias is not None
            and prior_alias.canonical_id != mapping.canonical_id
            and (
                mapping.mapping_action != "remap"
                or mapping.predecessor_mapping_sha256 != prior_alias.sha256
            )
        ):
            raise PitchApiContingencyError("provider alias collision requires remapping evidence")
        if mapping.mapping_action == "migration" and (
            prior_canonical is None
            or mapping.replaces_provider_entity_id != prior_canonical.provider_entity_id
            or mapping.predecessor_mapping_sha256 != prior_canonical.sha256
        ):
            raise PitchApiContingencyError("provider ID migration evidence is invalid")
        latest_by_alias[alias_key] = mapping
        latest_by_canonical[(mapping.entity_type, mapping.canonical_id)] = mapping


@dataclass(frozen=True, slots=True)
class PitchApiRetrospectiveCorpusGroupV1:
    scope_key: str
    role: CorpusRole
    competition_ref: str
    season_ref: str
    source_snapshot_id: UUID
    source_snapshot_sha256: str
    source_series_sha256: str
    target_plan_sha256: str
    cutoff_evidence_sha256: str
    firewall_access_audit_sha256: str
    nominal_match_count: int
    match_ids: tuple[UUID, ...]
    target_ids: tuple[UUID, ...]
    exclusion_counts: tuple[tuple[str, int], ...]
    point_in_time_status: GateStatus
    evaluation_protocol_id: str = PITCHAPI_RETROSPECTIVE_EVALUATION_V1
    contract: str = "PitchApiRetrospectiveCorpusGroupV1"

    def __post_init__(self) -> None:
        if self.contract != "PitchApiRetrospectiveCorpusGroupV1":
            raise PitchApiContingencyError("unsupported PitchAPI retrospective group contract")
        if self.evaluation_protocol_id != PITCHAPI_RETROSPECTIVE_EVALUATION_V1:
            raise PitchApiContingencyError("PitchAPI group has the wrong evaluation protocol")
        if self.role not in ("development", "evaluation"):
            raise PitchApiContingencyError("unsupported corpus role")
        if not self.scope_key or not self.competition_ref or not self.season_ref:
            raise PitchApiContingencyError("group identity fields are required")
        _validate_group_hashes(self)
        _validate_group_membership(self)
        _validate_group_exclusions(self)
        if self.point_in_time_status not in ("PASS", "FAIL", "UNPROVED"):
            raise PitchApiContingencyError("unsupported point-in-time status")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_protocol_id": self.evaluation_protocol_id,
            "scope_key": self.scope_key,
            "role": self.role,
            "competition_ref": self.competition_ref,
            "season_ref": self.season_ref,
            "source_snapshot_id": str(self.source_snapshot_id),
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_series_sha256": self.source_series_sha256,
            "target_plan_sha256": self.target_plan_sha256,
            "cutoff_evidence_sha256": self.cutoff_evidence_sha256,
            "firewall_access_audit_sha256": self.firewall_access_audit_sha256,
            "nominal_match_count": self.nominal_match_count,
            "match_ids": sorted(str(value) for value in self.match_ids),
            "target_ids": sorted(str(value) for value in self.target_ids),
            "exclusion_counts": [
                {"reason": reason, "count": count}
                for reason, count in sorted(self.exclusion_counts)
            ],
            "point_in_time_status": self.point_in_time_status,
        }


def _validate_group_hashes(group: PitchApiRetrospectiveCorpusGroupV1) -> None:
    for field_name in (
        "source_snapshot_sha256",
        "source_series_sha256",
        "target_plan_sha256",
        "cutoff_evidence_sha256",
        "firewall_access_audit_sha256",
    ):
        if not SHA256_PATTERN.fullmatch(getattr(group, field_name)):
            raise PitchApiContingencyError(f"{field_name} must be a SHA-256")


def _validate_group_membership(group: PitchApiRetrospectiveCorpusGroupV1) -> None:
    if len(group.match_ids) != len(set(group.match_ids)):
        raise PitchApiContingencyError("group match IDs must be unique")
    if len(group.target_ids) != len(set(group.target_ids)):
        raise PitchApiContingencyError("group target IDs must be unique")
    if not set(group.target_ids) <= set(group.match_ids):
        raise PitchApiContingencyError("group targets must be members of its match corpus")


def _validate_group_exclusions(group: PitchApiRetrospectiveCorpusGroupV1) -> None:
    exclusion_names = [name for name, _count in group.exclusion_counts]
    if len(exclusion_names) != len(set(exclusion_names)):
        raise PitchApiContingencyError("group exclusion reasons must be unique")
    if any(not name or count < 0 for name, count in group.exclusion_counts):
        raise PitchApiContingencyError("group exclusion counts must be named and non-negative")
    if group.nominal_match_count <= 0:
        raise PitchApiContingencyError("group nominal match count must be positive")
    excluded_count = sum(count for _name, count in group.exclusion_counts)
    if len(group.target_ids) + excluded_count != group.nominal_match_count:
        raise PitchApiContingencyError("group target and exclusion counts do not reconcile")


@dataclass(frozen=True, slots=True)
class PitchApiRetrospectiveCorpusGateReportV1:
    status: GateStatus
    evaluation_protocol_id: str
    policy_sha256: str
    corpus_sha256: str
    firewall_sha256: str
    evaluation_group_count: int
    evaluation_competition_count: int
    evaluation_season_count: int
    evaluation_target_count: int
    findings: tuple[str, ...]
    contract: str = "PitchApiRetrospectiveCorpusGateReportV1"

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "evaluation_protocol_id": self.evaluation_protocol_id,
            "policy_sha256": self.policy_sha256,
            "status": self.status,
            "corpus_sha256": self.corpus_sha256,
            "firewall_sha256": self.firewall_sha256,
            "evaluation_group_count": self.evaluation_group_count,
            "evaluation_competition_count": self.evaluation_competition_count,
            "evaluation_season_count": self.evaluation_season_count,
            "evaluation_target_count": self.evaluation_target_count,
            "findings": list(self.findings),
        }


def validate_pitchapi_retrospective_corpus_firewall(
    groups: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    *,
    policy: PitchApiRetrospectivePolicyV1,
    snapshot_identities: tuple[PitchApiSnapshotIdentityV1, ...],
    protected_match_ids: frozenset[UUID],
    protected_scope_refs: frozenset[tuple[str, str]],
) -> PitchApiRetrospectiveCorpusGateReportV1:
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
            policy,
            competition_count,
            season_count,
            target_count,
        )
    )
    findings.update(_snapshot_identity_findings(groups, snapshot_identities))
    findings.update(
        _corpus_isolation_findings(
            groups,
            development,
            evaluation,
            policy,
            protected_match_ids,
            protected_scope_refs,
        )
    )
    corpus_payload = {
        "evaluation_protocol_id": policy.evaluation_protocol_id,
        "policy_sha256": policy.sha256,
        "groups": [group.to_dict() for group in sorted(groups, key=lambda item: item.scope_key)],
    }
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
    return PitchApiRetrospectiveCorpusGateReportV1(
        status=status,
        evaluation_protocol_id=policy.evaluation_protocol_id,
        policy_sha256=policy.sha256,
        corpus_sha256=corpus_sha256,
        firewall_sha256=firewall_sha256,
        evaluation_group_count=len(evaluation),
        evaluation_competition_count=competition_count,
        evaluation_season_count=season_count,
        evaluation_target_count=target_count,
        findings=tuple(sorted(findings)),
    )


def _snapshot_identity_findings(
    groups: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    snapshots: tuple[PitchApiSnapshotIdentityV1, ...],
) -> set[str]:
    by_id = {snapshot.snapshot_id: snapshot for snapshot in snapshots}
    if len(by_id) != len(snapshots):
        return {"SNAPSHOT_IDENTITIES_DUPLICATED"}
    findings: set[str] = set()
    for group in groups:
        snapshot = by_id.get(group.source_snapshot_id)
        if snapshot is None:
            findings.add(f"SNAPSHOT_IDENTITY_MISSING:{group.scope_key}")
        elif snapshot.sha256 != group.source_snapshot_sha256:
            findings.add(f"SNAPSHOT_IDENTITY_MISMATCH:{group.scope_key}")
    return findings


def _corpus_minimum_findings(
    development: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    evaluation: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    policy: PitchApiRetrospectivePolicyV1,
    competition_count: int,
    season_count: int,
    target_count: int,
) -> set[str]:
    findings: set[str] = set()
    checks = (
        (
            len(development) != policy.development_group_count,
            "DEVELOPMENT_GROUP_COUNT_INVALID",
        ),
        (
            len(evaluation) < policy.minimum_evaluation_groups,
            "EVALUATION_GROUP_COUNT_BELOW_MINIMUM",
        ),
        (
            any(
                group.nominal_match_count < policy.minimum_nominal_matches_per_evaluation_group
                for group in evaluation
            ),
            "EVALUATION_GROUP_MATCH_COUNT_BELOW_MINIMUM",
        ),
        (
            competition_count < policy.minimum_evaluation_competitions,
            "EVALUATION_COMPETITION_COUNT_BELOW_MINIMUM",
        ),
        (
            season_count < policy.minimum_evaluation_seasons,
            "EVALUATION_SEASON_COUNT_BELOW_MINIMUM",
        ),
        (
            target_count < policy.minimum_evaluation_targets,
            "EVALUATION_TARGET_COUNT_BELOW_MINIMUM",
        ),
    )
    findings.update(code for failed, code in checks if failed)
    return findings


def _corpus_isolation_findings(
    groups: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    development: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    evaluation: tuple[PitchApiRetrospectiveCorpusGroupV1, ...],
    policy: PitchApiRetrospectivePolicyV1,
    protected_match_ids: frozenset[UUID],
    protected_scope_refs: frozenset[tuple[str, str]],
) -> set[str]:
    findings: set[str] = set()
    scope_refs = [(group.competition_ref, group.season_ref) for group in groups]
    if len(scope_refs) != len(set(scope_refs)):
        findings.add("CROSS_GROUP_SCOPE_INTERSECTION")
    if policy.require_development_competition_independence and {
        group.competition_ref for group in development
    } & {group.competition_ref for group in evaluation}:
        findings.add("DEVELOPMENT_EVALUATION_COMPETITION_INTERSECTION")
    if set(scope_refs) & protected_scope_refs:
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
