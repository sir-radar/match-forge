"""Resolution Center cases for external prediction associations (external-only).

A decision here appends to football.external_prediction_context_matches. It never
changes canonical fixtures, team identity, provider mappings or history.
"""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.external_prediction_association import (
    refresh_contextual_association,
    review_contextual_association,
)

KIND = "external_prediction"
ACTIONS = frozenset({"APPROVE", "REJECT", "REVALIDATE"})

EXTERNAL_CASES = """
WITH cases AS (
    SELECT 'external_prediction:'||c.prediction_id AS case_key,'external_prediction' AS kind,
           ep.source_code AS provider,
           ep.home_team_text||' vs '||ep.away_team_text||' · '||ep.prediction_date AS name,
           c.classification AS status,c.reason,c.basis,ep.competition_text AS country,
           cardinality(c.candidate_fixture_ids) AS candidates,c.decided_at AS recorded_at
    FROM football.external_prediction_context_current c
    JOIN football.external_predictions ep USING (prediction_id)
    WHERE c.decided_at<=transaction_timestamp()
), filtered AS (
    SELECT * FROM cases WHERE (%(provider)s='' OR provider=%(provider)s)
      AND (%(status)s='' OR status=%(status)s) AND (%(kind)s='' OR kind=%(kind)s)
      AND (%(q)s='' OR position(lower(%(q)s) IN lower(name||' '||reason||' '||case_key))>0)
)
"""


def external_detail(connection: Connection[Any], key: str) -> dict[str, Any]:
    prediction = UUID(key.split(":", 1)[1])
    with connection.cursor(row_factory=dict_row) as cursor:
        source = cursor.execute(
            """SELECT ep.prediction_id,ep.source_code,ep.source_page,ep.prediction_date,
                ep.original_date_text,ep.competition_text,ep.home_team_text,ep.away_team_text,
                ep.market,ep.selection,ep.collected_at,eff.effective_match_status,
                eff.effective_fixture_id,eff.date_status
            FROM football.external_predictions ep
            JOIN football.external_prediction_effective eff USING (prediction_id)
            WHERE ep.prediction_id=%s""",
            (prediction,),
        ).fetchone()
        if source is None:
            raise ValueError("external prediction case not found")
        history = cursor.execute(
            """SELECT context_match_id,basis,classification,reason,fixture_id,policy_version,
                review_reason,decided_at FROM football.external_prediction_context_matches
            WHERE prediction_id=%s ORDER BY decided_at,context_match_id""",
            (prediction,),
        ).fetchall()
        current = cursor.execute(
            "SELECT evidence FROM football.external_prediction_context_current "
            "WHERE prediction_id=%s",
            (prediction,),
        ).fetchone()
        settlement = cursor.execute(
            """SELECT settlement_state,home_score,away_score,score_basis,
                evidence->>'fixture_association' AS association,
                evidence->>'evaluation' AS evaluation
            FROM football.external_prediction_latest_results WHERE prediction_id=%s""",
            (prediction,),
        ).fetchone()
    evidence = current["evidence"] if current else None
    # Evidence versions hash this detail, so keep it JSON-native like the other cases.
    return _json_native(
        {
            "case_key": key,
            "status": history[-1]["classification"] if history else "NOT_EVALUATED",
            "source": source,
            "decision": evidence,
            "candidates": evidence["candidates"] if evidence else [],
            "decision_history": history,
            "settlement": settlement,
            "verified_association": source["effective_match_status"] == "MATCHED",
            "proposed_action": (
                "APPROVE one retained candidate, REJECT the association, or REVALIDATE to rerun "
                "the policy. External-only: canonical identity is unchanged."
            ),
        }
    )


def _json_native(value: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(value, default=str)))


def qualify_external(request: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    action = request["action"]
    if action not in ACTIONS:
        raise ValueError("use APPROVE, REJECT or REVALIDATE for external prediction cases")
    if detail["verified_association"]:
        return {"status": "BLOCKED", "reason": "VERIFIED_ASSOCIATION_IS_NOT_REVIEWED_HERE"}
    if action == "APPROVE":
        fixture = request.get("candidate", {}).get("fixture_id")
        candidates = {item["effective_fixture_id"] for item in detail["candidates"]}
        if fixture not in candidates:
            return {"status": "BLOCKED", "reason": "Select one retained candidate fixture"}
    if action != "REVALIDATE" and detail["decision"] is None:
        return {"status": "BLOCKED", "reason": "Run matching before reviewing"}
    return {
        "status": "QUALIFIED",
        "reason": {
            "APPROVE": "EXTERNAL_ONLY_REVIEWED_ASSOCIATION",
            "REJECT": "EXTERNAL_ONLY_REVIEWED_REJECTION",
            "REVALIDATE": "RERUN_CONTEXTUAL_POLICY",
        }[action],
        "canonical_identity": "UNCHANGED",
    }


def apply_external(
    connection: Connection[Any], request: dict[str, Any], actor: str
) -> dict[str, Any]:
    prediction = UUID(request["case_key"].split(":", 1)[1])
    action = request["action"]
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT football.authorize_worker_publication()")
        if action == "REVALIDATE":
            changed = refresh_contextual_association(cursor, prediction, retry=True)
        else:
            fixture = request["candidate"]["fixture_id"] if action == "APPROVE" else None
            changed = review_contextual_association(
                cursor,
                prediction,
                UUID(fixture) if fixture else None,
                reason=request["reason"],
                reviewer=actor,
            )
    return {
        "status": "APPLIED" if changed else "UNCHANGED",
        "domain_mutated": False,
        "downstream_status": "QUEUED; EXTERNAL_SETTLEMENT_REFRESH",
    }
