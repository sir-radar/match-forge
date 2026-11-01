from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID

from football.contracts.decisions import DecisionRecordV1
from football.contracts.observations import (
    EntityReference,
    FixtureObservationV1,
    LineupObservationV1,
    Observation,
    observation_from_bytes,
)
from football.contracts.observations_v2 import EntityReferenceV2
from football.contracts.observations_v3 import ObservationVersionsV3
from football.contracts.source import canonical_json_bytes
from football.ingestion.conflicts import ConflictRecordV1

_METADATA = frozenset(("provenance", "time", "versions"))
_SCOPE_FIELDS = {
    "FixtureObservation": ("fixture",),
    "ResultObservation": ("fixture", "score_basis"),
    "CompetitionObservation": ("competition", "season_label"),
    "TeamObservation": ("team",),
    "PlayerObservation": ("player",),
    "CoachObservation": ("team",),
    "LineupObservation": ("fixture", "team"),
    "AvailabilityObservation": ("team", "player", "fixture", "availability_type"),
    "FormationObservation": ("fixture", "team"),
    "EventObservation": ("fixture",),
    "ShotObservation": ("fixture",),
    "ExpectedGoalsObservation": ("fixture", "team", "scope", "shot"),
    "TeamStatisticObservation": ("fixture", "team", "period"),
    "PlayerStatisticObservation": ("fixture", "team", "player"),
    "StandingObservation": ("competition", "team", "season_label"),
    "OddsObservation": ("fixture", "bookmaker", "market"),
    "PeriodScoreObservation": ("fixture", "period", "score_basis"),
    "RefereeObservation": ("fixture",),
    "TeamRatingObservation": ("team", "rating_date", "rating_system"),
}
_IDENTITY_TYPES = frozenset(
    ("identity_resolution", "identity_admission", "fixture_identity_resolution")
)
_ADMITTED = frozenset(
    (
        "ORIGIN_ANCHOR",
        "CROSSWALK",
        "AUTO_ACCEPTED",
        "MANUALLY_APPROVED",
        "UNIQUE",
        "DUPLICATE_RESOLVED",
    )
)


class CanonicalResolutionError(ValueError):
    """A canonical conclusion lacks consistent scope, knowledge or identity evidence."""


@dataclass(frozen=True, slots=True)
class CanonicalBinding:
    reference_path: str
    canonical_id: UUID
    identity_decision: DecisionRecordV1

    def __post_init__(self) -> None:
        if not self.reference_path.startswith("/") or not isinstance(self.canonical_id, UUID):
            raise CanonicalResolutionError("canonical reference path and UUID are required")
        _validate_identity(self.identity_decision, self.canonical_id)


@dataclass(frozen=True, slots=True, kw_only=True)
class CanonicalCandidate[T: Observation]:
    """Identity-owner-qualified evidence for one explicitly identified resource unit.

    Entity and resource-unit identity decisions are supplied by existing owners.
    This value contract validates their bindings; it does not establish identity
    or grant provider authority. Source observations remain unchanged.
    """

    observation: T
    canonical_subject_id: UUID
    subject_identity: DecisionRecordV1
    bindings: tuple[CanonicalBinding, ...]

    def __post_init__(self) -> None:
        _validate_identity(self.subject_identity, self.canonical_subject_id)
        snapshot = observation_from_bytes(self.observation.to_bytes())
        object.__setattr__(self, "observation", cast(T, snapshot))
        object.__setattr__(self, "bindings", tuple(self.bindings))
        expected = set(_references(snapshot))
        paths = [binding.reference_path for binding in self.bindings]
        if len(paths) != len(set(paths)) or set(paths) != expected:
            raise CanonicalResolutionError(
                "every source entity reference requires one identity binding"
            )
        references = _references(snapshot)
        for binding in self.bindings:
            _validate_reference_scope(snapshot, binding, references[binding.reference_path])
        _validate_participants(snapshot, self.bindings)
        if self.resource_type in ("EventObservation", "ShotObservation"):
            if self.subject_identity.subject_type not in ("event", "shot"):
                raise CanonicalResolutionError("event and shot units require their own identity")
        elif not any(
            binding.reference_path == "/" + _SCOPE_FIELDS[self.resource_type][0]
            and binding.canonical_id == self.canonical_subject_id
            and binding.identity_decision == self.subject_identity
            for binding in self.bindings
        ):
            raise CanonicalResolutionError("resource subject must have an exact entity binding")

    @property
    def resource_type(self) -> str:
        return self.observation.CONTRACT.removesuffix("V1").removesuffix("V2").removesuffix("V3")

    @property
    def value_sha256(self) -> str:
        identities = {binding.reference_path: binding.canonical_id for binding in self.bindings}
        payload = {
            item.name: _canonical_value(
                getattr(self.observation, item.name), "/" + item.name, identities
            )
            for item in fields(self.observation)
            if item.name not in _METADATA
        }
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

    @property
    def context_sha256(self) -> str:
        identities = {binding.reference_path: binding.canonical_id for binding in self.bindings}
        payload = {
            name: _canonical_value(getattr(self.observation, name), "/" + name, identities)
            for name in _SCOPE_FIELDS[self.resource_type]
        }
        payload["validity"] = {
            "valid_from": _canonical_value(self.observation.time.valid_from, "", identities),
            "valid_to": _canonical_value(self.observation.time.valid_to, "", identities),
        }
        if isinstance(self.observation.versions, ObservationVersionsV3):
            payload["semantic_version"] = self.observation.versions.semantic_version
        return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalResolution[T: Observation]:
    decision: DecisionRecordV1
    selection: ConflictRecordV1
    resource_type: str
    canonical_subject_id: UUID
    knowledge_cutoff: datetime
    candidates: tuple[CanonicalCandidate[T], ...]
    selected: CanonicalCandidate[T] | None
    supporting: tuple[UUID, ...]
    conflicting: tuple[UUID, ...]


def resolve_canonical_resource[T: Observation](
    candidates: tuple[CanonicalCandidate[T], ...],
    selection: ConflictRecordV1,
    *,
    knowledge_cutoff: datetime,
    predecessor: UUID | None = None,
) -> CanonicalResolution[T]:
    """Materialize an explicit selection; disagreements never invent a winner."""
    ordered = tuple(sorted(candidates, key=lambda item: item.observation.observation_id.int))
    _validate_selection(ordered, selection, knowledge_cutoff)
    first = ordered[0]
    by_id = {str(item.observation.observation_id): item for item in ordered}
    selected_ref = selection.selected_observation_ref
    selected = by_id[selected_ref] if selection.disposition == "RESOLVED" and selected_ref else None
    supporting = tuple(
        item.observation.observation_id
        for item in ordered
        if selected is not None and item.value_sha256 == selected.value_sha256
    )
    conflicting = tuple(
        item.observation.observation_id
        for item in ordered
        if selected is not None and item.value_sha256 != selected.value_sha256
    )
    evidence = {
        "knowledge_cutoff": knowledge_cutoff.astimezone(UTC).isoformat(),
        "context_sha256": first.context_sha256,
        "selection": selection.to_dict(),
        "selection_sha256": selection.sha256,
        "selected_observation_id": str(selected.observation.observation_id) if selected else None,
        "supporting": [str(value) for value in supporting],
        "conflicting": [str(value) for value in conflicting],
        "candidates": [_candidate_evidence(item) for item in ordered],
    }
    decision = DecisionRecordV1(
        decision_type="canonical_resource_resolution",
        subject_type=first.resource_type,
        subject_id=str(first.canonical_subject_id),
        decided_at=selection.created_at,
        disposition=selection.disposition,
        reason=selection.reason,
        evidence=evidence,
        predecessor=str(predecessor) if predecessor else None,
    )
    return CanonicalResolution(
        decision,
        selection,
        first.resource_type,
        first.canonical_subject_id,
        knowledge_cutoff.astimezone(UTC),
        ordered,
        selected,
        supporting,
        conflicting,
    )


def _validate_identity(decision: DecisionRecordV1, canonical_id: UUID) -> None:
    if not isinstance(canonical_id, UUID) or decision.subject_id != str(canonical_id):
        raise CanonicalResolutionError("identity decision must bind the canonical subject UUID")
    if decision.decision_type not in _IDENTITY_TYPES or decision.disposition not in _ADMITTED:
        raise CanonicalResolutionError("an admitted identity decision is required")
    evidence = decision.to_dict()["evidence"]
    assert isinstance(evidence, dict)
    source = evidence.get("source_contract")
    if not isinstance(source, dict) or not source:
        raise CanonicalResolutionError("identity source evidence is required")
    if evidence.get("source_sha256") != hashlib.sha256(canonical_json_bytes(source)).hexdigest():
        raise CanonicalResolutionError("identity source evidence checksum mismatch")
    if source.get("contract") == "ResolutionDecisionV1" and (
        source.get("status") != decision.disposition
        or source.get("selected_canonical_id") != str(canonical_id)
    ):
        raise CanonicalResolutionError("identity decision differs from its source decision")


def _validate_reference_scope(
    observation: Observation, binding: CanonicalBinding, reference: object
) -> None:
    assert isinstance(reference, (EntityReference, EntityReferenceV2))
    kinds = {
        "fixture": ("match", "fixture"),
        "competition": ("competition",),
        "team": ("team",),
        "home_team": ("team",),
        "away_team": ("team",),
        "player": ("player",),
        "coach": ("coach", "manager"),
        "venue": ("venue",),
        "shot": ("shot", "event"),
        "assisting_player": ("player",),
        "assist_event": ("event",),
        "referee": ("referee",),
    }
    kind = binding.reference_path.rsplit("/", 1)[-1]
    if binding.identity_decision.subject_type not in kinds.get(kind, ()):
        raise CanonicalResolutionError("identity decision has the wrong entity kind")
    evidence = binding.identity_decision.to_dict()["evidence"]
    assert isinstance(evidence, dict)
    source = evidence["source_contract"]
    assert isinstance(source, dict)
    if source.get("contract") == "ResolutionDecisionV1":
        if reference.provider_native_id is None:
            raise CanonicalResolutionError(
                "anonymous reference needs scoped source-record evidence"
            )
        expected = (
            observation.provenance.provider,
            reference.provider_native_id,
            str(binding.canonical_id),
        )
        actual = (
            source.get("provider_id"),
            source.get("provider_entity_id"),
            source.get("selected_canonical_id"),
        )
        if actual != expected:
            raise CanonicalResolutionError(
                "identity decision belongs to another provider or reference"
            )
        return
    scope = source.get("identity_scope")
    if not isinstance(scope, dict):
        raise CanonicalResolutionError("identity decision requires explicit reference scope")
    expected_scope = {
        "provider": observation.provenance.provider,
        "provider_native_id": reference.provider_native_id,
        "canonical_id": str(binding.canonical_id),
    }
    if reference.provider_native_id is None:
        expected_scope.update(
            source_resource_id=str(observation.provenance.source_resource_id),
            source_record_key=getattr(reference, "source_record_key", None),
        )
        if reference.canonical_id is not None:
            expected_scope["source_canonical_id"] = str(reference.canonical_id)
    if any(scope.get(key) != value for key, value in expected_scope.items()):
        raise CanonicalResolutionError("identity source-record scope does not match the reference")


def _validate_selection[T: Observation](
    candidates: tuple[CanonicalCandidate[T], ...],
    selection: ConflictRecordV1,
    cutoff: datetime,
) -> None:
    if cutoff.utcoffset() is None or selection.created_at.utcoffset() is None:
        raise CanonicalResolutionError("canonical knowledge and decision times require timezones")
    if selection.created_at < cutoff:
        raise CanonicalResolutionError("canonical decision precedes its knowledge cutoff")
    if not candidates:
        raise CanonicalResolutionError("canonical evidence is required")
    first = candidates[0]
    if any(
        (item.resource_type, item.canonical_subject_id, item.context_sha256)
        != (first.resource_type, first.canonical_subject_id, first.context_sha256)
        for item in candidates
    ):
        raise CanonicalResolutionError("canonical candidates must share a resource and subject")
    ids = [str(item.observation.observation_id) for item in candidates]
    if len(ids) != len(set(ids)) or set(ids) != set(selection.observation_refs):
        raise CanonicalResolutionError("selection must retain exactly the candidate evidence")
    if selection.subject_type != f"{first.resource_type}:{first.canonical_subject_id}":
        raise CanonicalResolutionError("selection subject does not match the canonical resource")
    for item in candidates:
        clocks = [item.observation.time.known_at, item.subject_identity.decided_at]
        clocks.extend(binding.identity_decision.decided_at for binding in item.bindings)
        if any(value > cutoff for value in clocks):
            raise CanonicalResolutionError("candidate or identity exceeds the knowledge cutoff")


def _references(value: object, path: str = "") -> dict[str, object]:
    if isinstance(value, (EntityReference, EntityReferenceV2)):
        return {path: value}
    if is_dataclass(value) and not isinstance(value, type):
        result: dict[str, object] = {}
        for item in fields(value):
            if path or item.name not in _METADATA:
                result.update(_references(getattr(value, item.name), path + "/" + item.name))
        return result
    if isinstance(value, tuple):
        return {
            key: ref
            for index, item in enumerate(value)
            for key, ref in _references(item, path + "/" + str(index)).items()
        }
    return {}


def _validate_participants(
    observation: Observation, bindings: tuple[CanonicalBinding, ...]
) -> None:
    refs = {binding.reference_path: binding.canonical_id for binding in bindings}
    paths: list[str] = []
    if isinstance(observation, FixtureObservationV1):
        paths = ["/home_team", "/away_team"]
    elif isinstance(observation, LineupObservationV1):
        paths = [path for path in refs if path.startswith("/players/") and path.endswith("/player")]
    values = [refs[path] for path in paths]
    if len(values) != len(set(values)):
        raise CanonicalResolutionError("canonical participants must remain distinct")


def _canonical_value(value: object, path: str, identities: dict[str, UUID]) -> object:
    if isinstance(value, (EntityReference, EntityReferenceV2)):
        return str(identities[path])
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _canonical_value(
                getattr(value, item.name), path + "/" + item.name, identities
            )
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [
            _canonical_value(item, path + "/" + str(index), identities)
            for index, item in enumerate(value)
        ]
    return value


def _proof_ref(decision: DecisionRecordV1) -> dict[str, str]:
    return {
        "decision_id": str(decision.decision_id),
        "sha256": decision.sha256,
        "known_at": decision.decided_at.isoformat(),
    }


def _candidate_evidence[T: Observation](item: CanonicalCandidate[T]) -> dict[str, object]:
    source = item.observation.provenance
    return {
        "observation_id": str(item.observation.observation_id),
        "observation_sha256": item.observation.sha256,
        "provider": source.provider,
        "source_snapshot_id": str(source.source_snapshot_id),
        "source_resource_id": str(source.source_resource_id),
        "source_sha256": source.source_sha256,
        "canonical_value_sha256": item.value_sha256,
        "subject_identity": _proof_ref(item.subject_identity),
        "bindings": [
            {
                "reference_path": binding.reference_path,
                "canonical_id": str(binding.canonical_id),
                "identity_decision": _proof_ref(binding.identity_decision),
            }
            for binding in sorted(item.bindings, key=lambda value: value.reference_path)
        ],
    }
