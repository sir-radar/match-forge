"""Bounded SQL-only binding, date review and append-only external settlement."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row

from football.product.domain import external_settlement_state, sha256_json
from football.product.external_prediction_sources import ParserBrokenError, source_prediction_date

SETTLEMENT_BATCH_LIMIT = 128


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
                AND (mapping.valid_from IS NULL OR mapping.valid_from<=fixture.kickoff_at)
                AND (mapping.valid_to IS NULL OR mapping.valid_to>fixture.kickoff_at)
                AND mapping.first_seen_at<=statement_timestamp()""",
            (
                prediction["provider_code"],
                prediction["provider_code"],
                prediction["provider_fixture_id"],
                prediction["provider_code"],
                previous["mapping_id"] if previous else None,
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


def bind_reviewed_prediction(
    connection: Connection[Any], prediction_id: UUID, mapping_id: UUID, *, reason: str
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
    count = 0
    for (prediction_id,) in selected:
        with connection.transaction(), connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT football.authorize_worker_publication()")
            # Report invalidation precedes settlement detail in source writers too.
            report = cursor.execute(
                """SELECT scope_id FROM football.product_report_refresh_work
                WHERE report_kind='COMPARISON' AND scope_id=%s AND horizon='LATEST'
                FOR UPDATE SKIP LOCKED""",
                (prediction_id,),
            ).fetchone()
            if report is None:
                continue
            work = cursor.execute(
                """SELECT generation FROM football.external_prediction_refresh_work
                WHERE prediction_id=%s AND generation>completed_generation
                FOR UPDATE SKIP LOCKED""",
                (prediction_id,),
            ).fetchone()
            if work is None:
                continue
            refresh_prediction_binding(connection, prediction_id)
            _review_date(connection, prediction_id)
            count += _append_settlement(connection, prediction_id, requested_at)
            cursor.execute(
                """UPDATE football.external_prediction_refresh_work
                SET completed_generation=generation,completed_at=clock_timestamp()
                WHERE prediction_id=%s""",
                (prediction_id,),
            )
    return count


def _append_settlement(
    connection: Connection[Any], prediction_id: UUID, requested_at: datetime
) -> int:
    with connection.cursor(row_factory=dict_row) as cursor:
        row = cursor.execute(
            """SELECT ep.market,ep.selection,ep.binding_id,ep.date_status,
                coalesce(fixture.status,'UNKNOWN') AS fixture_status,fixture.identity_status,
                fixture.home_score,fixture.away_score,
                coalesce(fixture.result_score_basis,'UNKNOWN') AS score_basis,
                observation.provider_code,observation.provider_updated_at
            FROM football.external_prediction_effective ep
            LEFT JOIN football.product_fixtures fixture
                ON fixture.fixture_id=ep.effective_fixture_id
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
            ) observation ON true WHERE ep.prediction_id=%s""",
            (prediction_id,),
        ).fetchone()
        assert row is not None
        eligible = row["identity_status"] == "VERIFIED" and row["date_status"] in (
            "VERIFIED",
            "NOT_APPLICABLE",
        )
        state = (
            external_settlement_state(
                row["market"],
                row["selection"],
                row["fixture_status"],
                row["home_score"],
                row["away_score"],
                row["score_basis"],
            )
            if eligible
            else "PENDING"
        )
        fingerprint = sha256_json(
            {
                **row,
                "binding_id": str(row["binding_id"]) if row["binding_id"] else None,
                "provider_updated_at": row["provider_updated_at"].isoformat()
                if row["provider_updated_at"]
                else None,
                "settlement_state": state,
            }
        )
        previous = cursor.execute(
            "SELECT * FROM football.external_prediction_latest_results WHERE prediction_id=%s",
            (prediction_id,),
        ).fetchone()
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
