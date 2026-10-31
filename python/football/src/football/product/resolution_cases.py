"""Read-only, paginated operational cases over the existing domain owners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.product.identity_admission import RetainedIdentityVerifier
from football.product.resolution_data import data_detail
from football.product.resolution_identity import mapping_detail

MAPPING_CASES = """
WITH mappings AS (
    SELECT 'team' AS kind,m.id,m.team_id AS canonical_id,p.code AS provider,
           m.provider_team_id AS provider_entity_id,t.name,t.country,m.source_snapshot_id,
           m.mapping_method,m.valid_from,m.valid_to
    FROM football.team_provider_mappings m JOIN football.providers p ON p.id=m.provider_id
    LEFT JOIN football.product_teams t ON t.team_id=m.team_id
    UNION ALL
    SELECT 'competition',m.id,m.competition_id,p.code,m.provider_competition_id,t.name,t.country,
           m.source_snapshot_id,m.mapping_method,m.valid_from,m.valid_to
    FROM football.competition_provider_mappings m JOIN football.providers p ON p.id=m.provider_id
    LEFT JOIN football.product_competitions t ON t.competition_id=m.competition_id
), current_cases AS (
    SELECT m.*,m.kind||':'||m.id AS case_key,
           CASE WHEN a.disposition='CONTRADICTORY' THEN 'CONTRADICTORY'
                WHEN a.disposition='REVOKED' THEN 'BLOCKED'
                WHEN football.product_mapping_trusted(m.kind,m.id,a.canonical_id)
                    THEN 'VERIFIED'
                WHEN a.reason='RETAINED_SOURCE_EVIDENCE_REQUIRED' THEN 'BLOCKED'
                WHEN a.disposition IN ('ORIGIN_ANCHOR','CROSSWALK') THEN 'NEEDS_REVIEW'
                ELSE 'UNRESOLVED' END AS status,
           coalesce(a.reason,'ADMISSION_OR_REVIEW_EVIDENCE_REQUIRED') AS reason,
           a.decision_id,a.canonical_id AS effective_canonical_id
    FROM mappings m LEFT JOIN LATERAL (
        SELECT * FROM football.product_identity_admissions a
        WHERE a.entity_type=m.kind AND a.mapping_id=m.id AND decided_at<=transaction_timestamp()
        ORDER BY decided_at DESC,decision_id DESC LIMIT 1
    ) a ON true WHERE (m.valid_from IS NULL OR m.valid_from<=transaction_timestamp())
                   AND (m.valid_to IS NULL OR m.valid_to>transaction_timestamp())
), filtered AS (
    SELECT * FROM current_cases WHERE (%(provider)s='' OR provider=%(provider)s)
      AND (%(status)s='' OR status=%(status)s) AND (%(kind)s='' OR kind=%(kind)s)
      AND (%(q)s='' OR position(lower(%(q)s) IN lower(
          coalesce(name,'')||' '||provider_entity_id||' '||canonical_id::text||' '||
          coalesce(country,'')||' '||reason))>0)
)
"""

FIXTURE_CASES = """
WITH latest AS (
    SELECT DISTINCT ON(provider_code,provider_match_id) *
    FROM football.product_provider_mapping_decisions WHERE created_at<=transaction_timestamp()
    ORDER BY provider_code,provider_match_id,observed_at DESC,decision_id DESC
), cases AS (
    SELECT 'fixture:'||provider_code||':'||provider_match_id AS case_key,'fixture' AS kind,
           provider_code AS provider,provider_match_id AS name,
           disposition AS status,
           disposition AS recorded_status,reason,candidate_fixture_id AS fixture_id,
           source_snapshot_id,decision_id,observed_at
    FROM latest
    UNION ALL
    SELECT 'fixture_record:'||f.fixture_id,'fixture','',
           home.name||' vs '||away.name,
           CASE WHEN f.identity_status='QUARANTINED' OR
                     r.resolution_status IN ('AMBIGUOUS_QUARANTINED',
                                             'IMPOSSIBLE_TEAM_SCHEDULE_QUARANTINED')
                THEN 'BLOCKED' ELSE 'NEEDS_REVIEW' END,
           f.identity_status,coalesce(r.resolution_reason,'PROVISIONAL_FIXTURE_IDENTITY'),
           f.fixture_id,NULL::uuid,NULL::uuid,f.updated_at
    FROM football.product_fixtures f JOIN football.product_teams home
        ON home.team_id=f.home_team_id JOIN football.product_teams away
        ON away.team_id=f.away_team_id
    LEFT JOIN football.fixture_identity_resolutions r
        ON r.member_fixture_id=f.fixture_id AND r.active
    WHERE f.identity_status<>'VERIFIED' AND f.updated_at<=transaction_timestamp()
      AND (r.resolution_status IS NULL OR r.resolution_status<>'DUPLICATE_RESOLVED')
), filtered AS (
    SELECT * FROM cases WHERE (%(provider)s='' OR provider=%(provider)s)
        AND (%(status)s='' OR status=%(status)s) AND (%(kind)s='' OR kind=%(kind)s)
        AND (%(q)s='' OR position(lower(%(q)s) IN lower(name||' '||reason||' '||case_key))>0)
)
"""

HISTORY_CASES = """
WITH cases AS (
    SELECT entity_type||':'||mapping_id AS case_key,decision_id::text AS event_id,
           provider_code AS provider,entity_type AS kind,disposition AS status,
           disposition AS action,reason,decided_at AS recorded_at,
           'product_identity_admissions' AS source,to_jsonb(a) AS detail
    FROM football.product_identity_admissions a WHERE decided_at<=transaction_timestamp()
    UNION ALL
    SELECT 'fixture:'||provider_code||':'||provider_match_id,decision_id::text,
           provider_code,'fixture',disposition,disposition,reason,created_at,
           'product_provider_mapping_decisions',to_jsonb(d)
    FROM football.product_provider_mapping_decisions d WHERE created_at<=transaction_timestamp()
    UNION ALL
    SELECT 'fixture_record:'||member_fixture_id,
           canonical_real_fixture_id||':'||member_fixture_id||':'||resolution_version,
           '', 'fixture',resolution_status,resolution_status,resolution_reason,created_at,
           'fixture_identity_resolutions (current records)',to_jsonb(r)
    FROM football.fixture_identity_resolutions r WHERE created_at<=transaction_timestamp()
), filtered AS (
    SELECT * FROM cases WHERE (%(provider)s='' OR provider=%(provider)s)
      AND (%(status)s='' OR status=%(status)s) AND (%(kind)s='' OR kind=%(kind)s)
      AND (%(case_key)s='' OR case_key=%(case_key)s)
      AND (%(q)s='' OR position(lower(%(q)s) IN lower(case_key||' '||action||' '||reason))>0)
)
"""


def case_page(connection: Connection[Any], view: str, query: dict[str, Any]) -> dict[str, Any]:
    cte = {"identity": MAPPING_CASES, "fixtures": FIXTURE_CASES, "history": HISTORY_CASES}[view]
    if view == "history" and review_ready(connection):
        review_sql = """ UNION ALL SELECT case_key,event_id::text,'',split_part(case_key,':',1),
            action,action,reason,recorded_at,'resolution_review_events',to_jsonb(e)
            FROM football.resolution_review_events e WHERE recorded_at<=transaction_timestamp()
        """
        cte = cte.replace("), filtered AS (", review_sql + "), filtered AS (")
    params = {key: query.get(key, "") for key in ("provider", "status", "kind", "q", "case_key")}
    page, size = query.get("page", 1), query.get("page_size", 20)
    params.update(limit=size, offset=(page - 1) * size)
    order = "recorded_at DESC,event_id DESC" if view == "history" else "provider,case_key"
    items = connection.execute(
        cte
        + "SELECT to_jsonb(f) FROM filtered f ORDER BY "
        + order
        + " LIMIT %(limit)s OFFSET %(offset)s",
        params,
    ).fetchall()
    counts = dict(
        connection.execute(
            cte + "SELECT status,count(*) FROM filtered GROUP BY status ORDER BY status", params
        ).fetchall()
    )
    groups = case_groups(connection, cte, params, view)
    return {
        "items": [row[0] for row in items],
        "page": page,
        "page_size": size,
        "total": sum(counts.values()),
        "counts": counts,
        "groups": groups[:100],
        "groups_has_more": len(groups) > 100,
        "scope": (
            "DOMAIN_DECISION_HISTORY; fixture resolutions show current records"
            if view == "history"
            else "RECORDED_DOMAIN_DECISIONS; inspect to recheck retained evidence"
        ),
    }


def case_groups(
    connection: Connection[Any], cte: str, params: dict[str, Any], view: str
) -> list[Any]:
    if view != "identity":
        query = """SELECT jsonb_build_object('provider',provider,'kind',kind,'status',status,
            'reason',reason,'country',NULL,'count',count(*)) FROM filtered
            GROUP BY provider,kind,status,reason
            ORDER BY count(*) DESC,provider,kind,status,reason LIMIT 101"""
    else:
        cte += """, scopes AS (
            SELECT DISTINCT 'team' AS kind,f.home_team_id AS canonical_id,
                            f.competition_id,m.season_id
            FROM football.product_fixtures f JOIN football.matches m ON m.id=f.fixture_id
            UNION SELECT DISTINCT 'team',f.away_team_id,f.competition_id,m.season_id
            FROM football.product_fixtures f JOIN football.matches m ON m.id=f.fixture_id
            UNION SELECT DISTINCT 'competition',f.competition_id,f.competition_id,m.season_id
            FROM football.product_fixtures f JOIN football.matches m ON m.id=f.fixture_id
        ) """
        query = """SELECT jsonb_build_object('provider',f.provider,'kind',f.kind,'status',f.status,
            'reason',f.reason,'country',f.country,'competition_id',s.competition_id,
            'season_id',s.season_id,'count',count(*)) FROM filtered f LEFT JOIN scopes s
            ON s.kind=f.kind AND s.canonical_id=f.canonical_id
            GROUP BY f.provider,f.kind,f.status,f.reason,f.country,s.competition_id,s.season_id
            ORDER BY count(*) DESC,f.provider,f.kind,f.status,f.reason,f.country,
                     s.competition_id,s.season_id
            LIMIT 101"""
    return [row[0] for row in connection.execute(cte + query, params)]


def fixture_detail(connection: Connection[Any], key: str) -> dict[str, Any]:
    _, provider, identifier = key.split(":", 2)
    row = connection.execute(
        """SELECT to_jsonb(d) FROM football.product_provider_mapping_decisions d
           WHERE provider_code=%s AND provider_match_id=%s AND created_at<=transaction_timestamp()
           ORDER BY observed_at DESC,decision_id DESC LIMIT 1""",
        (provider, identifier),
    ).fetchone()
    if row is None:
        raise ValueError("fixture identity case not found")
    observation = connection.execute(
        """SELECT to_jsonb(o) FROM football.product_provider_fixture_observations o
           WHERE provider_code=%s AND provider_match_id=%s AND observed_at<=transaction_timestamp()
           ORDER BY observed_at DESC,observation_id DESC LIMIT 1""",
        (provider, identifier),
    ).fetchone()
    return {
        "case_key": key,
        "status": row[0]["disposition"],
        "decision": row[0],
        "observation": observation[0] if observation else None,
        "proposed_action": "Review native IDs and fixture context before choosing a target.",
    }


def fixture_record_detail(connection: Connection[Any], key: str) -> dict[str, Any]:
    identifier = UUID(key.split(":", 1)[1])
    fixture = connection.execute(
        "SELECT to_jsonb(f) FROM football.product_fixtures f WHERE fixture_id=%s", (identifier,)
    ).fetchone()
    if fixture is None:
        raise ValueError("fixture record not found")
    sources = connection.execute(
        """SELECT to_jsonb(m)||jsonb_build_object('provider',p.code)
           FROM football.match_provider_mappings m JOIN football.providers p ON p.id=m.provider_id
           WHERE m.match_id=%s ORDER BY m.id""",
        (identifier,),
    ).fetchall()
    resolutions = connection.execute(
        """SELECT to_jsonb(r) FROM football.fixture_identity_resolutions r
           WHERE member_fixture_id=%s ORDER BY created_at,resolution_version""",
        (identifier,),
    ).fetchall()
    dependencies = connection.execute(
        """SELECT count(*) FROM football.product_forecasts WHERE fixture_id=%s""", (identifier,)
    ).fetchone()
    return {
        "case_key": key,
        "status": fixture[0]["identity_status"],
        "fixture": fixture[0],
        "source_mappings": [row[0] for row in sources],
        "resolutions": [row[0] for row in resolutions],
        "published_forecasts": dependencies[0] if dependencies else 0,
        "proposed_action": "Review teams, competition, season and source before merging.",
    }


def case_detail(
    connection: Connection[Any],
    root: Path,
    key: str,
    verifier: RetainedIdentityVerifier | None = None,
) -> dict[str, Any]:
    kind = key.split(":", 1)[0]
    if kind in {"team", "competition"}:
        result = mapping_detail(
            connection,
            root,
            cast(Literal["team", "competition"], kind),
            UUID(key.split(":", 1)[1]),
            verifier,
        )
    elif kind == "fixture":
        result = fixture_detail(connection, key)
    elif kind == "fixture_record":
        result = fixture_record_detail(connection, key)
    elif kind in {"resource", "dataset"}:
        result = data_detail(connection, root, key)
    elif kind in {"stage", "parity"}:
        from football.product.resolution_migration import migration_detail

        result = migration_detail(connection, Path.cwd(), key)
    else:
        raise ValueError("unsupported resolution case")
    result["recovery_work"] = recovery_work(connection, key)
    result["parity_work"] = parity_work(connection, key)
    if kind in {"resource", "dataset"}:
        result["file_recovery_work"] = file_recovery_work(connection, key)
    result["downstream_work"] = downstream_progress(connection, key)
    result.pop("evidence_version", None)
    review = latest_review(connection, key)
    result["latest_review"] = {k: v for k, v in review.items() if k != "detail"} if review else None
    result["evidence_version"] = sha256_json(result)
    return result


def latest_review(connection: Connection[Any], key: str) -> dict[str, Any] | None:
    if not review_ready(connection):
        return None
    row = connection.execute(
        """SELECT to_jsonb(e) FROM football.resolution_review_events e WHERE case_key=%s
           ORDER BY recorded_at DESC,event_id DESC LIMIT 1""",
        (key,),
    ).fetchone()
    return cast(dict[str, Any], row[0]) if row else None


def parity_work(connection: Connection[Any], key: str) -> list[dict[str, Any]]:
    ready = connection.execute("SELECT to_regclass('football.resolution_parity_work')").fetchone()
    if not ready or not ready[0]:
        return []
    return [
        row[0]
        for row in connection.execute(
            """SELECT jsonb_build_object('work_id',w.work_id,'state',w.state,
        'requested_at',w.requested_at,'finished_at',w.finished_at,
        'error',w.last_error_message,'report_sha256',b.outcome->>'report_sha256',
        'parity_status',b.outcome->'report'->>'status',
        'next_action','Inspect Migration Parity for exact checks and retained discrepancies')
        FROM football.resolution_parity_work b JOIN football.work_items w USING(work_id)
        JOIN football.resolution_review_events e USING(request_id)
        WHERE e.case_key=%s ORDER BY w.requested_at DESC,w.work_id DESC LIMIT 20""",
            (key,),
        )
    ]


def file_recovery_work(connection: Connection[Any], key: str) -> list[dict[str, Any]]:
    ready = connection.execute(
        "SELECT to_regclass('football.resolution_file_recovery_work')"
    ).fetchone()
    if not ready or not ready[0]:
        return []
    return [
        row[0]
        for row in connection.execute(
            """SELECT jsonb_build_object('work_id',w.work_id,'state',w.state,
           'request_id',b.request_id,'attempt_count',w.attempt_count,
           'error_code',w.last_error_code,'error',w.last_error_message,'outcome',b.outcome,
           'plan',b.plan,'total_attempts',count(*) OVER())
           FROM football.resolution_file_recovery_work b JOIN football.work_items w USING(work_id)
           JOIN football.resolution_review_events e ON e.request_id=b.request_id
           WHERE e.case_key=%s ORDER BY w.requested_at DESC,w.work_id DESC LIMIT 100""",
            (key,),
        )
    ]


def append_event(
    connection: Connection[Any],
    request: dict[str, Any],
    actor: str,
    request_hash: str,
    detail: dict[str, Any],
) -> dict[str, Any]:
    row = connection.execute(
        """INSERT INTO football.resolution_review_events
           (request_id,case_key,action,actor,reason,evidence_version,request_sha256,detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING to_jsonb(resolution_review_events)""",
        (
            request["request_id"],
            request["case_key"],
            request["action"],
            actor,
            request["reason"],
            request["evidence_version"],
            request_hash,
            Jsonb(detail),
        ),
    ).fetchone()
    assert row is not None
    return cast(dict[str, Any], row[0])


def review_ready(connection: Connection[Any]) -> bool:
    row = connection.execute("SELECT to_regclass('football.resolution_review_events')").fetchone()
    return bool(row and row[0])


def recovery_work(connection: Connection[Any], key: str) -> list[dict[str, Any]]:
    exists = connection.execute(
        "SELECT to_regclass('football.resolution_recovery_work')"
    ).fetchone()
    if not exists or not exists[0]:
        return []
    return [
        row[0]
        for row in connection.execute(
            """SELECT jsonb_build_object('work_id',w.work_id,'state',w.state,
           'request_id',b.request_id,'attempt_count',w.attempt_count,
           'error_code',w.last_error_code,'outcome',b.outcome,'total_pages',count(*) OVER())
           FROM football.resolution_recovery_work b JOIN football.work_items w USING(work_id)
           JOIN football.resolution_review_events e ON e.request_id=b.request_id
           WHERE e.case_key=%s ORDER BY w.requested_at DESC,w.work_id DESC LIMIT 100""",
            (key,),
        )
    ]


def downstream_progress(connection: Connection[Any], key: str) -> dict[str, Any]:
    exists = connection.execute(
        "SELECT to_regclass('football.resolution_recovery_work')"
    ).fetchone()
    if not exists or not exists[0]:
        return {"status": "NOT_REQUESTED"}
    row = connection.execute(
        """WITH latest AS (
            SELECT request_id FROM football.resolution_review_events e WHERE case_key=%s
              AND EXISTS (SELECT 1 FROM football.resolution_recovery_work b
                          WHERE b.request_id=e.request_id)
            ORDER BY recorded_at DESC,event_id DESC LIMIT 1
        ), scopes AS (
            SELECT target_id AS fixture_id FROM football.resolution_recovery_targets
            WHERE request_id IN(SELECT request_id FROM latest) AND target_kind='FIXTURE'
            UNION SELECT (result->>'fixture_id')::uuid FROM football.resolution_recovery_results
            WHERE request_id IN(SELECT request_id FROM latest) AND result->>'fixture_id' IS NOT NULL
        ) SELECT jsonb_build_object(
            'recovery_pending',(SELECT count(*) FROM football.resolution_recovery_work b
                JOIN football.work_items w USING(work_id) WHERE b.request_id=latest.request_id
                AND w.state IN('PENDING','RUNNING','RETRY_WAIT')),
            'recovery_blocked',(SELECT count(*) FROM football.resolution_recovery_work b
                JOIN football.work_items w USING(work_id) WHERE b.request_id=latest.request_id
                AND w.state IN('BLOCKED','FAILED','CANCELLED')),
            'blocked_targets',(SELECT count(*) FROM football.resolution_recovery_results
                WHERE request_id=latest.request_id AND result->>'status'='BLOCKED'),
            'forecast_pending',(SELECT count(*) FROM football.product_forecast_refresh_work
                WHERE fixture_id IN(SELECT fixture_id FROM scopes)
                  AND generation>completed_generation),
            'context_pending',(SELECT count(*) FROM football.product_context_report_refresh_work
                WHERE fixture_id IN(SELECT fixture_id FROM scopes)
                  AND generation>completed_generation),
            'report_pending',(SELECT count(*) FROM football.product_report_refresh_work
                WHERE generation>completed_generation AND
                  ((report_kind='PERFORMANCE' AND scope_id IN(SELECT competition_id
                    FROM football.product_fixtures
                    WHERE fixture_id IN(SELECT fixture_id FROM scopes)))
                  OR (report_kind='COMPARISON' AND scope_id IN(SELECT prediction_id
                    FROM football.external_prediction_effective
                    WHERE effective_fixture_id IN(SELECT fixture_id FROM scopes))))),
            'external_pending',(SELECT count(*) FROM football.external_prediction_refresh_work
                WHERE generation>completed_generation AND prediction_id IN(SELECT prediction_id
                    FROM football.external_prediction_effective
                    WHERE effective_fixture_id IN(SELECT fixture_id FROM scopes)))
        ) FROM latest""",
        (key,),
    ).fetchone()
    if row is None:
        return {"status": "NOT_REQUESTED"}
    result = cast(dict[str, Any], row[0])
    result["status"] = (
        "BLOCKED"
        if result["blocked_targets"] or result["recovery_blocked"]
        else (
            "PENDING"
            if any(
                result[name]
                for name in (
                    "recovery_pending",
                    "forecast_pending",
                    "context_pending",
                    "report_pending",
                    "external_pending",
                )
            )
            else "NO_PENDING_WORK_IN_AFFECTED_SCOPES"
        )
    )
    result["scope"] = "Latest recovery request; shared generations may include later requests"
    return result
