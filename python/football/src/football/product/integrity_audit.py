"""Read-only, resumable integrity audit of canonical results, history and served form.

The audit never writes to the database. Each run reads in REPEATABLE READ READ
ONLY transactions, keeps a checkpoint and per-record findings under an output
directory, and stops at a batch boundary when its time limit is reached. A
later run with the same output directory resumes after the last finished batch
and keeps the original watermark, so rows changed after the scan started are
counted against the same frozen population rather than silently verified.

Form is recomputed independently of public_context_source_v2: official results
are read from product_fixtures here and qualified history from the existing
public_context_source, then passed to the same form-policy-v1 engine. Integration
tests prove the two paths select the same inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from football.product.form import (
    DEFAULT_WINDOW,
    FORM_POLICY_VERSION,
    STALE_AFTER,
    competition_scope,
    team_form,
)

AUDIT_VERSION = "p02-integrity-audit-v3"
BATCH_SIZE = 500
RUN_LIMIT_SECONDS = 30 * 60
UNRESOLVED = ("SCHEDULED", "LIVE", "HALF_TIME", "SUSPENDED", "INTERRUPTED")
NOT_AUDITED_DOMAINS = (
    "standings",
    "h2h_correctness",
    "team_statistics_beyond_form",
    "live_events",
    "lineups",
    "availability",
)

_OFFICIAL = """
    SELECT DISTINCT ON (pf.fixture_id) pf.fixture_id::text, pf.competition_id::text,
           pf.home_team_id::text, pf.away_team_id::text, pf.kickoff_at, pf.status,
           pf.home_score AS home_goals, pf.away_score AS away_goals,
           pf.result_score_basis AS score_basis, home.name AS home_team, away.name AS away_team
    FROM unnest(%(teams)s::uuid[]) AS team(team_id)
    CROSS JOIN LATERAL (
        SELECT side.* FROM (
            (SELECT f.* FROM football.product_fixtures f
             WHERE f.home_team_id = team.team_id AND f.kickoff_at < %(kickoff)s
               AND f.status IN ('FINISHED','AWARDED') AND f.home_score IS NOT NULL
               AND f.identity_status = 'VERIFIED' AND f.updated_at <= %(cutoff)s
             ORDER BY f.kickoff_at DESC, f.fixture_id LIMIT 30)
            UNION ALL
            (SELECT f.* FROM football.product_fixtures f
             WHERE f.away_team_id = team.team_id AND f.kickoff_at < %(kickoff)s
               AND f.status IN ('FINISHED','AWARDED') AND f.home_score IS NOT NULL
               AND f.identity_status = 'VERIFIED' AND f.updated_at <= %(cutoff)s
             ORDER BY f.kickoff_at DESC, f.fixture_id LIMIT 30)
        ) side ORDER BY side.kickoff_at DESC, side.fixture_id LIMIT 30
    ) pf
    JOIN football.product_teams home ON home.team_id = pf.home_team_id
    JOIN football.product_teams away ON away.team_id = pf.away_team_id
    WHERE pf.fixture_id <> %(fixture)s AND NOT EXISTS (
        SELECT 1 FROM football.fixture_identity_resolutions r
        WHERE r.member_fixture_id = pf.fixture_id AND r.active
          AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
               OR r.representative_fixture_id <> pf.fixture_id))
    ORDER BY pf.fixture_id
"""

_PENDING = """
    SELECT team.team_id::text, p.fixture_id::text, p.kickoff_at, p.status
    FROM unnest(%(teams)s::uuid[]) AS team(team_id)
    CROSS JOIN LATERAL (
        SELECT f.fixture_id, f.kickoff_at, f.status FROM football.product_fixtures f
        WHERE (f.home_team_id = team.team_id OR f.away_team_id = team.team_id)
          AND f.fixture_id <> %(fixture)s AND f.kickoff_at < %(kickoff)s
          AND f.kickoff_at >= %(kickoff)s - interval '400 days'
          AND f.identity_status = 'VERIFIED' AND f.updated_at <= %(cutoff)s
          AND (f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED')
               OR (f.status = 'AWARDED' AND f.home_score IS NULL))
        ORDER BY f.kickoff_at DESC, f.fixture_id LIMIT 10
    ) p
"""


def _iso(value: Any) -> Any:
    return value.astimezone(UTC).isoformat() if isinstance(value, datetime) else value


def _row(item: dict[str, Any]) -> dict[str, Any]:
    return {key: _iso(value) for key, value in item.items()}


def official_inputs(
    connection: Connection[Any], source: dict[str, Any], cutoff: datetime
) -> dict[str, Any]:
    """Build the form-policy-v1 additions to a v1 context source from base tables."""
    params = {
        "teams": [source["home_team_id"], source["away_team_id"]],
        "kickoff": datetime.fromisoformat(source["kickoff_at"]),
        "cutoff": cutoff,
        "fixture": source["fixture_id"],
    }
    with connection.cursor(row_factory=dict_row) as cursor:
        results = [_row(item) for item in cursor.execute(_OFFICIAL, params).fetchall()]
        pending = [_row(item) for item in cursor.execute(_PENDING, params).fetchall()]
        ids = {source["competition_id"]}
        ids |= {row["competition_id"] for row in results}
        ids |= {row["competition_id"] for row in source["history"]}
        scopes = {
            str(item["competition_id"]): competition_scope(item["competition_type"], item["name"])
            for item in cursor.execute(
                "SELECT competition_id,competition_type,name FROM football.product_competitions "
                "WHERE competition_id=ANY(%s::uuid[])",
                (sorted(ids),),
            ).fetchall()
        }
    return {
        **source,
        "results": sorted(results, key=lambda row: (row["kickoff_at"], row["fixture_id"])),
        "pending_results": pending,
        "competition_scopes": scopes,
        "form_policy_version": FORM_POLICY_VERSION,
    }


def _traceable(served: list[dict[str, Any]], history: list[dict[str, Any]], team: str) -> bool:
    """Every served symbol matches one qualified history row from the team's side."""
    keys = set()
    for row in history:
        home = row["home_team_id"] == team
        if team not in (row["home_team_id"], row["away_team_id"]):
            continue
        gf, ga = (
            (row["home_goals"], row["away_goals"])
            if home
            else (row["away_goals"], row["home_goals"])
        )
        keys.add((datetime.fromisoformat(row["kickoff_at"]), "HOME" if home else "AWAY", gf, ga))
    return all(
        (
            datetime.fromisoformat(match["kickoff_at"].replace("Z", "+00:00")),
            match["venue"],
            match["goals_for"],
            match["goals_against"],
        )
        in keys
        for match in served
    )


def classify_side(
    served: list[dict[str, Any]] | None,
    report_current: bool,
    source: dict[str, Any],
    team: str,
    *,
    official_report: bool = False,
) -> dict[str, Any]:
    """Compare served form with the governed recomputation for one team.

    A v1 report serves forecast-eligible history only, so its symbols must trace
    to history. A form-policy report serves official results, which may include
    awarded or not yet eligible rows, so those also count as a valid trace.
    """
    trace_rows = source["history"] + (source["results"] if official_report else [])
    window = team_form(source, team)["windows"][DEFAULT_WINDOW]
    kickoff = datetime.fromisoformat(source["kickoff_at"])
    served_text = "".join(row["result"] for row in served) if served is not None else None
    served_old = bool(
        served
        and kickoff - datetime.fromisoformat(served[-1]["kickoff_at"].replace("Z", "+00:00"))
        > STALE_AFTER
    )
    if served is None:
        state = "NO_REPORT"
    elif served_text == window["results"]:
        state = "MATCHING"
    elif not report_current:
        state = "DIVERGENT_STALE_REPORT"
    elif {"UNQUALIFIED_RESULT", "AWARDED_INCLUDED"} & set(window["flags"]):
        state = "DIVERGENT_POLICY_OR_UNQUALIFIED"
    else:
        state = "DIVERGENT_OTHER"
    return {
        "state": state,
        "served": served_text,
        "served_traceable": None if served is None else _traceable(served, trace_rows, team),
        "served_older_than_stale_limit": served_old,
        "recomputed": window["results"],
        "coverage": window["coverage"],
        "flags": window["flags"],
        "fixture_ids": window["fixture_ids"],
    }


def _audit_fixture(
    connection: Connection[Any], fixture_id: UUID, watermark: datetime
) -> dict[str, Any] | None:
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            """SELECT source,encode(sha256(convert_to(source::text,'UTF8')),'hex') AS fingerprint
               FROM (SELECT football.public_context_source(%s) AS source) s""",
            (fixture_id,),
        ).fetchone()
        if row is None or row["source"] is None:
            return None
        report = cursor.execute(
            """SELECT record_bytes, source_fingerprint FROM football.product_read_reports
               WHERE report_kind='CONTEXT' AND scope_id=%s AND horizon='LATEST'
                 AND registered_at<=%s
               ORDER BY source_observed_at DESC,registered_at DESC,input_sha256 LIMIT 1""",
            (fixture_id, watermark),
        ).fetchone()
        cutoff = cursor.execute(
            "SELECT LEAST(%s::timestamptz,statement_timestamp())",
            (row["source"]["kickoff_at"],),
        ).fetchone()
        # After the form-policy migration the API serves a report built from the
        # v2 source, falling back to a current v1 report until it is rebuilt.
        v2 = cursor.execute(
            """SELECT CASE WHEN to_regprocedure('football.public_context_source_v2(uuid)') IS NULL
                      THEN NULL ELSE encode(sha256(convert_to(
                          football.public_context_source_v2(%s)::text,'UTF8')),'hex') END AS fp""",
            (fixture_id,),
        ).fetchone()
    assert cutoff is not None and v2 is not None
    source = official_inputs(connection, row["source"], next(iter(cutoff.values())))
    served = json.loads(bytes(report["record_bytes"])) if report else None
    fingerprint = report["source_fingerprint"] if report else None
    report_source = (
        "v2"
        if fingerprint is not None and fingerprint == v2["fp"]
        else "v1"
        if fingerprint is not None and fingerprint == row["fingerprint"]
        else None
    )
    current = report_source is not None
    official = report_source == "v2"
    return {
        "fixture_id": str(fixture_id),
        "report_current": current,
        "report_source": report_source,
        "home": classify_side(
            served["home_form"] if served else None,
            current,
            source,
            source["home_team_id"],
            official_report=official,
        ),
        "away": classify_side(
            served["away_form"] if served else None,
            current,
            source,
            source["away_team_id"],
            official_report=official,
        ),
    }


def _scope_labels(
    connection: Connection[Any], fixtures: Sequence[UUID]
) -> dict[str, tuple[Any, ...]]:
    rows = connection.execute(
        """SELECT f.fixture_id::text, COALESCE(p.code,'(none)'), c.country, c.name, c.season_label
           FROM football.product_fixtures f
           JOIN football.product_competitions c USING (competition_id)
           LEFT JOIN LATERAL (
               SELECT p.code FROM football.match_provider_mappings m
               JOIN football.providers p ON p.id=m.provider_id
               WHERE m.match_id=f.fixture_id AND m.valid_to IS NULL
               ORDER BY m.created_at,m.id LIMIT 1) p ON true
           WHERE f.fixture_id=ANY(%s)""",
        (list(fixtures),),
    ).fetchall()
    return {row[0]: row[1:] for row in rows}


def corpus_checks(connection: Connection[Any]) -> dict[str, Any]:
    """Whole-table checks that are cheap enough to run on every audit."""
    rows = connection.execute(
        """SELECT COALESCE(p.code,'(none)'), f.status, f.result_score_basis,
                  count(*) AS total,
                  count(*) FILTER (WHERE f.status='FINISHED' AND f.home_score IS NOT NULL
                                   AND h.fixture_id IS NULL) AS finished_without_history,
                  count(*) FILTER (WHERE f.status = ANY(%s)
                                   AND f.kickoff_at < statement_timestamp()-interval '4 hours')
                      AS result_overdue,
                  count(*) FILTER (WHERE h.fixture_id IS NOT NULL
                      AND (f.home_score,f.away_score) IS DISTINCT FROM (h.home_goals,h.away_goals))
                      AS history_score_mismatch,
                  count(*) FILTER (WHERE h.fixture_id IS NOT NULL AND f.status<>'FINISHED')
                      AS history_on_unfinished,
                  count(*) FILTER (WHERE f.identity_status<>'VERIFIED') AS identity_unverified
           FROM football.product_fixtures f
           LEFT JOIN football.product_team_match_history h USING (fixture_id)
           LEFT JOIN LATERAL (
               SELECT p.code FROM football.match_provider_mappings m
               JOIN football.providers p ON p.id=m.provider_id
               WHERE m.match_id=f.fixture_id AND m.valid_to IS NULL
               ORDER BY m.created_at,m.id LIMIT 1) p ON true
           GROUP BY 1,2,3 ORDER BY 1,2,3""",
        (list(UNRESOLVED),),
    ).fetchall()
    keys = (
        "provider",
        "status",
        "score_basis",
        "total",
        "finished_without_history",
        "result_overdue",
        "history_score_mismatch",
        "history_on_unfinished",
        "identity_unverified",
    )
    conflicts = connection.execute(
        """SELECT (SELECT count(*) FROM football.product_source_result_conflicts),
                  (SELECT count(*) FROM football.fixture_identity_ingestion_conflicts),
                  (SELECT count(*) FROM football.product_context_report_refresh_work
                   WHERE generation>completed_generation)"""
    ).fetchone()
    assert conflicts is not None
    return {
        "fixtures_by_provider_status_basis": [dict(zip(keys, row, strict=True)) for row in rows],
        "provider_result_conflicts": conflicts[0],
        "fixture_identity_ingestion_conflicts": conflicts[1],
        "context_refresh_pending": conflicts[2],
        "not_audited": list(NOT_AUDITED_DOMAINS),
    }


_PAIRINGS = """
WITH league_fixtures AS (
    SELECT f.competition_id, m.season_id, f.home_team_id, f.away_team_id, f.status, f.kickoff_at
    FROM football.product_fixtures f
    JOIN football.matches m ON m.id = f.fixture_id
    JOIN football.product_competitions c ON c.competition_id = f.competition_id
    WHERE c.competition_type = 'LEAGUE' AND f.identity_status = 'VERIFIED'
      AND f.status <> 'CANCELLED'
), teams AS (
    SELECT DISTINCT competition_id, season_id, team_id
    FROM league_fixtures, LATERAL unnest(ARRAY[home_team_id, away_team_id]) team_id
), seasons AS (
    SELECT f.competition_id, f.season_id, count(*) AS fixtures,
           count(DISTINCT (f.home_team_id, f.away_team_id)) AS present_pairs,
           max(f.kickoff_at) AS last_kickoff, min(f.kickoff_at) AS first_kickoff,
           (SELECT count(*) FROM teams t WHERE (t.competition_id, t.season_id)
                = (f.competition_id, f.season_id)) AS teams
    FROM league_fixtures f GROUP BY 1, 2
)
SELECT s.competition_id::text, s.season_id::text, c.country, c.name, s.teams, s.fixtures,
       s.present_pairs, s.first_kickoff, s.last_kickoff,
       CASE WHEN s.teams BETWEEN 4 AND 30 AND s.present_pairs < s.teams * (s.teams - 1)
                 AND s.present_pairs >= 0.8 * s.teams * (s.teams - 1)
            THEN (SELECT jsonb_agg(jsonb_build_array(a.team_id, b.team_id)
                                   ORDER BY a.team_id, b.team_id)
                  FROM teams a JOIN teams b USING (competition_id, season_id)
                  WHERE (a.competition_id, a.season_id) = (s.competition_id, s.season_id)
                    AND a.team_id <> b.team_id AND NOT EXISTS (
                        SELECT 1 FROM league_fixtures f
                        WHERE (f.competition_id, f.season_id) = (s.competition_id, s.season_id)
                          AND f.home_team_id = a.team_id AND f.away_team_id = b.team_id))
       END AS missing_pairs
FROM seasons s JOIN football.product_competitions c USING (competition_id)
ORDER BY 1, 2
"""


def league_coverage(connection: Connection[Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Classify each league season by its home/away pairings.

    A double round robin with n teams has n(n-1) ordered pairings. Seasons with
    at least 80% of them get their absent pairings listed as candidate missing
    matches; sparser seasons are partial coverage. Leagues with splits, groups
    or extra rounds can make an absent pairing legitimate, so these are
    candidates for source checks, not proven defects.
    """
    records = []
    counts: Counter[str] = Counter()
    by_country: dict[str, Counter[str]] = defaultdict(Counter)
    for row in connection.execute(_PAIRINGS).fetchall():
        competition, season, country, name, teams, fixtures, present, first, last, missing = row
        expected = teams * (teams - 1)
        if teams < 4 or teams > 30:
            state = "UNSUPPORTED_SIZE"
        elif present >= expected:
            state = "COMPLETE_PAIRINGS"
        elif missing is not None:
            state = "CANDIDATE_MISSING_MATCHES"
        else:
            state = "PARTIAL_COVERAGE"
        counts[state] += 1
        counts["missing_pairings"] += expected - present if state != "UNSUPPORTED_SIZE" else 0
        counts["candidate_missing_matches"] += len(missing or ())
        by_country[country][state] += 1
        records.append(
            {
                "competition_id": competition,
                "season_id": season,
                "competition": f"{country} / {name}",
                "state": state,
                "teams": teams,
                "fixtures": fixtures,
                "present_pairings": present,
                "expected_pairings": expected,
                "first_kickoff_at": _iso(first),
                "last_kickoff_at": _iso(last),
                "missing_pairings": missing or [],
            }
        )
    summary = {
        "league_seasons": len(records),
        **dict(sorted(counts.items())),
        "by_country": {key: dict(value) for key, value in sorted(by_country.items())},
    }
    return summary, records


def affected_forecasts(connection: Connection[Any], decided_from: datetime) -> list[dict[str, Any]]:
    """Forecasts whose inputs lacked results that a later re-qualification admitted.

    A forecast is affected only when the newly qualified result was already in a
    retained source response before the forecast's knowledge cutoff
    (source_known_at <= knowledge_cutoff), kicked off before the forecast
    fixture, and involved one of its teams. Results first acquired after the
    cutoff were legitimately unknown and do not count.
    """
    rows = connection.execute(
        """WITH admitted AS (
               SELECT DISTINCT ON (d.fixture_id) d.*
               FROM football.product_match_history_decisions d
               WHERE d.decided_at >= %s AND d.eligible
               ORDER BY d.fixture_id, d.decided_at, d.decision_id)
           SELECT f.forecast_id::text, f.fixture_id::text, f.created_at, f.knowledge_cutoff,
                  f.model_label, count(*) AS missing_results,
                  count(*) FILTER (WHERE a.kickoff_at >= t.kickoff_at - interval '120 days')
                      AS missing_within_120_days,
                  array_agg(a.fixture_id::text ORDER BY a.kickoff_at DESC, a.fixture_id)
           FROM football.product_forecasts f
           JOIN football.product_fixtures t ON t.fixture_id = f.fixture_id
           JOIN admitted a ON a.source_known_at <= f.knowledge_cutoff
             AND a.kickoff_at < t.kickoff_at AND a.fixture_id <> t.fixture_id
             AND (a.home_team_id IN (t.home_team_id, t.away_team_id)
                  OR a.away_team_id IN (t.home_team_id, t.away_team_id))
           GROUP BY f.forecast_id, f.fixture_id, f.created_at, f.knowledge_cutoff, f.model_label
           ORDER BY f.created_at, f.forecast_id""",
        (decided_from,),
    ).fetchall()
    keys = (
        "forecast_id",
        "fixture_id",
        "created_at",
        "knowledge_cutoff",
        "model_label",
        "missing_results",
        "missing_within_120_days",
        "missing_fixture_ids",
    )
    return [{key: _iso(value) for key, value in zip(keys, row, strict=True)} for row in rows]


def incremental_findings(connection: Connection[Any], since: datetime) -> dict[str, int]:
    """Cheap checks over fixtures changed since a time; the scheduled job runs these."""
    row = connection.execute(
        """SELECT
             count(*) FILTER (WHERE f.status='FINISHED' AND f.result_score_basis='REGULATION_90'
                 AND f.home_score IS NOT NULL AND h.fixture_id IS NULL
                 AND f.updated_at < statement_timestamp()-interval '15 minutes'
                 AND EXISTS (SELECT 1 FROM football.match_provider_mappings m
                     JOIN football.providers p ON p.id=m.provider_id
                     WHERE m.match_id=f.fixture_id AND m.valid_to IS NULL
                       AND p.code='api_football')),
             count(*) FILTER (WHERE f.status = ANY(%s)
                 AND f.kickoff_at < statement_timestamp()-interval '4 hours'),
             count(*) FILTER (WHERE h.fixture_id IS NOT NULL
                 AND (f.home_score,f.away_score) IS DISTINCT FROM (h.home_goals,h.away_goals))
           FROM football.product_fixtures f
           LEFT JOIN football.product_team_match_history h USING (fixture_id)
           WHERE f.updated_at >= %s""",
        (list(UNRESOLVED), since),
    ).fetchone()
    stale = connection.execute(
        """SELECT count(*) FROM football.product_context_report_refresh_work
           WHERE generation>completed_generation
             AND requested_at < statement_timestamp()-interval '1 hour'"""
    ).fetchone()
    assert row is not None and stale is not None
    return {
        "finished_without_history": row[0],
        "result_overdue": row[1],
        "history_score_mismatch": row[2],
        "context_refresh_older_than_1h": stale[0],
    }


class AuditRun:
    """Checkpointed batches under one output directory."""

    def __init__(self, out: Path) -> None:
        self.out = out
        self.state_path = out / "checkpoint.json"
        self.findings_path = out / "findings.jsonl"

    def load(self, connection: Connection[Any]) -> dict[str, Any]:
        if self.state_path.exists():
            state: dict[str, Any] = json.loads(self.state_path.read_text())
            if state["audit_version"] != AUDIT_VERSION:
                raise ValueError("checkpoint was written by another audit version")
            return state
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            watermark = connection.execute("SELECT statement_timestamp()").fetchone()
            assert watermark is not None
            population = connection.execute(
                """SELECT count(DISTINCT scope_id), md5(string_agg(DISTINCT scope_id::text, ','
                       ORDER BY scope_id::text))
                   FROM football.product_read_reports
                   WHERE report_kind='CONTEXT' AND registered_at<=%s""",
                (watermark[0],),
            ).fetchone()
            assert population is not None
            corpus = corpus_checks(connection)
            corpus["league_coverage"], coverage = league_coverage(connection)
        self.out.mkdir(parents=True, exist_ok=True)
        with (self.out / "league_coverage.jsonl").open("w", encoding="utf-8") as handle:
            for record in coverage:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        state = {
            "audit_version": AUDIT_VERSION,
            "form_policy_version": FORM_POLICY_VERSION,
            "watermark": watermark[0].astimezone(UTC).isoformat(),
            "population": {"context_fixtures": population[0], "scope_id_md5": population[1]},
            "after_fixture_id": "00000000-0000-0000-0000-000000000000",
            "batches": 0,
            "audited": 0,
            "complete": False,
            "corpus": corpus,
        }
        self.save(state)
        return state

    def save(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True, indent=1))
        temporary.replace(self.state_path)

    def batch(self, connection: Connection[Any], state: dict[str, Any], size: int) -> int:
        watermark = datetime.fromisoformat(state["watermark"])
        with connection.transaction():
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            scopes = [
                row[0]
                for row in connection.execute(
                    """SELECT DISTINCT scope_id FROM football.product_read_reports
                       WHERE report_kind='CONTEXT' AND registered_at<=%s AND scope_id>%s
                       ORDER BY scope_id LIMIT %s""",
                    (watermark, state["after_fixture_id"], size),
                ).fetchall()
            ]
            labels = _scope_labels(connection, scopes)
            records = []
            for scope in scopes:
                record = _audit_fixture(connection, scope, watermark)
                if record is None:
                    record = {"fixture_id": str(scope), "state": "FIXTURE_MISSING"}
                record["scope"] = labels.get(str(scope))
                records.append(record)
        with self.findings_path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        if scopes:
            state["after_fixture_id"] = str(scopes[-1])
            state["batches"] += 1
            state["audited"] += len(scopes)
        state["complete"] = len(scopes) < size
        self.save(state)
        return len(scopes)


def summarize(out: Path) -> dict[str, Any]:
    """Aggregate per-record findings into the committed summary."""
    state = json.loads((out / "checkpoint.json").read_text())
    totals: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    by: dict[str, dict[str, Counter[str]]] = {
        "provider": defaultdict(Counter),
        "country": defaultdict(Counter),
        "competition_season": defaultdict(Counter),
    }
    digest = hashlib.sha256()
    findings = out / "findings.jsonl"
    lines = findings.read_text(encoding="utf-8").splitlines() if findings.exists() else []
    for line in lines:
        digest.update(line.encode() + b"\n")
        record = json.loads(line)
        scope = record.get("scope") or ["(unknown)", "(unknown)", "(unknown)", "(unknown)"]
        keys = {
            "provider": scope[0],
            "country": scope[1],
            "competition_season": f"{scope[1]} / {scope[2]} / {scope[3]}",
        }
        for side in ("home", "away"):
            if side not in record:
                totals["fixture_missing"] += 1
                continue
            item = record[side]
            totals["sides"] += 1
            totals[item["state"]] += 1
            totals[f"coverage_{item['coverage']}"] += 1
            totals["served_untraceable"] += item["served_traceable"] is False
            totals["served_older_than_stale_limit"] += item["served_older_than_stale_limit"]
            flags.update(item["flags"])
            for name, key in keys.items():
                by[name][key][item["state"]] += 1
                by[name][key]["sides"] += 1
        totals["fixtures"] += 1
        totals["report_current"] += bool(record.get("report_current"))
        if record.get("report_source"):
            totals[f"report_source_{record['report_source']}"] += 1
    return {
        "audit_version": AUDIT_VERSION,
        "form_policy_version": FORM_POLICY_VERSION,
        "watermark": state["watermark"],
        "population": state["population"],
        "audited_fixtures": state["audited"],
        "complete": state["complete"],
        "coverage_fraction": round(
            state["audited"] / max(1, state["population"]["context_fixtures"]), 6
        ),
        "findings_sha256": digest.hexdigest(),
        "findings_records": len(lines),
        "form_sides": dict(sorted(totals.items())),
        "default_window_flags": dict(sorted(flags.items())),
        "by_provider": {key: dict(value) for key, value in sorted(by["provider"].items())},
        "by_country": {key: dict(value) for key, value in sorted(by["country"].items())},
        "divergent_competition_seasons": {
            key: dict(value)
            for key, value in sorted(by["competition_season"].items())
            if value["sides"] != value["MATCHING"]
        },
        "corpus": state["corpus"],
    }


def run(
    database_url: str, out: Path, *, batch_size: int, time_limit: float, max_batches: int | None
) -> dict[str, Any]:
    started = time.monotonic()
    with psycopg.connect(database_url) as connection:
        connection.read_only = True
        audit = AuditRun(out)
        state = audit.load(connection)
        batches = 0
        while not state["complete"]:
            if time.monotonic() - started > time_limit:
                break
            if max_batches is not None and batches >= max_batches:
                break
            audit.batch(connection, state, batch_size)
            batches += 1
    summary = summarize(out)
    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=1))
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="read-only P02 integrity audit")
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--out", type=Path, required=True, help="checkpoint and findings directory")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--time-limit", type=float, default=RUN_LIMIT_SECONDS)
    parser.add_argument("--max-batches", type=int)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 5000:
        parser.error("--batch-size must be between 1 and 5000")
    summary = run(
        args.database_url,
        args.out,
        batch_size=args.batch_size,
        time_limit=args.time_limit,
        max_batches=args.max_batches,
    )
    print(
        json.dumps(
            {key: summary[key] for key in ("audited_fixtures", "complete", "form_sides")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
