"""Prepare immutable files before registering canonical conclusions in one transaction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection, Cursor

from football.canonical_resources.resolution import (
    CanonicalResolution,
    CanonicalResolutionError,
    resolve_canonical_resource,
)
from football.contracts.decisions import DecisionRecordV1, decision_schema
from football.contracts.observations import Observation
from football.contracts.source import canonical_json_bytes
from football.identity.repository import ADMISSION_SOURCE_CONTRACT, IdentityRepository
from football.storage.raw import ImmutableFileStore, ImmutableWrite


@dataclass(frozen=True, slots=True)
class PreparedCanonicalResolution:
    artifact: ImmutableWrite
    identity_artifacts: tuple[ImmutableWrite, ...]


def prepare_canonical_resolution[T: Observation](
    root: Path, resolution: CanonicalResolution[T]
) -> PreparedCanonicalResolution:
    """Publish all bytes before opening the registration transaction."""
    checked = _checked(resolution)
    files = ImmutableFileStore(root)
    proofs = _proofs(checked)
    identities = tuple(
        files.publish(_identity_path(proof.sha256), proof.to_bytes()) for proof in proofs
    )
    artifact = files.publish(_decision_path(checked.decision.sha256), checked.decision.to_bytes())
    return PreparedCanonicalResolution(artifact, identities)


class CanonicalResolutionRegistry:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def register[T: Observation](
        self, resolution: CanonicalResolution[T], prepared: PreparedCanonicalResolution
    ) -> UUID:
        checked = _checked(resolution)
        _check_prepared(checked, prepared)
        return self._register(checked, prepared)

    def register_prepared[T: Observation](
        self, resolution: CanonicalResolution[T], prepared: PreparedCanonicalResolution
    ) -> UUID:
        """Register prepared metadata without filesystem access; caller owns the transaction."""
        checked = _checked(resolution)
        _check_prepared_metadata(checked, prepared)
        return self._register(checked, prepared)

    def _register[T: Observation](
        self, checked: CanonicalResolution[T], prepared: PreparedCanonicalResolution
    ) -> UUID:
        with self._connection.transaction(), self._connection.cursor() as cursor:
            _check_observations(cursor, checked)
            _check_identities(cursor, checked)
            _check_predecessor(cursor, checked)
            _register_decision(cursor, checked, prepared.artifact)
            _register_evidence(cursor, checked)
        return checked.decision.decision_id

    def latest_id_at(
        self,
        resource_type: str,
        canonical_subject_id: UUID,
        context_sha256: str,
        knowledge_cutoff: datetime,
    ) -> UUID | None:
        """A later review/quarantine is returned too; never fall back to an older winner."""
        if knowledge_cutoff.utcoffset() is None:
            raise CanonicalResolutionError("knowledge_cutoff must include a timezone")
        row = self._connection.execute(
            """SELECT decision_id FROM football.canonical_resource_resolutions
               WHERE resource_type=%s AND canonical_subject_id=%s
                 AND context_sha256=%s AND known_at<=%s
               ORDER BY known_at DESC,publication_sequence DESC LIMIT 1""",
            (resource_type, canonical_subject_id, context_sha256, knowledge_cutoff),
        ).fetchone()
        return row[0] if row else None


def _checked[T: Observation](resolution: CanonicalResolution[T]) -> CanonicalResolution[T]:
    predecessor = UUID(resolution.decision.predecessor) if resolution.decision.predecessor else None
    checked = resolve_canonical_resource(
        resolution.candidates,
        resolution.selection,
        knowledge_cutoff=resolution.knowledge_cutoff,
        predecessor=predecessor,
    )
    if checked != resolution:
        raise CanonicalResolutionError("canonical conclusion differs from its declared evidence")
    return checked


def _proofs[T: Observation](resolution: CanonicalResolution[T]) -> tuple[DecisionRecordV1, ...]:
    proofs = {}
    for candidate in resolution.candidates:
        for proof in (
            candidate.subject_identity,
            *(binding.identity_decision for binding in candidate.bindings),
        ):
            proofs[proof.sha256] = proof
    return tuple(proofs[key] for key in sorted(proofs))


def _decision_path(digest: str) -> str:
    return f"canonical-resolutions/v1/{digest}.json"


def _identity_path(digest: str) -> str:
    return f"canonical-resolutions/identity/v1/{digest}.json"


def _check_prepared_metadata[T: Observation](
    resolution: CanonicalResolution[T], prepared: PreparedCanonicalResolution
) -> None:
    expected = tuple(
        (_identity_path(proof.sha256), proof.sha256, len(proof.to_bytes()))
        for proof in _proofs(resolution)
    )
    actual = tuple(
        (item.relative_path, item.sha256, item.size_bytes) for item in prepared.identity_artifacts
    )
    if actual != expected:
        raise CanonicalResolutionError("prepared identity artifacts differ from their evidence")
    artifact = prepared.artifact
    if (artifact.relative_path, artifact.sha256, artifact.size_bytes) != (
        _decision_path(resolution.decision.sha256),
        resolution.decision.sha256,
        len(resolution.decision.to_bytes()),
    ):
        raise CanonicalResolutionError("prepared canonical artifact differs from its decision")


def _check_prepared[T: Observation](
    resolution: CanonicalResolution[T], prepared: PreparedCanonicalResolution
) -> None:
    _check_prepared_metadata(resolution, prepared)
    writes = (prepared.artifact, *prepared.identity_artifacts)
    payloads = (
        resolution.decision.to_bytes(),
        *(proof.to_bytes() for proof in _proofs(resolution)),
    )
    try:
        for write, payload in zip(writes, payloads, strict=True):
            if write.path.is_symlink() or write.path.read_bytes() != payload:
                raise CanonicalResolutionError("prepared artifact bytes are missing or changed")
    except OSError as error:
        raise CanonicalResolutionError("prepared artifact bytes are unavailable") from error


def _check_observations[T: Observation](
    cursor: Cursor[Any], resolution: CanonicalResolution[T]
) -> None:
    expected = {
        item.observation.observation_id: (item.observation.sha256, item.observation.time.known_at)
        for item in resolution.candidates
    }
    rows = cursor.execute(
        "SELECT observation_id,artifact_sha256,known_at "
        "FROM football.resource_observation_artifacts "
        "WHERE observation_id=ANY(%s)",
        (list(expected),),
    ).fetchall()
    if {row[0]: row[1:] for row in rows} != expected:
        raise CanonicalResolutionError(
            "canonical observations are unregistered or differ from their artifacts"
        )


def _register_decision[T: Observation](
    cursor: Cursor[Any], resolution: CanonicalResolution[T], artifact: ImmutableWrite
) -> None:
    decision = resolution.decision
    selected = resolution.selected.observation.observation_id if resolution.selected else None
    predecessor = UUID(decision.predecessor) if decision.predecessor else None
    schema_hash = hashlib.sha256(canonical_json_bytes(decision_schema())).hexdigest()
    values = (
        decision.decision_id,
        resolution.resource_type,
        resolution.canonical_subject_id,
        resolution.candidates[0].context_sha256,
        decision.disposition,
        selected,
        predecessor,
        resolution.knowledge_cutoff,
        decision.decided_at,
        decision.contract_version,
        schema_hash,
        artifact.relative_path,
        artifact.sha256,
    )
    cursor.execute(
        """WITH publication_clock AS (SELECT clock_timestamp() AS stamp)
           INSERT INTO football.canonical_resource_resolutions(
               decision_id,resource_type,canonical_subject_id,context_sha256,
               disposition,selected_observation_id,
               predecessor_decision_id,knowledge_cutoff,decided_at,decision_contract_version,
               schema_sha256,artifact_path,artifact_sha256,registered_at,known_at)
           SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,stamp,greatest(stamp,%s,%s)
           FROM publication_clock ON CONFLICT (decision_id) DO NOTHING""",
        (*values, decision.decided_at, resolution.knowledge_cutoff),
    )
    row = cursor.execute(
        """SELECT resource_type,canonical_subject_id,context_sha256,
                  disposition,selected_observation_id,
                  predecessor_decision_id,knowledge_cutoff,decided_at,decision_contract_version,
                  schema_sha256,artifact_path,artifact_sha256
           FROM football.canonical_resource_resolutions WHERE decision_id=%s""",
        (decision.decision_id,),
    ).fetchone()
    if row != values[1:]:
        raise CanonicalResolutionError(
            "canonical decision identity conflicts with registered evidence"
        )


def _check_predecessor[T: Observation](
    cursor: Cursor[Any], resolution: CanonicalResolution[T]
) -> None:
    decision = resolution.decision
    if cursor.execute(
        "SELECT 1 FROM football.canonical_resource_resolutions WHERE decision_id=%s",
        (decision.decision_id,),
    ).fetchone():
        return
    row = cursor.execute(
        """SELECT decision_id FROM football.canonical_resource_resolutions
           WHERE resource_type=%s AND canonical_subject_id=%s AND context_sha256=%s
           ORDER BY publication_sequence DESC LIMIT 1""",
        (
            resolution.resource_type,
            resolution.canonical_subject_id,
            resolution.candidates[0].context_sha256,
        ),
    ).fetchone()
    expected = str(row[0]) if row else None
    if decision.predecessor != expected:
        raise CanonicalResolutionError("canonical revision must reference the current predecessor")


def _check_identities[T: Observation](
    cursor: Cursor[Any], resolution: CanonicalResolution[T]
) -> None:
    """Reuse the existing identity owner; never admit an asserted proof or confidence."""
    for proof in _proofs(resolution):
        evidence = proof.to_dict()["evidence"]
        assert isinstance(evidence, dict)
        source = evidence["source_contract"]
        assert isinstance(source, dict)
        if source.get("contract") == ADMISSION_SOURCE_CONTRACT:
            _check_admission(cursor, proof, source, resolution.knowledge_cutoff)
            continue
        if source.get("contract") != "ResolutionDecisionV1":
            raise CanonicalResolutionError("identity source has no registered publication adapter")
        row = cursor.execute(
            """SELECT r.subject_type,p.code,r.provider_entity_id,r.evidence_refs,
                      r.candidate_canonical_ids,r.rule_version,r.confidence,r.status,
                      r.selected_canonical_id,r.actor,r.reason,r.created_at,
                      r.supersedes_decision_id
               FROM football.resolution_decisions r
               JOIN football.providers p ON p.id=r.provider_id
               WHERE r.decision_key=%s AND NOT EXISTS (
                   SELECT 1 FROM football.resolution_decisions successor
                   WHERE successor.supersedes_decision_id=r.id AND successor.created_at<=%s)
               FOR SHARE OF r""",
            (evidence["source_sha256"], resolution.knowledge_cutoff),
        ).fetchone()
        names = (
            "subject_type",
            "provider_id",
            "provider_entity_id",
            "evidence_refs",
            "candidate_canonical_ids",
            "rule_version",
            "confidence",
            "status",
            "selected_canonical_id",
            "actor",
            "reason",
            "created_at",
            "supersedes_decision_id",
        )
        actual = None if row is None else dict(zip(names, row, strict=True))
        expected = {name: source.get(name) for name in names}
        if actual is not None:
            for name in ("selected_canonical_id", "supersedes_decision_id"):
                actual[name] = str(actual[name]) if actual[name] is not None else None
        created_at = source.get("created_at")
        if not isinstance(created_at, str):
            raise CanonicalResolutionError("identity source requires its decision clock")
        expected["created_at"] = datetime.fromisoformat(created_at)
        if actual != expected or (
            proof.decision_type != "identity_resolution"
            or proof.subject_type != source.get("subject_type")
            or proof.decided_at != expected["created_at"]
            or proof.reason != source.get("reason")
            or proof.predecessor != source.get("supersedes_decision_id")
            or proof.effective_at is not None
        ):
            raise CanonicalResolutionError("identity proof is unregistered, superseded or changed")


def _check_admission(
    cursor: Cursor[Any],
    proof: DecisionRecordV1,
    source: dict[str, Any],
    cutoff: datetime,
) -> None:
    if proof.subject_type not in ("team", "competition"):
        raise CanonicalResolutionError("identity admission proof has the wrong entity kind")
    mapping = source.get("mapping_id")
    if not isinstance(mapping, str):
        raise CanonicalResolutionError("identity admission proof requires its mapping UUID")
    try:
        mapping_id = UUID(mapping)
    except ValueError as error:
        raise CanonicalResolutionError(
            "identity admission proof has an invalid mapping UUID"
        ) from error
    subject: Literal["team", "competition"] = (
        "team" if proof.subject_type == "team" else "competition"
    )
    actual = IdentityRepository(cursor.connection).admission_proof_at(subject, mapping_id, cutoff)
    if actual != proof:
        raise CanonicalResolutionError(
            "identity admission proof is unregistered, revoked or changed"
        )


def load_canonical_decision(root: Path, decision_id: UUID, sha256: str) -> DecisionRecordV1:
    """Verify immutable conclusion bytes outside the metadata transaction."""
    path = ImmutableFileStore(root).path_for(_decision_path(sha256))
    if path.is_symlink():
        raise CanonicalResolutionError("canonical artifact must not be a symlink")
    payload = path.read_bytes()
    decision = DecisionRecordV1.from_bytes(payload)
    if (
        hashlib.sha256(payload).hexdigest() != sha256
        or decision.decision_id != decision_id
        or decision.decision_type != "canonical_resource_resolution"
    ):
        raise CanonicalResolutionError("canonical artifact checksum or identity mismatch")
    return decision


def _register_evidence[T: Observation](
    cursor: Cursor[Any], resolution: CanonicalResolution[T]
) -> None:
    expected = []
    for candidate in resolution.candidates:
        item = candidate.observation
        role = (
            "SUPPORTING"
            if item.observation_id in resolution.supporting
            else ("CONFLICTING" if item.observation_id in resolution.conflicting else "UNRESOLVED")
        )
        values = (
            resolution.decision.decision_id,
            item.observation_id,
            role,
            item.sha256,
            candidate.value_sha256,
        )
        cursor.execute(
            """INSERT INTO football.canonical_resolution_evidence(
                decision_id,observation_id,role,observation_sha256,canonical_value_sha256)
               VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            values,
        )
        expected.append(values[1:])
    actual = cursor.execute(
        "SELECT observation_id,role,observation_sha256,canonical_value_sha256 "
        "FROM football.canonical_resolution_evidence WHERE decision_id=%s ORDER BY observation_id",
        (resolution.decision.decision_id,),
    ).fetchall()
    if actual != expected:
        raise CanonicalResolutionError(
            "registered canonical lineage differs from its source evidence"
        )
