"""Preview, approve and recheck each decision against existing domain qualification."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection

from football.product.domain import sha256_json
from football.product.identity_admission import RetainedIdentityVerifier, admit_reviewed_mapping
from football.product.identity_correction import (
    TeamIdentityCorrection,
    correct_team_identity,
    qualify_team_correction,
)
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.resolution_cases import append_event, case_detail
from football.product.resolution_recovery import enqueue_recovery
from football.storage.locks import (
    FIXTURE_CROSSWALK_LOCK,
    IDENTITY_ADMISSION_LOCK,
    LockClass,
    LockRequest,
    acquire_locks,
)

REVIEW_ACTIONS = {"REJECT", "REQUEST_EVIDENCE", "BLOCK", "DEFER"}


def correction_request(key: UUID, candidate: dict[str, Any]) -> TeamIdentityCorrection:
    if candidate.get("orientation") not in {"HOME", "AWAY"}:
        raise ValueError("correction requires HOME or AWAY orientation")
    return TeamIdentityCorrection(
        key,
        UUID(candidate["target_mapping_id"]),
        UUID(candidate["original_decision_id"]),
        UUID(candidate["fixture_registration_id"]),
        candidate["orientation"],
    )


def preview(
    connection: Connection[Any],
    root: Path,
    request: dict[str, Any],
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    detail = case_detail(connection, root, request["case_key"], verifier)
    action = request["action"]
    if request["case_key"].split(":", 1)[0] not in {
        "team",
        "competition",
        "fixture",
        "fixture_record",
    }:
        raise ValueError("identity or fixture case required")
    qualification: dict[str, Any] = {"status": "QUALIFIED", "reason": "REVIEW_WORKFLOW_ONLY"}
    if action == "REJECT" and not any(
        item["mapping_id"] == request.get("candidate", {}).get("target_mapping_id")
        for item in detail.get("candidates", [])
    ):
        qualification = {"status": "BLOCKED", "reason": "Select an exact retained candidate"}
    if action not in REVIEW_ACTIONS:
        try:
            qualification = qualify_action(connection, root, request, detail, verifier)
        except ValueError as error:
            qualification = {"status": "BLOCKED", "reason": str(error)}
    result = {
        "case_key": request["case_key"],
        "action": action,
        "detail": detail,
        "candidate": request.get("candidate", {}),
        "reason": request["reason"],
        "qualification": qualification,
        "allowed": qualification["status"] == "QUALIFIED",
        "downstream_status": "NOT_APPLIED",
        "approval_required": True,
    }
    result["evidence_version"] = sha256_json(result)
    return result


def qualify_action(
    connection: Connection[Any],
    root: Path,
    request: dict[str, Any],
    detail: dict[str, Any],
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    action, kind = request["action"], request["case_key"].split(":", 1)[0]
    candidate = request.get("candidate", {})
    if kind not in {"team", "competition", "fixture", "fixture_record"}:
        raise ValueError("identity review requires an identity or fixture case")
    if action == "REVALIDATE":
        return {"status": "QUALIFIED", "reason": "RECHECK_ONLY_NO_NEW_ADMISSION"}
    if kind == "fixture" and action == "RESOLVE_DUPLICATE":
        _, provider, identifier = request["case_key"].split(":", 2)
        proof = OperationalProviderSync(
            connection, root, provider_code=provider
        ).preview_reviewed_mapping(
            identifier,
            UUID(candidate["fixture_id"]),
            source_snapshot_id=UUID(candidate["source_snapshot_id"]),
            verifier=verifier,
        )
        return {"status": "QUALIFIED", "reason": "EXISTING_REVIEWED_FIXTURE_RULES", "proof": proof}
    if kind not in {"team", "competition"}:
        raise ValueError("action is not supported for this case")
    if action == "CORRECT" and kind == "team":
        return qualify_team_correction(
            connection,
            root,
            correction_request(UUID(request["case_key"].split(":", 1)[1]), candidate),
            verifier=verifier,
        )
    if action == "QUARANTINE":
        return {"status": "QUALIFIED", "reason": "WITHDRAW_CURRENT_TRUST_PROSPECTIVELY"}
    if action != "APPROVE":
        raise ValueError("action is not supported for this mapping")
    allowed = detail["decision"]["disposition"] in {"ORIGIN_ANCHOR", "CROSSWALK"}
    return {
        "status": "QUALIFIED" if allowed else "BLOCKED",
        "reason": detail["decision"]["reason"],
        "decision": detail["decision"],
    }


def _quarantine(connection: Connection[Any], detail: dict[str, Any]) -> None:
    admission = detail.get("admission")
    if not admission or admission["disposition"] == "REVOKED":
        return
    connection.execute(
        """INSERT INTO football.product_identity_admissions
           (entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,disposition,
            reason,source_snapshot_id,source_observed_at,evidence,evidence_sha256,
            corrects_decision_id,target_mapping_id)
           SELECT entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,'REVOKED',
                  'OPERATOR_REVOKED',source_snapshot_id,source_observed_at,evidence,evidence_sha256,
                  corrects_decision_id,target_mapping_id
           FROM football.product_identity_admissions WHERE decision_id=%s""",
        (admission["decision_id"],),
    )


def apply_domain(
    connection: Connection[Any],
    root: Path,
    request: dict[str, Any],
    prepared: dict[str, Any],
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    kind, identifier = request["case_key"].split(":", 1)
    action = request["action"]
    detail = prepared["detail"]
    if action in REVIEW_ACTIONS or action == "REVALIDATE":
        return {
            "status": "RECORDED",
            "case_status": detail["status"],
            "domain_mutated": False,
            "downstream_status": "NOT_REQUESTED",
        }
    if action == "QUARANTINE":
        _quarantine(connection, detail)
        return {"status": "QUARANTINED", "downstream_status": "DOMAIN_HISTORY_REQUALIFIED"}
    if action == "CORRECT":
        result = correct_team_identity(
            connection,
            root,
            correction_request(UUID(identifier), request["candidate"]),
            reviewed_revalidation=True,
            verifier=verifier,
        )
    elif action == "APPROVE":
        result = admit_reviewed_mapping(
            connection,
            root,
            cast(Literal["team", "competition"], kind),
            UUID(identifier),
            verifier=verifier,
        )
    elif action == "RESOLVE_DUPLICATE":
        provider, native = identifier.split(":", 1)
        candidate = request["candidate"]
        OperationalProviderSync(connection, root, provider_code=provider).apply_reviewed_mapping(
            native,
            UUID(candidate["fixture_id"]),
            source_snapshot_id=UUID(candidate["source_snapshot_id"]),
            verifier=verifier,
        )
        result = {"fixture_id": candidate["fixture_id"], "status": "RESOLVED"}
    else:
        raise ValueError("unsupported action")
    return {
        "status": "APPLIED",
        "decision": result,
        "downstream_status": "RECONCILIATION_REQUIRED; EXISTING_REFRESH_QUEUES_OWN_REFRESH",
    }


def apply_one(
    connection: Connection[Any], root: Path, request: dict[str, Any], actor: str
) -> dict[str, Any]:
    if request.get("approved") is not True:
        raise ValueError("explicit operator approval is required")
    request_hash = sha256_json({"request": request, "actor": actor})
    previous = replayed_decision(connection, request["request_id"], request_hash)
    if previous:
        return previous
    verifier = RetainedIdentityVerifier(root)
    preview(connection, root, request, verifier)
    verifier.seal()
    with connection.transaction():
        acquire_locks(
            connection, (LockRequest(LockClass.CONTROL, "resolution:" + request["case_key"]),)
        )
        previous = replayed_decision(connection, request["request_id"], request_hash)
        if previous:
            return previous
        # Domain owners acquire the same identity lock; stale previews cannot slip between checks.
        if request["case_key"].split(":", 1)[0] in {"team", "competition", "fixture"}:
            acquire_locks(connection, (IDENTITY_ADMISSION_LOCK, FIXTURE_CROSSWALK_LOCK))
        current = preview(connection, root, request, verifier)
        if current["evidence_version"] != request["evidence_version"]:
            raise ValueError("evidence or review changed; preview again before approval")
        if not current["allowed"]:
            raise ValueError("backend qualification blocked this action")
        result = apply_domain(connection, root, request, current, verifier)
        # Serialize domain datetime values before storing the workflow result.
        result = json_safe(result)
        recovering = request["action"] in {
            "APPROVE",
            "CORRECT",
            "QUARANTINE",
            "RESOLVE_DUPLICATE",
            "REVALIDATE",
        }
        if recovering:
            result["downstream_status"] = "QUEUED; EXISTING_REFRESH_QUEUES_OWN_PUBLICATION"
            result["recovery_request_id"] = request["request_id"]
        event = append_event(
            connection, request, actor, request_hash, {"preview": current, "result": result}
        )
        if recovering:
            enqueue_recovery(connection, request["request_id"], current)
        return event


def json_safe(value: dict[str, Any]) -> dict[str, Any]:
    import json

    return cast(dict[str, Any], json.loads(json.dumps(value, default=str)))


def replayed_decision(
    connection: Connection[Any], request_id: str, request_hash: str
) -> dict[str, Any] | None:
    previous = connection.execute(
        "SELECT request_sha256,to_jsonb(e) FROM football.resolution_review_events e "
        "WHERE request_id=%s",
        (request_id,),
    ).fetchone()
    if previous and previous[0] != request_hash:
        raise ValueError("request ID is already bound to different approved inputs")
    return cast(dict[str, Any], previous[1]) if previous else None
