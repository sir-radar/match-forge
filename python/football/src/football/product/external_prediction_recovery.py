"""Bounded SQL-only binding, date review and append-only external settlement."""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Connection, Cursor, Error
from psycopg.errors import ObjectNotInPrerequisiteState
from psycopg.rows import dict_row

from football.product.domain import (
    external_selection_correct,
    external_settlement_state,
    sha256_json,
)
from football.product.external_prediction_sources import ParserBrokenError, source_prediction_date
from football.product.external_predictions import ImportedPrediction, verified_r2bet_mapping

SETTLEMENT_BATCH_LIMIT = 128
FINAL_STATES = frozenset({"WON", "LOST", "VOID"})
LOGGER = logging.getLogger(__name__)


def refresh_prediction_binding(connection: Connection[Any], prediction_id: UUID) -> None:
    """Use existing verified native mappings only; source names cannot repair a binding."""
    with connection.cursor(row_factory=dict_row) as cursor:
        prediction = cursor.execute(
            "SELECT * FROM football.external_predictions WHERE prediction_id=%s", (prediction_id,)
        ).fetchone()
        assert prediction is not None
        previous = cursor.execute(
            """SELECT binding.* FROM football.external_prediction_bindings binding
            WHERE prediction_id=%s AND NOT EXISTS (
                SELECT 1 FROM football.external_prediction_bindings successor
                WHERE successor.previous_binding_id=binding.binding_id)""",
            (prediction_id,),
        ).fetchone()
        if prediction["provider_code"] is None and (
            previous is None or previous["mapping_id"] is None
        ):
            _recover_r2bet_binding(connection, prediction_id, prediction)
            return
        matches = cursor.execute(
            """SELECT mapping.id,fixture.fixture_id,
                mapping.source_snapshot_id,mapping.mapping_method
            FROM football.match_provider_mappings mapping
            JOIN football.providers provider ON provider.id=mapping.provider_id
            JOIN football.product_fixtures fixture ON fixture.fixture_id=mapping.match_id
            WHERE ((%s::text IS NOT NULL AND provider.code=%s AND mapping.provider_match_id=%s)
                OR (%s::text IS NULL AND mapping.id=%s))
                AND mapping.mapping_confidence=1
                AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
                AND fixture.identity_status='VERIFIED'
                AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                    WHERE resolution.member_fixture_id=fixture.fixture_id AND resolution.active
                    AND (resolution.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                         OR resolution.representative_fixture_id<>fixture.fixture_id))
                AND (mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
                AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at)
                AND mapping.first_seen_at<=statement_timestamp()
                AND (%s::timestamptz IS NULL OR fixture.kickoff_at=%s)""",
            (
                prediction["provider_code"],
                prediction["provider_code"],
                prediction["provider_fixture_id"],
                prediction["provider_code"],
                previous["mapping_id"] if previous else None,
                prediction["source_kickoff_at"],
                prediction["source_kickoff_at"],
            ),
        ).fetchall()
        target = matches[0] if len(matches) == 1 else None
        if target is None and previous is None and prediction["fixture_id"] is None:
            return
        fixture, mapping = (target["fixture_id"], target["id"]) if target else (None, None)
        if previous and (previous["fixture_id"], previous["mapping_id"]) == (fixture, mapping):
            return
        cursor.execute(
            """INSERT INTO football.external_prediction_bindings
            (prediction_id,previous_binding_id,fixture_id,mapping_id,match_status,evidence)
            VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
            (
                prediction_id,
                previous["binding_id"] if previous else None,
                fixture,
                mapping,
                "MATCHED" if target else "UNMATCHED",
                json.dumps(
                    {
                        "method": "VERIFIED_PROVIDER_ID",
                        "provider_code": prediction["provider_code"],
                        "provider_fixture_id": prediction["provider_fixture_id"],
                        "candidate_count": len(matches),
                        "source_snapshot_id": str(target["source_snapshot_id"]) if target else None,
                        "mapping_method": target["mapping_method"] if target else None,
                        "reason": "verified mapping"
                        if target
                        else "mapping unavailable or not verified",
                    },
                    sort_keys=True,
                ),
            ),
        )


def _recover_r2bet_binding(
    connection: Connection[Any],
    prediction_id: UUID,
    prediction: dict[str, Any],
) -> None:
    provenance = prediction["mapping_provenance"]
    if (
        prediction["source_code"] != "r2bet"
        or not provenance.get("r2bet_match_id")
        or prediction["match_status"] == "AMBIGUOUS"
    ):
        return
    row = ImportedPrediction(
        source_page=prediction["source_page"],
        prediction_date=prediction["prediction_date"],
        original_date_text=prediction["original_date_text"],
        competition=prediction["competition_text"],
        home_team=prediction["home_team_text"],
        away_team=prediction["away_team_text"],
        market=prediction["market"],
        selection=prediction["selection"],
        fixture_reference_url=provenance.get("fixture_reference_url"),
        source_kickoff_text=provenance.get("source_kickoff_text"),
    )
    if mapping := verified_r2bet_mapping(connection, row):
        bind_reviewed_prediction(
            connection,
            prediction_id,
            mapping,
            reason=f"R2Bet match link and fixture context verified: {row.fixture_reference_url}",
        )


def bind_reviewed_prediction(
    connection: Connection[Any],
    prediction_id: UUID,
    mapping_id: UUID,
    *,
    reason: str,
) -> bool:
    """Record an explicit review; never infer a missing native ID from source names."""
    if not reason.strip():
        raise ValueError("external binding review requires retained evidence and a reason")
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT football.authorize_worker_publication()")
        cursor.execute("SELECT football.enqueue_external_prediction_refresh(%s)", (prediction_id,))
        prediction = cursor.execute(
            "SELECT revision_sha256 FROM football.external_predictions WHERE prediction_id=%s",
            (prediction_id,),
        ).fetchone()
        mapping = cursor.execute(
            """SELECT mapping.match_id,mapping.source_snapshot_id
            FROM football.match_provider_mappings mapping
            JOIN football.product_fixtures fixture ON fixture.fixture_id=mapping.match_id
            WHERE mapping.id=%s AND mapping.mapping_confidence=1
                AND mapping.mapping_method IN ('explicit_crosswalk','manual','deterministic')
                AND fixture.identity_status='VERIFIED'
                AND (mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
                AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at)
                AND mapping.first_seen_at<=statement_timestamp()""",
            (mapping_id,),
        ).fetchone()
        if prediction is None or mapping is None or mapping["source_snapshot_id"] is None:
            raise ValueError(
                "review requires an existing source capture and retained native mapping"
            )
        previous = cursor.execute(
            """SELECT binding.* FROM football.external_prediction_bindings binding
            WHERE prediction_id=%s AND NOT EXISTS (
                SELECT 1 FROM football.external_prediction_bindings successor
                WHERE successor.previous_binding_id=binding.binding_id)""",
            (prediction_id,),
        ).fetchone()
        if previous and previous["mapping_id"] == mapping_id:
            return False
        cursor.execute(
            """INSERT INTO football.external_prediction_bindings
            (prediction_id,previous_binding_id,fixture_id,mapping_id,match_status,evidence)
            VALUES(%s,%s,%s,%s,'MATCHED',%s::jsonb)""",
            (
                prediction_id,
                previous["binding_id"] if previous else None,
                mapping["match_id"],
                mapping_id,
                json.dumps(
                    {
                        "method": "REVIEWED_VERIFIED_PROVIDER_ID",
                        "review_reason": reason.strip(),
                        "source_revision_sha256": prediction["revision_sha256"],
                        "source_snapshot_id": str(mapping["source_snapshot_id"]),
                    }
                ),
            ),
        )
    return True


def _review_date(connection: Connection[Any], prediction_id: UUID) -> None:
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            """SELECT ep.source_code,ep.original_date_text,ep.prediction_date
            FROM football.external_predictions ep WHERE prediction_id=%s
            AND NOT EXISTS (SELECT 1 FROM football.external_prediction_date_reviews
                WHERE prediction_id=ep.prediction_id)""",
            (prediction_id,),
        ).fetchone()
        if row is None:
            return
        source_date, state = None, "NOT_APPLICABLE"
        if row["source_code"] in ("r2bet", "tips1960"):
            try:
                source_date = source_prediction_date(row["source_code"], row["original_date_text"])
                state = "VERIFIED" if source_date == row["prediction_date"] else "MISMATCH"
            except ParserBrokenError:
                state = "UNKNOWN"
        cursor.execute(
            """INSERT INTO football.external_prediction_date_reviews
            (prediction_id,source_date,date_status,reason) VALUES(%s,%s,%s,%s)
            ON CONFLICT(prediction_id) DO NOTHING""",
            (prediction_id, source_date, state, "exact retained source-date validation"),
        )


def settle_pending_predictions(
    connection: Connection[Any],
    requested_at: datetime,
    *,
    limit: int = SETTLEMENT_BATCH_LIMIT,
) -> int:
    """Checkpoint each bounded selection; caller-owned transactions remain caller-owned."""
    if requested_at.utcoffset() is None:
        raise ValueError("external settlement requires an aware request time")
    if type(limit) is not int or not 1 <= limit <= SETTLEMENT_BATCH_LIMIT:
        raise ValueError("external settlement limit must be between 1 and 128")
    with connection.transaction(), connection.cursor() as cursor:
        selected = cursor.execute(
            """SELECT prediction_id FROM football.external_prediction_refresh_work
            WHERE generation>completed_generation ORDER BY requested_at,prediction_id LIMIT %s""",
            (limit,),
        ).fetchall()
    return sum(
        _process_prediction(connection, prediction_id, requested_at)[1]
        for (prediction_id,) in selected
    )


def reconcile_external_predictions(
    connection: Connection[Any],
    requested_at: datetime,
    *,
    audit_only: bool = False,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Walk a fixed retained inventory. Committed outcomes survive interrupted runs."""
    if requested_at.utcoffset() is None:
        raise ValueError("external settlement requires an aware request time")
    with connection.transaction():
        inventory = connection.execute(
            """SELECT prediction_id FROM football.external_predictions
            ORDER BY prediction_id"""
        ).fetchall()
    counts: Counter[str] = Counter()
    details: list[dict[str, str]] = []
    changed: list[str] = []
    associations: Counter[str] = Counter()
    for index, (prediction_id,) in enumerate(inventory, 1):
        try:
            if audit_only:
                category, association = _inspect_prediction(connection, prediction_id)
            else:
                category, _, association = _process_prediction(
                    connection,
                    prediction_id,
                    requested_at,
                    manual=True,
                )
            associations[association] += 1
        except Error as error:
            if _unrecoverable_settlement_error(connection, error):
                raise
            LOGGER.error("External settlement failed for %s (%s)", prediction_id, error.sqlstate)
            category = association = "FAILED"
            associations[association] += 1
        counts[category] += 1
        if category in {"NEWLY_SETTLED", "NEWLY_VOIDED"}:
            changed.append(str(prediction_id))
        if audit_only:
            details.append(
                {
                    "prediction_id": str(prediction_id),
                    "category": category,
                    "association": association,
                }
            )
        if progress and index % SETTLEMENT_BATCH_LIMIT == 0:
            progress(
                {
                    "examined": index,
                    "total": len(inventory),
                    "counts": dict(counts),
                    "associations": dict(associations),
                }
            )
    result = {
        "examined": len(inventory),
        "total": len(inventory),
        "counts": dict(counts),
        "associations": dict(associations),
    }
    if audit_only:
        result["predictions"] = details
    else:
        result["changed_prediction_ids"] = changed
    return result


def _unrecoverable_settlement_error(connection: Connection[Any], error: Error) -> bool:
    return connection.closed or isinstance(error, ObjectNotInPrerequisiteState)


def _inspect_prediction(connection: Connection[Any], prediction_id: UUID) -> tuple[str, str]:
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        row = _settlement_input(cursor, prediction_id)
        state, reason = _evaluate(row)
        previous = _latest_result(cursor, prediction_id)
        return _finalized_category(previous, state, row) or reason or "ELIGIBLE", _association(row)


def _process_prediction(
    connection: Connection[Any],
    prediction_id: UUID,
    requested_at: datetime,
    *,
    manual: bool = False,
) -> tuple[str, int, str]:
    with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute("SELECT football.authorize_worker_publication()")
        if not _lock_prediction(cursor, prediction_id, manual=manual):
            return "DEFERRED", 0, "DEFERRED"
        refresh_prediction_binding(connection, prediction_id)
        _review_date(connection, prediction_id)
        row = _settlement_input(cursor, prediction_id)
        state, reason = _evaluate(row)
        previous = _latest_result(cursor, prediction_id)
        finalized = _finalized_category(previous, state, row)
        if manual and finalized:
            return finalized, 0, _association(row)
        unchanged_pending = (
            manual
            and reason is not None
            and previous is not None
            and previous["settlement_state"] == "PENDING"
            and (
                not row["native_provider"]
                or previous["evidence"].get("fixture_association") == _association(row)
            )
        )
        appended = (
            0
            if unchanged_pending
            else _append_settlement(
                cursor, prediction_id, requested_at, row, state, reason, previous
            )
        )
        cursor.execute(
            """UPDATE football.external_prediction_refresh_work
            SET completed_generation=generation,completed_at=clock_timestamp()
            WHERE prediction_id=%s AND completed_generation<generation""",
            (prediction_id,),
        )
        category = reason or ("NEWLY_VOIDED" if state == "VOID" else "NEWLY_SETTLED")
        return category, appended, _association(row)


def _lock_prediction(cursor: Cursor[dict[str, Any]], prediction_id: UUID, *, manual: bool) -> bool:
    # Provider and report workers take comparison detail before settlement detail.
    lock = "FOR UPDATE" if manual else "FOR UPDATE SKIP LOCKED"
    if manual:
        cursor.execute("SET LOCAL lock_timeout='2s'")
    report = cursor.execute(
        "SELECT scope_id FROM football.product_report_refresh_work "
        "WHERE report_kind='COMPARISON' AND scope_id=%s AND horizon='LATEST' " + lock,
        (prediction_id,),
    ).fetchone()
    if report is None:
        if not manual:
            return False
        cursor.execute("SELECT football.enqueue_external_prediction_refresh(%s)", (prediction_id,))
    pending = "" if manual else "AND generation>completed_generation "
    work = cursor.execute(
        "SELECT generation FROM football.external_prediction_refresh_work WHERE prediction_id=%s "
        + pending
        + lock,
        (prediction_id,),
    ).fetchone()
    if manual and work is None:
        cursor.execute("SELECT football.enqueue_external_prediction_refresh(%s)", (prediction_id,))
        return True
    return work is not None


_PROVIDER_ONLY_RESULT = """
SELECT o.*
FROM football.product_provider_fixture_observations o
JOIN football.source_snapshots snapshot ON snapshot.id=o.source_snapshot_id
JOIN football.providers provider ON provider.id=snapshot.provider_id
    AND provider.code=o.provider_code
WHERE o.provider_code=ep.provider_code AND o.provider_match_id=ep.provider_fixture_id
    AND snapshot.status='validated' AND o.observed_at<=statement_timestamp()
    AND snapshot.acquired_at<=statement_timestamp()
"""


def _settlement_input(cursor: Cursor[dict[str, Any]], prediction_id: UUID) -> dict[str, Any]:
    row = cursor.execute(
        """SELECT ep.market,ep.selection,ep.binding_id,ep.date_status,
            ep.effective_match_status, ep.provider_code AS native_provider,
            coalesce(fixture.status,native.canonical_status,'UNKNOWN') AS fixture_status,
            fixture.identity_status,
            native.observation_id IS NOT NULL AS native_fixture,
            native.source_snapshot_id::text AS native_snapshot_id,
            native.provider_match_id AS native_match_id,
            CASE WHEN fixture.fixture_id IS NOT NULL THEN fixture.home_score
                ELSE native.home_score END AS home_score,
            CASE WHEN fixture.fixture_id IS NOT NULL THEN fixture.away_score
                ELSE native.away_score END AS away_score,
            coalesce(fixture.result_score_basis,native.result_score_basis,'UNKNOWN')
                AS canonical_score_basis,
            coalesce(recovery.provider_code,history.source_provider_code,
                observation.provider_code,native.provider_code) AS provider_code,
            coalesce(recovery.provider_updated_at,history.known_at,
                observation.provider_updated_at,native.source_updated_at,native.observed_at)
                AS provider_updated_at,
            (recovery.provider_code IS NOT NULL) AS observed_regulation,
            history.source_provider_code AS history_provider,
            coalesce(recovery.source_snapshot_id,history.source_snapshot_id)::text
                AS recovery_snapshot_id,
            EXISTS (
                SELECT 1 FROM football.product_source_result_conflicts conflict
                WHERE conflict.canonical_match_id=fixture.fixture_id
            ) OR EXISTS (
                SELECT 1 FROM (
                    SELECT DISTINCT ON (o.provider_code) o.home_score,o.away_score
                    FROM football.product_provider_fixture_observations o
                    JOIN football.source_snapshots snap ON snap.id=o.source_snapshot_id
                    WHERE o.canonical_fixture_id=fixture.fixture_id
                        AND o.canonical_status='FINISHED' AND o.result_score_basis='REGULATION_90'
                        AND o.home_score IS NOT NULL AND o.observed_at>=fixture.kickoff_at
                        AND o.observed_at<=statement_timestamp() AND snap.status='validated'
                    ORDER BY o.provider_code,coalesce(o.source_updated_at,o.observed_at) DESC,
                        o.observed_at DESC,o.observation_id DESC
                ) current_scores
                WHERE (current_scores.home_score,current_scores.away_score)
                    IS DISTINCT FROM (fixture.home_score,fixture.away_score)
            ) OR coalesce(native.result_conflict,false) AS result_conflict,
            EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
                WHERE r.active AND r.member_fixture_id=fixture.fixture_id
                    AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
                         OR r.representative_fixture_id<>fixture.fixture_id))
                OR coalesce(native.identity_conflict,false) AS identity_conflict
        FROM football.external_prediction_effective ep
        LEFT JOIN football.product_fixtures fixture
            ON fixture.fixture_id=ep.effective_fixture_id
        LEFT JOIN LATERAL (
            WITH evidence AS MATERIALIZED ("""
        + _PROVIDER_ONLY_RESULT
        + """)
            SELECT current.*,
                EXISTS (SELECT 1 FROM evidence earlier
                    WHERE (earlier.provider_competition_id,earlier.provider_home_team_id,
                           earlier.provider_away_team_id) IS DISTINCT FROM
                          (current.provider_competition_id,current.provider_home_team_id,
                           current.provider_away_team_id))
                OR EXISTS (SELECT 1 FROM football.product_provider_mapping_decisions decision
                    WHERE decision.provider_code=current.provider_code
                      AND decision.provider_match_id=current.provider_match_id
                      AND decision.disposition='CONTRADICTORY') AS identity_conflict,
                EXISTS (SELECT 1 FROM evidence other
                    WHERE other.canonical_status='FINISHED'
                      AND other.result_score_basis='REGULATION_90'
                      AND current.result_score_basis='REGULATION_90'
                      AND (other.home_score,other.away_score) IS DISTINCT FROM
                          (current.home_score,current.away_score)) AS result_conflict
            FROM (SELECT evidence.* FROM evidence ORDER BY
                coalesce(source_updated_at,observed_at) DESC,observed_at DESC,observation_id DESC
                LIMIT 1) current
            WHERE current.provider_home_team_id IS NOT NULL
                AND current.provider_away_team_id IS NOT NULL
                AND current.provider_home_team_id<>current.provider_away_team_id
                AND current.canonical_fixture_id IS NULL
                AND (ep.source_kickoff_at IS NULL OR ep.source_kickoff_at=current.kickoff_at)
                AND (ep.source_kickoff_at IS NOT NULL OR ep.prediction_date IN (
                    (current.kickoff_at AT TIME ZONE 'UTC')::date,
                    (current.kickoff_at AT TIME ZONE 'Africa/Lagos')::date))
                AND NOT EXISTS (SELECT 1 FROM evidence linked
                    WHERE linked.canonical_fixture_id IS NOT NULL)
                AND (current.canonical_status NOT IN ('FINISHED','CANCELLED','ABANDONED','AWARDED')
                     OR current.observed_at>=current.kickoff_at)
                AND NOT EXISTS (SELECT 1 FROM football.match_provider_mappings mapping
                    JOIN football.providers p ON p.id=mapping.provider_id
                    WHERE p.code=ep.provider_code
                      AND mapping.provider_match_id=ep.provider_fixture_id
                      AND (mapping.valid_from IS NULL OR mapping.valid_from<=current.kickoff_at)
                      AND (mapping.valid_to IS NULL OR mapping.valid_to>current.kickoff_at))
        ) native ON fixture.fixture_id IS NULL AND ep.provider_code IS NOT NULL
        LEFT JOIN LATERAL (
            SELECT provider_code,coalesce(source_updated_at,observed_at) AS provider_updated_at
            FROM football.product_provider_fixture_observations
            WHERE canonical_fixture_id=fixture.fixture_id AND canonical_status=fixture.status
                AND home_score IS NOT DISTINCT FROM fixture.home_score
                AND away_score IS NOT DISTINCT FROM fixture.away_score
                AND result_score_basis=fixture.result_score_basis
            ORDER BY coalesce(source_updated_at,observed_at) DESC,
                observed_at DESC,observation_id DESC
            LIMIT 1
        ) observation ON true
        LEFT JOIN LATERAL (
            SELECT o.provider_code,o.source_snapshot_id,
                coalesce(o.source_updated_at,o.observed_at) AS provider_updated_at
            FROM football.product_provider_fixture_observations o
            JOIN football.source_snapshots snap ON snap.id=o.source_snapshot_id
            WHERE o.canonical_fixture_id=fixture.fixture_id AND o.canonical_status='FINISHED'
                AND o.result_score_basis='REGULATION_90'
                AND (o.home_score,o.away_score)=(fixture.home_score,fixture.away_score)
                AND o.observed_at>=fixture.kickoff_at AND o.observed_at<=statement_timestamp()
                AND snap.status='validated'
            ORDER BY coalesce(o.source_updated_at,o.observed_at) DESC,o.observed_at DESC,
                o.observation_id DESC LIMIT 1
        ) recovery ON fixture.status='FINISHED' AND fixture.result_score_basis='UNKNOWN'
        LEFT JOIN LATERAL (
            SELECT source_provider_code,source_snapshot_id,known_at
            FROM football.product_eligible_fixture_history_at(
                statement_timestamp(),ARRAY[fixture.fixture_id])
            WHERE (home_goals,away_goals)=(fixture.home_score,fixture.away_score)
                AND (home_team_id,away_team_id,kickoff_at)
                    =(fixture.home_team_id,fixture.away_team_id,fixture.kickoff_at)
        ) history ON fixture.status='FINISHED' AND fixture.result_score_basis='UNKNOWN'
        WHERE ep.prediction_id=%s""",
        (prediction_id,),
    ).fetchone()
    assert row is not None
    row["score_basis"] = row["canonical_score_basis"]
    if row["score_basis"] == "UNKNOWN" and (row["observed_regulation"] or row["history_provider"]):
        row["score_basis"] = "REGULATION_90"
    return row


def _verified_association(row: dict[str, Any]) -> bool:
    return row["native_fixture"] is True or (
        row["identity_status"] == "VERIFIED" and row["effective_match_status"] == "MATCHED"
    )


def _association(row: dict[str, Any]) -> str:
    if row["identity_conflict"]:
        return "IDENTITY_CONFLICT"
    if row["native_fixture"]:
        return "VERIFIED_PROVIDER_ONLY"
    if _verified_association(row):
        return "VERIFIED_CANONICAL"
    if row["effective_match_status"] == "AMBIGUOUS":
        return "AMBIGUOUS_IDENTITY"
    return "PROVIDER_FIXTURE_UNVERIFIED" if row["native_provider"] else "FIXTURE_IDENTITY"


def _evaluate(row: dict[str, Any]) -> tuple[str, str | None]:
    association = _association(row)
    if association not in {"VERIFIED_CANONICAL", "VERIFIED_PROVIDER_ONLY"}:
        return "PENDING", association
    if row["date_status"] not in ("VERIFIED", "NOT_APPLICABLE"):
        return "PENDING", "SOURCE_DATE"
    if row["result_conflict"] and row["fixture_status"] == "FINISHED":
        return "PENDING", "RESULT_CONFLICT"
    state = external_settlement_state(
        row["market"],
        row["selection"],
        row["fixture_status"],
        row["home_score"],
        row["away_score"],
        row["score_basis"],
    )
    if state != "PENDING":
        return state, None
    if external_selection_correct(row["market"], row["selection"], 0, 0) is None:
        return state, "UNSUPPORTED_MARKET"
    if row["fixture_status"] != "FINISHED":
        return state, "MATCH_NOT_FINISHED"
    return state, "QUALIFIED_SCORE_UNAVAILABLE"


def _latest_result(cursor: Cursor[dict[str, Any]], prediction_id: UUID) -> dict[str, Any] | None:
    return cursor.execute(
        "SELECT * FROM football.external_prediction_latest_results WHERE prediction_id=%s",
        (prediction_id,),
    ).fetchone()


def _finalized_category(
    previous: dict[str, Any] | None,
    state: str,
    row: dict[str, Any],
) -> str | None:
    if previous is None or previous["settlement_state"] not in FINAL_STATES:
        return None
    if any(previous[key] != row[key] for key in ("home_score", "away_score", "fixture_status")):
        return "FINALIZED_NEEDS_REVIEW"
    if previous["settlement_state"] != state:
        return "FINALIZED_NEEDS_REVIEW"
    return "ALREADY_VOIDED" if state == "VOID" else "ALREADY_SETTLED"


def _append_settlement(
    cursor: Cursor[dict[str, Any]],
    prediction_id: UUID,
    requested_at: datetime,
    row: dict[str, Any],
    state: str,
    reason: str | None,
    previous: dict[str, Any] | None,
) -> int:
    fingerprint = sha256_json(
        {
            **{
                key: row[key]
                for key in (
                    "market",
                    "selection",
                    "date_status",
                    "fixture_status",
                    "identity_status",
                    "home_score",
                    "away_score",
                    "score_basis",
                    "provider_code",
                )
            },
            "binding_id": str(row["binding_id"]) if row["binding_id"] else None,
            "provider_updated_at": row["provider_updated_at"].isoformat()
            if row["provider_updated_at"]
            else None,
            "settlement_state": state,
        }
        | ({"blocker": reason} if reason else {})
        | ({"native_match_id": row["native_match_id"]} if row["native_fixture"] else {})
    )
    if previous and previous["evidence"].get("result_fingerprint") == fingerprint:
        return 0
    predecessor = str(previous["result_revision_id"]) if previous else None
    sequence = (previous["revision_sequence"] or 0) + 1 if previous else 1
    semantic = sha256_json(
        {
            "prediction_id": str(prediction_id),
            "result_fingerprint": fingerprint,
            "predecessor": predecessor,
        }
    )
    cursor.execute(
        """INSERT INTO football.external_prediction_result_revisions
        (prediction_id,semantic_sha256,settlement_state,fixture_status,home_score,away_score,
         score_basis,provider_code,provider_updated_at,evidence,settled_at,
         revision_sequence,previous_result_revision_id)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,clock_timestamp(),%s,%s)""",
        (
            prediction_id,
            semantic,
            state,
            row["fixture_status"],
            row["home_score"],
            row["away_score"],
            row["score_basis"] if row["fixture_status"] == "FINISHED" else "NOT_SETTLED",
            row["provider_code"],
            row["provider_updated_at"],
            json.dumps(
                {
                    "market": row["market"],
                    "selection": row["selection"],
                    "result_fingerprint": fingerprint,
                    "requested_at": requested_at.isoformat(),
                    "previous_result_revision_id": predecessor,
                    "date_status": row["date_status"],
                    "blocker": reason,
                    "canonical_score_basis": row["canonical_score_basis"],
                    "recovery_snapshot_id": row["recovery_snapshot_id"],
                    "native_snapshot_id": row["native_snapshot_id"],
                    "native_match_id": row["native_match_id"],
                    "fixture_association": _association(row),
                },
                sort_keys=True,
            ),
            sequence,
            predecessor,
        ),
    )
    if state in ("WON", "LOST"):
        cursor.execute(
            """INSERT INTO football.external_prediction_results
            (prediction_id,correct,settled_at)
            VALUES(%s,%s,clock_timestamp()) ON CONFLICT(prediction_id) DO NOTHING""",
            (prediction_id, state == "WON"),
        )
    return 1
