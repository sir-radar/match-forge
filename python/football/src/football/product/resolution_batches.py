"""Bounded independent approvals; each case retains its own transaction and audit."""

from pathlib import Path
from typing import Any

from psycopg import Connection, Error

from football.product.identity_admission import RetainedEvidenceChanged, RetainedIdentityVerifier
from football.product.resolution_actions import apply_one, preview

# One normal Admin page bounds retained-byte verification and HTTP request time.
MAX_BATCH = 20
MUTATIONS = {"APPROVE", "CORRECT", "QUARANTINE", "RESOLVE_DUPLICATE"}


def validate_batch(requests: list[dict[str, Any]]) -> None:
    if not isinstance(requests, list) or not 1 <= len(requests) <= MAX_BATCH:
        raise ValueError("review between 1 and 20 independent cases")
    keys = [request["case_key"] for request in requests]
    if len(keys) != len(set(keys)):
        raise ValueError("a batch cannot repeat a case")


def conflict_scopes(prepared: dict[str, Any]) -> set[str]:
    """Overlapping identities or fixture effects require separate review transactions."""
    if prepared["action"] not in MUTATIONS:
        return set()
    detail, candidate = prepared["detail"], prepared["candidate"]
    if detail.get("affected_fixtures_has_more"):
        raise ValueError("unbounded fixture effects require single-case review")
    scopes = {prepared["case_key"]}
    scopes.update("fixture_record:" + key for key in detail.get("affected_fixtures", []))
    for field, prefix in (
        ("target_mapping_id", "team:"),
        ("fixture_registration_id", "registration:"),
        ("fixture_id", "fixture_record:"),
    ):
        if field in candidate:
            scopes.add(prefix + candidate[field])
    canonical = detail.get("decision", {}).get("canonical_id")
    if canonical:
        scopes.add("entity:" + canonical)
    scopes.update(
        "entity:" + item["canonical_id"]
        for item in detail.get("candidates", [])
        if item.get("mapping_id") == candidate.get("target_mapping_id") and item.get("canonical_id")
    )
    return scopes


def preview_batch(
    connection: Connection[Any], root: Path, requests: list[dict[str, Any]]
) -> dict[str, Any]:
    validate_batch(requests)
    verifier = RetainedIdentityVerifier(root)
    items = []
    seen: set[str] = set()
    for request in requests:
        try:
            prepared = preview(connection, root, request, verifier)
            scopes = conflict_scopes(prepared)
            if scopes & seen:
                raise ValueError("overlapping identity or fixture effects require separate review")
            seen.update(scopes)
            items.append(
                {"case_key": request["case_key"], "status": "PREVIEWED", "preview": prepared}
            )
        except (ValueError, KeyError, OSError, RetainedEvidenceChanged) as error:
            items.append(
                {"case_key": request["case_key"], "status": "BLOCKED", "error": str(error)}
            )
    return {"items": items, "source_bytes_verified": verifier.source_bytes_verified}


def apply_batch(
    connection: Connection[Any], root: Path, requests: list[dict[str, Any]], actor: str
) -> dict[str, Any]:
    validate_batch(requests)
    preflight = preview_batch(connection, root, requests)
    # Even when preflight fails, a committed request must replay its exact result.
    blocked = {
        item["case_key"]: item.get("error")
        for item in preflight["items"]
        if item["status"] == "BLOCKED"
    }
    connection.commit()
    results = []
    for request in requests:
        try:
            prior = connection.execute(
                "SELECT 1 FROM football.resolution_review_events WHERE request_id=%s",
                (request["request_id"],),
            ).fetchone()
            if request["case_key"] in blocked and not prior:
                raise ValueError(blocked[request["case_key"]])
            event = apply_one(connection, root, request, actor)
            connection.commit()
            results.append({"case_key": request["case_key"], "status": "SUCCEEDED", "event": event})
        except (ValueError, KeyError, OSError, RetainedEvidenceChanged) as error:
            connection.rollback()
            results.append(
                {"case_key": request["case_key"], "status": "BLOCKED", "error": str(error)}
            )
        except Error as error:
            connection.rollback()
            results.append(
                {
                    "case_key": request["case_key"],
                    "status": "BLOCKED",
                    "error": f"Database rejected decision ({error.sqlstate}); recheck before retry",
                }
            )
    return {
        "items": results,
        "succeeded": sum(item["status"] == "SUCCEEDED" for item in results),
        "blocked": sum(item["status"] == "BLOCKED" for item in results),
    }
