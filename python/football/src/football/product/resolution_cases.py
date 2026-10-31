"""Read-only, paginated operational cases over the existing domain owners."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

from psycopg import Connection

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
    country_value = "country" if view == "identity" else "NULL"
    country_group = ",country" if view == "identity" else ""
    groups = [
        row[0]
        for row in connection.execute(
            cte + "SELECT jsonb_build_object('provider',provider,'kind',kind,'status',status,"
            "'reason',reason,'country'," + country_value + ",'count',count(*)) FROM filtered "
            "GROUP BY provider,kind,status,reason" + country_group + " "
            "ORDER BY count(*) DESC,provider,kind,status,reason LIMIT 101",
            params,
        )
    ]
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
    else:
        raise ValueError("unsupported resolution case")
    result.pop("evidence_version", None)
    result["evidence_version"] = sha256_json(result)
    return result
