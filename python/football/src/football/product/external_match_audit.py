"""Read-only census of external prediction associations under the contextual policy.

The census writes nothing. It reports the current association of every retained
prediction, what EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1 would decide, and how
the policy agrees with independently verified native-ID bindings.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.external_prediction_association import (
    SOURCE_FACTS,
    load_candidates,
    load_countries,
    source_prediction,
)
from football.product.external_prediction_matching import (
    POLICY_VERSION,
    CandidateFixture,
    Decision,
    decide,
    search_window,
)
from football.product.external_prediction_recovery import source_date_review

CENSUS_FACTS = (
    SOURCE_FACTS.replace(
        "SELECT ep.prediction_id,",
        """SELECT ep.prediction_id,ep.collected_at,ep.original_date_text,eff.effective_match_status,
    eff.effective_fixture_id,eff.date_status,result.settlement_state,
    ep.provider_code IS NOT NULL OR EXISTS (
        SELECT 1 FROM football.external_prediction_fixture_evidence e
        WHERE e.prediction_id=ep.prediction_id
          AND (e.provider_code IS NOT NULL OR e.r2bet_match_id IS NOT NULL))
        AS native_reference,""",
    )
    + """JOIN football.external_prediction_effective eff USING (prediction_id)
LEFT JOIN football.external_prediction_latest_results result USING (prediction_id)
ORDER BY ep.prediction_date,ep.prediction_id"""
)

FIXTURE_OUTCOMES = """
SELECT fixture_id,kickoff_at,identity_status,status='FINISHED' AND home_score IS NOT NULL AS final
FROM football.product_fixtures WHERE fixture_id=ANY(%s)
"""


class _Catalogue:
    """All candidate fixtures for the census range, searchable by kickoff."""

    def __init__(self, fixtures: list[CandidateFixture]) -> None:
        entries = sorted(
            (kickoff, index)
            for index, fixture in enumerate(fixtures)
            for kickoff in (fixture.kickoff_at, *fixture.earlier_kickoffs)
        )
        self._fixtures = fixtures
        self._kickoffs = [kickoff for kickoff, _ in entries]
        self._indexes = [index for _, index in entries]

    def window(self, prediction_date: date) -> list[CandidateFixture]:
        start, end = (
            datetime.combine(day, time.min, UTC) for day in search_window(prediction_date)
        )
        found = self._indexes[
            bisect_left(self._kickoffs, start) : bisect_right(self._kickoffs, end)
        ]
        return [self._fixtures[index] for index in sorted(set(found))]


def census(connection: Connection[Any]) -> dict[str, Any]:
    """Classify every retained prediction; the caller owns the read-only transaction."""
    with connection.cursor(row_factory=dict_row) as cursor:
        rows = cursor.execute(CENSUS_FACTS).fetchall()
        if not rows:
            return {"policy_version": POLICY_VERSION, "total": 0, "predictions": []}
        countries = load_countries(cursor)
        first, _ = search_window(rows[0]["prediction_date"])
        _, last = search_window(rows[-1]["prediction_date"])
        catalogue = _Catalogue(load_candidates(cursor, first, last))
        records = [
            _record(
                row,
                decide(source_prediction(row), catalogue.window(row["prediction_date"]), countries),
            )
            for row in rows
        ]
        outcomes = _outcomes(cursor, records)
    for record in records:
        _attach_outcome(record, outcomes)
    summary = _summary(records)
    summary["calibration"]["negative_controls"] = _negative_controls(rows, catalogue, countries)
    return summary


def _negative_controls(
    rows: list[dict[str, Any]], catalogue: _Catalogue, countries: frozenset[str]
) -> dict[str, Any]:
    """Perturb each verified example; any automatic match is a false association."""
    verified = [row for row in rows if row["effective_match_status"] == "MATCHED"]
    teams = sorted({row["away_team_text"] for row in rows})
    results: Counter[str] = Counter()
    for index, row in enumerate(verified):
        source = source_prediction(row)
        other = teams[(teams.index(source.away_team) + 1 + index) % len(teams)]
        controls = {
            "reversed": replace(source, home_team=source.away_team, away_team=source.home_team),
            "date_plus_7": replace(source, prediction_date=source.prediction_date + timedelta(7)),
            "other_opponent": replace(source, away_team=other),
        }
        for name, control in controls.items():
            decision = decide(control, catalogue.window(control.prediction_date), countries)
            results[f"{name}:{decision.classification}"] += 1
    matched = sum(count for key, count in results.items() if key.endswith(":CONTEXTUAL_MATCH"))
    return {"controls": sum(results.values()), "false_associations": matched, **dict(results)}


def _record(row: dict[str, Any], decision: Decision) -> dict[str, Any]:
    verified = row["effective_match_status"] == "MATCHED" and row["effective_fixture_id"]
    representatives = {
        item.fixture.fixture_id: item.fixture.effective_fixture_id for item in decision.candidates
    }
    verified_fixture = (
        representatives.get(row["effective_fixture_id"], row["effective_fixture_id"])
        if verified
        else None
    )
    return {
        "prediction_id": str(row["prediction_id"]),
        "source_code": row["source_code"],
        "prediction_date": row["prediction_date"].isoformat(),
        "competition": row["competition_text"],
        "home_team": row["home_team_text"],
        "away_team": row["away_team_text"],
        "collected_at": row["collected_at"],
        "date_status": row["date_status"]
        if row["date_status"] != "UNKNOWN"
        else source_date_review(row)[1],
        "settlement_state": row["settlement_state"] or "UNSETTLED",
        "native_reference": row["native_reference"],
        "current": "VERIFIED" if verified else row["effective_match_status"],
        "verified_fixture_id": str(verified_fixture) if verified_fixture else None,
        "policy_classification": decision.classification,
        "policy_reason": decision.reason,
        "policy_fixture_id": str(decision.fixture_id) if decision.fixture_id else None,
        "date_relation": decision.evidence(source_prediction(row))["date_relation"],
        "candidate_count": len({item.fixture.effective_fixture_id for item in decision.candidates}),
        "candidate_dates": sorted({str(item.date) for item in decision.candidates}),
    }


def _outcomes(cursor: Any, records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    ids = {UUID(r["policy_fixture_id"]) for r in records if r["policy_fixture_id"]}
    rows = cursor.execute(FIXTURE_OUTCOMES, (list(ids),)).fetchall()
    return {str(row["fixture_id"]): row for row in rows}


def _attach_outcome(record: dict[str, Any], outcomes: dict[str, dict[str, Any]]) -> None:
    """Final classification and the external-only eligibility it would allow."""
    record["classification"] = (
        "VERIFIED" if record["current"] == "VERIFIED" else record["policy_classification"]
    )
    outcome = outcomes.get(record["policy_fixture_id"] or "")
    contextual = record["classification"] == "CONTEXTUAL_MATCH" and outcome is not None
    settleable = bool(
        contextual and outcome and outcome["final"] and outcome["identity_status"] == "VERIFIED"
    )
    record["newly_settleable"] = settleable and record["settlement_state"] in {
        "PENDING",
        "UNSETTLED",
    }
    record["identity_status"] = outcome["identity_status"] if outcome else None
    record["prospective"] = bool(
        contextual
        and outcome
        and record["collected_at"] < outcome["kickoff_at"]
        and record["date_status"] in {"VERIFIED", "NOT_APPLICABLE"}
    )
    record["collected_at"] = record["collected_at"].isoformat()


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "policy_version": POLICY_VERSION,
        "total": len(records),
        "before": dict(Counter(r["current"] for r in records)),
        "after": dict(Counter(r["classification"] for r in records)),
        "reasons": _nested(records, "classification", "policy_reason"),
        "by_source": _breakdown(records, "source_code"),
        "by_competition": _breakdown(records, "competition"),
        "by_prediction_date": _breakdown(records, "prediction_date"),
        "missing_native_reference": sum(not r["native_reference"] for r in records),
        "newly_settleable": sum(r["newly_settleable"] for r in records),
        "prospective_candidates": sum(r["prospective"] for r in records),
        "contextual_identity_status": dict(
            Counter(
                r["identity_status"] for r in records if r["classification"] == "CONTEXTUAL_MATCH"
            )
        ),
        "candidate_cohorts": _cohorts(records),
        "calibration": _calibration(records),
        "predictions": records,
    }


def _breakdown(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        grouped[str(record[key])][record["classification"]] += 1
        grouped[str(record[key])]["total"] += 1
    return {name: dict(counts) for name, counts in sorted(grouped.items())}


def _nested(records: list[dict[str, Any]], outer: str, inner: str) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        if record["current"] != "VERIFIED":
            grouped[record[outer]][record[inner]] += 1
    return {name: dict(counts) for name, counts in sorted(grouped.items())}


def _cohorts(records: list[dict[str, Any]]) -> dict[str, int]:
    """The earlier audit's cohorts: same-date and date-offset team-name candidates."""
    open_records = [r for r in records if r["current"] != "VERIFIED"]
    same = {r["prediction_id"] for r in open_records if "SAME_DAY" in r["candidate_dates"]}
    offset = {
        r["prediction_id"]
        for r in open_records
        if {"ADJACENT_DAY", "MIDNIGHT_ADJACENT"} & set(r["candidate_dates"])
    }
    r2bet = {r["prediction_id"] for r in open_records if r["source_code"] == "r2bet"}
    return {
        "same_date_candidates": len(same),
        "offset_candidates": len(offset),
        "offset_candidates_r2bet": len(offset & r2bet),
        "both": len(same & offset),
    }


def _calibration(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the policy blind on verified bindings and count false associations."""
    verified = [r for r in records if r["current"] == "VERIFIED"]
    matched = [r for r in verified if r["policy_classification"] == "CONTEXTUAL_MATCH"]
    wrong = [r for r in matched if r["policy_fixture_id"] != r["verified_fixture_id"]]
    return {
        "verified_examples": len(verified),
        "policy_matched": len(matched),
        "policy_agrees": len(matched) - len(wrong),
        "false_associations": len(wrong),
        "false_association_rate": len(wrong) / len(matched) if matched else None,
        "abstained": dict(Counter(r["policy_reason"] for r in verified if r not in matched)),
        "disagreements": [
            {key: r[key] for key in ("prediction_id", "verified_fixture_id", "policy_fixture_id")}
            for r in wrong
        ],
    }
