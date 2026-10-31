"""Freeze affected targets and continue their recovery through the shared work owner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID, uuid4

from psycopg import Connection, Error
from psycopg.types.json import Jsonb

from football.product.domain import sha256_json
from football.product.fixture_reconciliation import fixture_neighborhood, reconcile_product_fixtures
from football.product.identity_admission import (
    RetainedEvidenceChanged,
    RetainedIdentityVerifier,
    classify_mapping,
    mapping_rows,
    verify_source_identifier,
)
from football.product.operational_provider_sync import OperationalProviderSync
from football.product.sync import HISTORY_JOB_LEASE
from football.storage.locks import (
    FIXTURE_CROSSWALK_LOCK,
    IDENTITY_ADMISSION_LOCK,
    acquire_locks,
    lock_fixtures,
)
from football.work.contracts import (
    RetryClassification,
    RetryPolicy,
    WorkClaim,
    WorkRequest,
    WorkType,
)
from football.work.storage import WorkLeaseLost, WorkRegistry

BATCH_SIZE = 32  # Same bound as the existing context-report worker.
ZERO = UUID(int=0)
FIXTURE_DIGEST = """encode(sha256(convert_to(jsonb_build_array(f.fixture_id,f.competition_id,
    f.home_team_id,f.away_team_id,f.kickoff_at,f.status,f.home_score,f.away_score,
    f.updated_at,f.identity_status)::text,'UTF8')),'hex')"""
OBSERVATION_COLUMNS = """provider_match_id,provider_competition_id,provider_home_team_id,
    provider_away_team_id,provider_home_team_name,provider_away_team_name,kickoff_at,
    canonical_status,provider_status,home_score,away_score,match_minute,added_time,period,
    source_updated_at,observed_at,provider_competition_name,source_snapshot_id,result_score_basis"""


def recovery_scope(prepared: dict[str, Any]) -> dict[str, Any]:
    detail, candidate = prepared["detail"], prepared["candidate"]
    kind, identifier = prepared["case_key"].split(":", 1)
    mapping = detail.get("mapping_version", [])
    entities = {
        detail.get("decision", {}).get("canonical_id"),
        prepared["qualification"].get("canonical_id"),
    }
    if mapping:
        entities.add(mapping[1])
    entities.update(
        item.get("canonical_id")
        for item in detail.get("candidates", [])
        if item.get("mapping_id") == candidate.get("target_mapping_id")
    )
    fixtures = {candidate.get("fixture_id"), detail.get("decision", {}).get("candidate_fixture_id")}
    if kind == "fixture_record":
        fixtures.add(identifier)
    provider, native = (mapping[2], mapping[3]) if mapping else ("", "")
    if kind == "fixture":
        provider, native = identifier.split(":", 1)
    return {
        "entities": sorted(str(key) for key in entities if key),
        "fixtures": sorted(str(key) for key in fixtures if key),
        "kind": kind,
        "provider": provider,
        "native": native,
        "snapshots": [detail["registration"]["source_snapshot_id"]]
        if detail.get("registration", {}).get("source_snapshot_id")
        else [],
    }


def enqueue_recovery(
    connection: Connection[Any],
    request_id: str,
    prepared: dict[str, Any],
    parent: UUID | None = None,
) -> UUID:
    """Join the approved decision transaction; snapshot only its affected target IDs."""
    scope = recovery_scope(prepared)
    connection.execute(
        """INSERT INTO football.resolution_recovery_targets
           SELECT %s,'FIXTURE',f.fixture_id,"""
        + FIXTURE_DIGEST
        + """
           FROM football.product_fixtures f WHERE f.home_team_id=ANY(%s::uuid[])
             OR f.away_team_id=ANY(%s::uuid[]) OR f.competition_id=ANY(%s::uuid[])
             OR f.fixture_id=ANY(%s::uuid[]) OR EXISTS (
                SELECT 1 FROM football.product_provider_fixture_observations o
                WHERE o.canonical_fixture_id=f.fixture_id
                  AND o.source_snapshot_id=ANY(%s::uuid[])) ON CONFLICT DO NOTHING""",
        (
            request_id,
            scope["entities"],
            scope["entities"],
            scope["entities"],
            scope["fixtures"],
            scope["snapshots"],
        ),
    )
    connection.execute(
        """INSERT INTO football.resolution_recovery_targets
           SELECT %s,'OBSERVATION',o.observation_id,o.semantic_sha256
           FROM football.product_provider_fixture_observations o WHERE (
             EXISTS (SELECT 1 FROM football.resolution_recovery_targets t
                WHERE t.request_id=%s AND t.target_kind='FIXTURE'
                  AND t.target_id=o.canonical_fixture_id)
             OR o.source_snapshot_id=ANY(%s::uuid[])
             OR (o.provider_code=%s AND CASE %s WHEN 'team' THEN %s IN
                    (o.provider_home_team_id,o.provider_away_team_id)
                WHEN 'competition' THEN o.provider_competition_id=%s
                WHEN 'fixture' THEN o.provider_match_id=%s ELSE false END))
             AND NOT EXISTS (SELECT 1 FROM football.product_provider_fixture_observations newer
                WHERE newer.provider_code=o.provider_code
                  AND newer.provider_match_id=o.provider_match_id
                  AND (newer.observed_at,newer.observation_id)>(o.observed_at,o.observation_id))
           ON CONFLICT DO NOTHING""",
        (
            request_id,
            request_id,
            scope["snapshots"],
            scope["provider"],
            scope["kind"],
            scope["native"],
            scope["native"],
            scope["native"],
        ),
    )
    return enqueue_page(
        connection, request_id, inventory_digest(connection, request_id), "", ZERO, parent
    )


def inventory_digest(connection: Connection[Any], request_id: str) -> str:
    row = connection.execute(
        """SELECT encode(sha256(convert_to(coalesce(string_agg(target_kind||':'||target_id||':'||
           source_sha256,E'\\n' ORDER BY target_kind,target_id),''),'UTF8')),'hex')
           FROM football.resolution_recovery_targets WHERE request_id=%s""",
        (request_id,),
    ).fetchone()
    assert row is not None
    return cast(str, row[0])


def enqueue_page(
    connection: Connection[Any],
    request_id: str,
    inventory: str,
    cursor_kind: str,
    cursor_id: UUID,
    parent: UUID | None = None,
) -> UUID:
    request_id = str(UUID(request_id))
    inputs = page_inputs(request_id, inventory, cursor_kind, cursor_id)
    request = WorkRequest(
        work_type=WorkType.CANONICAL_RECONCILIATION,
        semantic_key=f"resolution-recovery:{request_id}:{cursor_kind}:{cursor_id}",
        input_hash=sha256_json(inputs),
        priority=0,
        available_at=datetime.now(UTC),
        max_attempts=2**31 - 1,
        retry_policy=RetryPolicy(timedelta(), timedelta(), 1, lease_expiry_delay=timedelta()),
        dependencies=(parent,) if parent else (),
        parent_work_id=parent,
    )
    WorkRegistry(connection).enqueue(request)
    connection.execute(
        """INSERT INTO football.resolution_recovery_work
           (work_id,request_id,inventory_sha256,cursor_kind,cursor_id) VALUES (%s,%s,%s,%s,%s)
           ON CONFLICT DO NOTHING""",
        (request.work_id, request_id, inventory, cursor_kind, cursor_id),
    )
    return request.work_id


def page_inputs(
    request_id: str, inventory: str, cursor_kind: str, cursor_id: UUID
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "inventory_sha256": inventory,
        "cursor_kind": cursor_kind,
        "cursor_id": str(cursor_id),
        "batch_size": BATCH_SIZE,
    }


def observation_source(
    connection: Connection[Any], identifier: UUID, expected: str
) -> tuple[str, tuple[Any, ...]]:
    row = connection.execute(
        "SELECT provider_code,"
        + OBSERVATION_COLUMNS
        + " FROM football.product_provider_fixture_observations "
        "WHERE observation_id=%s AND semantic_sha256=%s",
        (identifier, expected),
    ).fetchone()
    if row is None or any(row[n] is None for n in (2, 3, 4, 5, 6)):
        raise ValueError("retained native observation is missing or changed; request evidence")
    return row[0], tuple(row[1:])


def verify_observation(
    connection: Connection[Any],
    root: Path,
    provider: str,
    source: tuple[Any, ...],
    verifier: RetainedIdentityVerifier,
) -> None:
    for kind, identifier in (("competition", source[1]), ("team", source[2]), ("team", source[3])):
        if (
            verify_source_identifier(
                connection, root, source[17], provider, kind, identifier, None, verifier
            )
            is None
        ):
            raise ValueError(
                "retained source identifiers are unavailable; recover bytes or request evidence"
            )


def verify_fixture_admissions(
    connection: Connection[Any], root: Path, identifier: UUID, verifier: RetainedIdentityVerifier
) -> None:
    neighbors = fixture_neighborhood(connection, (identifier,))
    mappings = connection.execute(
        """WITH scopes AS (SELECT * FROM football.product_effective_fixtures
                          WHERE fixture_id=ANY(%s::uuid[]))
           SELECT DISTINCT 'team',m.id FROM football.product_effective_team_mappings m
           WHERE m.valid_to IS NULL AND EXISTS (SELECT 1 FROM scopes f
               WHERE m.team_id IN(f.home_team_id,f.away_team_id)
                  OR m.effective_team_id IN(f.home_team_id,f.away_team_id))
             AND football.product_mapping_trusted('team',m.id,m.effective_team_id)
           UNION SELECT DISTINCT 'competition',m.id FROM football.competition_provider_mappings m
           WHERE m.valid_to IS NULL AND m.competition_id IN(SELECT competition_id FROM scopes)
             AND football.product_mapping_trusted('competition',m.id,m.competition_id)
           ORDER BY 1,2""",
        (list(neighbors),),
    ).fetchall()
    for kind, key in mappings:
        entity = cast(Literal["team", "competition"], kind)
        rows = mapping_rows(connection, entity, mapping_id=key)
        if not rows or classify_mapping(connection, entity, rows[0], root, verifier)[
            "disposition"
        ] not in {"ORIGIN_ANCHOR", "CROSSWALK"}:
            raise ValueError(
                "current admitted identity lost retained proof; request evidence or quarantine"
            )


def prepare_targets(
    connection: Connection[Any],
    root: Path,
    targets: list[tuple[Any, ...]],
    verifier: RetainedIdentityVerifier,
) -> dict[UUID, str]:
    blocked = {}
    for kind, identifier, expected in targets:
        try:
            if kind == "FIXTURE":
                verify_fixture_admissions(connection, root, identifier, verifier)
            else:
                provider, source = observation_source(connection, identifier, expected)
                verify_observation(connection, root, provider, source, verifier)
        except (ValueError, OSError) as error:
            blocked[identifier] = str(error)
    verifier.seal()
    return blocked


def coordination_fixtures(
    connection: Connection[Any], targets: list[tuple[Any, ...]]
) -> list[UUID]:
    ids = [
        member
        for kind, identifier, _ in targets
        if kind == "FIXTURE"
        for member in fixture_neighborhood(connection, (identifier,))
    ]
    observations = [identifier for kind, identifier, _ in targets if kind == "OBSERVATION"]
    # The existing resolver uses this tolerance. Include native mappings for reschedules too.
    tolerance = OperationalProviderSync(
        connection, Path("."), provider_code="fotmob"
    ).kickoff_tolerance
    rows = connection.execute(
        """SELECT DISTINCT f.fixture_id FROM football.product_fixtures f
           WHERE f.fixture_id=ANY(%s::uuid[]) OR EXISTS (
             SELECT 1 FROM football.product_provider_fixture_observations o
             WHERE o.observation_id=ANY(%s::uuid[]) AND
               (f.kickoff_at BETWEEN o.kickoff_at-%s AND o.kickoff_at+%s OR EXISTS (
                 SELECT 1 FROM football.match_provider_mappings m
                 JOIN football.providers p ON p.id=m.provider_id
                 WHERE m.match_id=f.fixture_id AND p.code=o.provider_code
                   AND m.provider_match_id=o.provider_match_id)))
           ORDER BY f.fixture_id LIMIT %s""",
        (ids, observations, tolerance, tolerance, BATCH_SIZE * 100 + 1),
    ).fetchall()
    if len(rows) > BATCH_SIZE * 100:
        raise ValueError("fixture coordination exceeds bounded review; split the affected scope")
    return [row[0] for row in rows]


def request_downstream(connection: Connection[Any], identifier: UUID) -> dict[str, Any]:
    connection.execute("SELECT football.enqueue_product_context_report_refresh(%s)", (identifier,))
    row = connection.execute(
        """SELECT football.enqueue_product_forecast_refresh(fixture_id)
           FROM football.product_fixtures WHERE fixture_id=%s AND status='SCHEDULED'
             AND identity_status='VERIFIED' AND kickoff_at>clock_timestamp()""",
        (identifier,),
    ).fetchone()
    connection.execute(
        "SELECT football.enqueue_product_performance(competition_id) "
        "FROM football.product_fixtures WHERE fixture_id=%s",
        (identifier,),
    )
    predictions = connection.execute(
        "SELECT football.enqueue_external_prediction_refresh(prediction_id) "
        "FROM football.external_prediction_effective WHERE effective_fixture_id=%s",
        (identifier,),
    ).fetchall()
    return {
        "context_requested": True,
        "forecast_requested": row is not None,
        "performance_requested": True,
        "external_requests": len(predictions),
        "status": "REQUESTED; PUBLICATION_OWNERS_REMAIN_AUTHORITATIVE",
    }


def process_target(
    connection: Connection[Any],
    root: Path,
    target: tuple[Any, ...],
    verifier: RetainedIdentityVerifier,
) -> dict[str, Any]:
    kind, identifier, expected = target
    if kind == "FIXTURE":
        row = connection.execute(
            "SELECT " + FIXTURE_DIGEST + ",f.identity_status "
            "FROM football.product_fixtures f WHERE fixture_id=%s",
            (identifier,),
        ).fetchone()
        if row is None or row[0] != expected:
            raise ValueError("fixture context changed; approve a fresh revalidation")
        verify_fixture_admissions(connection, root, identifier, verifier)
        pairs = reconcile_product_fixtures(connection, fixture_ids=(identifier,))
        return {
            "resolved_pairs": pairs,
            "status": "RECONCILED" if pairs else "CHECKED",
            "domain_identity_status": row[1],
            "downstream": request_downstream(connection, identifier),
        }
    provider, source = observation_source(connection, identifier, expected)
    verify_observation(connection, root, provider, source, verifier)
    fixture = OperationalProviderSync(
        connection, root, provider_code=provider
    ).reconcile_retained_observation(source)
    return {
        "status": "RECONCILED" if fixture else "BLOCKED",
        "fixture_id": str(fixture) if fixture else None,
        "downstream": request_downstream(connection, fixture) if fixture else None,
        "reason": "Existing native-ID qualification; original observation and clocks retained"
        if fixture
        else "No qualified canonical fixture; review native identities and retained context",
    }


def target_receipt(
    connection: Connection[Any], request_id: UUID, target: tuple[Any, ...]
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT result FROM football.resolution_recovery_results WHERE request_id=%s "
        "AND target_kind=%s AND target_id=%s",
        (request_id, target[0], target[1]),
    ).fetchone()
    return row[0] if row else None


def publish_target(
    connection: Connection[Any],
    root: Path,
    claim: WorkClaim,
    request_id: UUID,
    target: tuple[Any, ...],
    verifier: RetainedIdentityVerifier,
    blocked: dict[UUID, str],
) -> dict[str, Any]:
    with connection.transaction():
        acquire_locks(connection, (IDENTITY_ADMISSION_LOCK, FIXTURE_CROSSWALK_LOCK))
        reason = blocked.get(target[1])
        fixtures: list[UUID] = []
        if reason is None:
            try:
                fixtures = coordination_fixtures(connection, [target])
            except ValueError as error:
                reason = str(error)
        lock_fixtures(connection, fixtures)
        with WorkRegistry(connection).progress(claim):
            previous = target_receipt(connection, request_id, target)
            if previous:
                return previous
            try:
                with connection.transaction():
                    if reason is not None:
                        raise ValueError(reason)
                    result = process_target(connection, root, target, verifier)
            except (ValueError, OSError) as error:
                result = {"status": "BLOCKED", "reason": str(error)}
            result = {"kind": target[0], "id": str(target[1]), **result}
            connection.execute(
                """INSERT INTO football.resolution_recovery_results
                   (request_id,target_kind,target_id,work_id,result,result_sha256)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    request_id,
                    target[0],
                    target[1],
                    claim.work_id,
                    Jsonb(result),
                    sha256_json(result),
                ),
            )
            return result


def publish_page(
    connection: Connection[Any],
    root: Path,
    claim: WorkClaim,
    binding: tuple[Any, ...],
    targets: list[tuple[Any, ...]],
    verifier: RetainedIdentityVerifier,
    blocked: dict[UUID, str],
    has_more: bool,
) -> dict[str, Any]:
    registry = WorkRegistry(connection)
    results = []
    for target in targets:
        claim = registry.heartbeat(claim, HISTORY_JOB_LEASE)
        results.append(
            publish_target(connection, root, claim, binding[0], target, verifier, blocked)
        )
    outcome = {
        "targets": results,
        "processed": len(results),
        "blocked": sum(item["status"] == "BLOCKED" for item in results),
        "downstream_status": "EXISTING_FORECAST_AND_PUBLIC_REPORT_QUEUES_OWN_REFRESH",
    }
    # Publish the child and page receipt together after the per-target checkpoints.
    with connection.transaction():
        if has_more:
            last = targets[-1]
            outcome["continuation_work_id"] = str(
                enqueue_page(
                    connection, str(binding[0]), binding[1], last[0], last[1], claim.work_id
                )
            )
        if not has_more:
            from football.product.resolution_parity import enqueue_parity

            case = connection.execute(
                "SELECT case_key FROM football.resolution_review_events WHERE request_id=%s",
                (binding[0],),
            ).fetchone()
            assert case is not None
            outcome["parity_work_id"] = str(
                enqueue_parity(connection, str(binding[0]), case[0], claim.work_id)
            )
        with registry.publication(claim, result_hash=sha256_json(outcome)):
            connection.execute(
                "UPDATE football.resolution_recovery_work SET outcome=%s WHERE work_id=%s",
                (Jsonb(outcome), claim.work_id),
            )
    return outcome


def run_pending_recovery(connection: Connection[Any], root: Path) -> dict[str, Any]:
    registry = WorkRegistry(connection)
    with connection.transaction():
        ready = connection.execute(
            "SELECT to_regclass('football.resolution_file_recovery_work')"
        ).fetchone()
        file_work = (
            " UNION ALL SELECT work_id FROM football.resolution_file_recovery_work"
            if ready and ready[0]
            else ""
        )
        parity_ready = connection.execute(
            "SELECT to_regclass('football.resolution_parity_work')"
        ).fetchone()
        if parity_ready and parity_ready[0]:
            file_work += " UNION ALL SELECT work_id FROM football.resolution_parity_work"
        rows = connection.execute(
            """SELECT b.work_id FROM (SELECT work_id FROM football.resolution_recovery_work"""
            + file_work
            + """) b
               JOIN football.work_items w USING(work_id)
               WHERE w.state IN ('PENDING','RETRY_WAIT','RUNNING')
               ORDER BY w.priority DESC,w.available_at,w.work_id"""
        ).fetchall()
    if not rows:
        return {"status": "IDLE"}
    claim = registry.claim(
        f"resolution-recovery:{uuid4()}",
        HISTORY_JOB_LEASE,
        (
            WorkType.CANONICAL_RECONCILIATION,
            WorkType.PROVIDER_ACQUISITION,
            WorkType.READ_MODEL_PROJECTION,
        ),
        work_ids=tuple(row[0] for row in rows),
    )
    if claim is None:
        return {"status": "BUSY"}
    if claim.work_type == WorkType.READ_MODEL_PROJECTION:
        from football.product.resolution_parity import publish_parity

        return publish_parity(connection, Path.cwd(), root, claim)
    if claim.work_type == WorkType.PROVIDER_ACQUISITION:
        from football.product.resolution_files import publish_file

        return publish_file(connection, root, claim)
    try:
        with connection.transaction():
            binding = connection.execute(
                "SELECT request_id,inventory_sha256,cursor_kind,cursor_id "
                "FROM football.resolution_recovery_work WHERE work_id=%s",
                (claim.work_id,),
            ).fetchone()
            assert binding is not None
            expected = page_inputs(str(binding[0]), binding[1], binding[2], binding[3])
            if claim.input_hash != sha256_json(expected) or binding[1] != inventory_digest(
                connection, str(binding[0])
            ):
                raise ValueError("recovery work differs from its approved frozen inventory")
            targets = connection.execute(
                """SELECT target_kind,target_id,source_sha256
                   FROM football.resolution_recovery_targets
                   WHERE request_id=%s AND (target_kind,target_id)>(%s,%s)
                   ORDER BY target_kind,target_id LIMIT %s""",
                (binding[0], binding[2], binding[3], BATCH_SIZE + 1),
            ).fetchall()
            verifier = RetainedIdentityVerifier(root)
            blocked = prepare_targets(connection, root, targets[:BATCH_SIZE], verifier)
        claim = registry.heartbeat(claim, HISTORY_JOB_LEASE)
        outcome = publish_page(
            connection,
            root,
            claim,
            binding,
            targets[:BATCH_SIZE],
            verifier,
            blocked,
            len(targets) > BATCH_SIZE,
        )
        return {
            "status": "PROCESSED_WITH_BLOCKERS" if outcome["blocked"] else "PROCESSED",
            "work_id": str(claim.work_id),
            "outcome": outcome,
        }
    except WorkLeaseLost:
        return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
    except (Error, ValueError, OSError, RetainedEvidenceChanged) as error:
        connection.rollback()
        classification = (
            RetryClassification.BLOCKED_EXTERNAL
            if isinstance(error, ValueError)
            else RetryClassification.RETRYABLE
        )
        try:
            registry.fail(
                claim,
                classification,
                error_code="RESOLUTION_RECOVERY_FAILED",
                error_message=str(error) if isinstance(error, ValueError) else type(error).__name__,
            )
        except WorkLeaseLost:
            return {"status": "LEASE_LOST", "work_id": str(claim.work_id)}
        return {
            "status": "BLOCKED"
            if classification == RetryClassification.BLOCKED_EXTERNAL
            else "RETRY_WAIT",
            "work_id": str(claim.work_id),
        }
