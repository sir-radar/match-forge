"""Audit a frozen accepted V4 history pilot through existing identity and normalization owners."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import psycopg
from football.contracts.observations_v2 import FixtureObservationV2, ResultObservationV2
from football.contracts.source import canonical_json_bytes
from football.identity.repository import IdentityRepository
from football.product.domain import fixture_identity
from football.product.identity_admission import (
    RetainedIdentityVerifier,
    classify_mapping,
    mapping_rows,
)
from football.providers.native.api_football import ApiFootballFixture
from football.providers.native.reader import native_json, native_record
from football.providers.normalization.cli import registered_resource
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource
from football.storage.raw import ImmutableFileStore
from psycopg import Connection


def verify_result(row: ApiFootballFixture, history: dict[str, Any]) -> None:
    """Compare source-native FT values with the already accepted history decision."""
    if history["source_kickoff_precision"] != "EXACT":
        raise ValueError("pilot requires an exact accepted kickoff")
    fixture = row["fixture"]
    kickoff = datetime.fromisoformat(fixture["date"])
    if kickoff.utcoffset() is None or kickoff != datetime.fromisoformat(history["kickoff_at"]):
        raise ValueError("source kickoff differs from accepted history")
    if (
        kickoff.utcoffset() != timedelta(0)
        or fixture.get("timestamp") != int(kickoff.timestamp())
        or fixture.get("timezone") != "UTC"
    ):
        raise ValueError("source UTC date and epoch do not agree")
    if fixture["status"]["short"] != "FT" or fixture["status"].get("elapsed") != 90:
        raise ValueError("pilot requires directly reported completed regulation time")
    expected = {"home": history["home_goals"], "away": history["away_goals"]}
    scores = row.get("score", {})
    if row["goals"] != expected or scores.get("fulltime") != expected:
        raise ValueError("source regulation scores differ from accepted history")
    if any(scores.get(key) != {"home": None, "away": None} for key in ("extratime", "penalty")):
        raise ValueError("pilot excludes extra-time and shootout score evidence")
    expected_id = fixture_identity(
        UUID(history["competition_id"]),
        str(row["league"]["season"]),
        kickoff,
        UUID(history["home_team_id"]),
        UUID(history["away_team_id"]),
    )
    if str(expected_id) != history["fixture_id"]:
        raise ValueError("original canonical fixture derivation differs")


def _accepted_history(
    connection: Connection[Any],
    root: Path,
    selected: dict[str, Any],
    cutoff: datetime,
    verifier: RetainedIdentityVerifier,
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT to_jsonb(h) FROM football.product_eligible_history_at(%s) h WHERE fixture_id=%s",
        (cutoff, selected["fixture_id"]),
    ).fetchone()
    if row is None or row[0] != selected["history"]:
        raise ValueError("frozen accepted history is unavailable at the label cutoff")
    repository = IdentityRepository(connection)
    for anchor in selected["anchors"]:
        kind, key = anchor["kind"], UUID(anchor["mapping_id"])
        proof = repository.admission_proof_at(kind, key, cutoff)
        if proof is None or proof.to_dict() != anchor["proof"]:
            raise ValueError("frozen canonical entity admission differs")
        mappings = mapping_rows(connection, kind, mapping_id=key)
        if len(mappings) != 1:
            raise ValueError("canonical mapping no longer exists uniquely")
        decision = classify_mapping(connection, kind, mappings[0], root, verifier)
        if decision["disposition"] not in {"ORIGIN_ANCHOR", "CROSSWALK"}:
            raise ValueError("retained canonical entity anchor no longer verifies")
    return cast(dict[str, Any], row[0])


def _source_result(
    connection: Connection[Any],
    root: Path,
    selected: dict[str, Any],
    history: dict[str, Any],
) -> tuple[NormalizationContext, ApiFootballFixture, int, bytes]:
    context, raw = registered_resource(connection, root, UUID(selected["source_resource_id"]))
    if (
        context.provenance.provider,
        str(context.provenance.source_snapshot_id),
        context.provenance.source_sha256,
    ) != (
        "api_football",
        selected["source_snapshot_id"],
        selected["source_sha256"],
    ):
        raise ValueError("source registration differs from frozen pilot")
    value = native_json(raw)
    if not isinstance(value, dict) or not isinstance(value.get("response"), list):
        raise ValueError("source fixture response must contain an array")
    matches = [
        (i, native_record(ApiFootballFixture, row))
        for i, row in enumerate(value["response"])
        if isinstance(row, dict)
        and str(row.get("fixture", {}).get("id")) == selected["native_fixture_id"]
    ]
    if len(matches) != 1:
        raise ValueError("native fixture is absent or ambiguous in retained resource")
    index, row = matches[0]
    if selected["source_record_key"] != f"json:/response/{index}":
        raise ValueError("frozen source-record key differs")
    expected_anchors = {
        ("competition", str(row["league"]["id"]), history["competition_id"]),
        ("team", str(row["teams"]["home"]["id"]), history["home_team_id"]),
        ("team", str(row["teams"]["away"]["id"]), history["away_team_id"]),
    }
    actual = {(a["kind"], a["native_id"], a["canonical_id"]) for a in selected["anchors"]}
    if len(selected["anchors"]) != 3 or actual != expected_anchors:
        raise ValueError("entity admissions do not bind the exact native participants")
    if str(context.provenance.source_snapshot_id) != history["source_snapshot_id"]:
        raise ValueError("source does not belong to the accepted history snapshot")
    verify_result(row, history)
    return context, row, index, raw


def audit_pilot(
    connection: Connection[Any],
    root: Path,
    pilot: dict[str, Any],
    pilot_sha256: str,
) -> dict[str, Any]:
    cutoff = datetime.fromisoformat(pilot["knowledge_cutoff"])
    if cutoff.utcoffset() is None:
        raise ValueError("label knowledge cutoff must include a timezone")
    selected_ids = [row["fixture_id"] for row in pilot["fixtures"]]
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise ValueError("pilot fixture identities must be nonempty and unique")
    verifier = RetainedIdentityVerifier(root)
    reports = []
    normalized: dict[UUID, NormalizationResult] = {}
    for selected in pilot["fixtures"]:
        history = _accepted_history(connection, root, selected, cutoff, verifier)
        context, native, index, raw = _source_result(connection, root, selected, history)
        if context.time.known_at > cutoff:
            raise ValueError("source was not known at the retrospective label cutoff")
        resource = context.provenance.source_resource_id
        if resource not in normalized:
            normalized[resource] = normalize_resource(context, "fixtures", raw)
        result = normalized[resource]
        # The existing normalizer owns source parsing, statuses and observation contracts.
        observations = [
            o
            for o in result.observations
            if isinstance(o, (FixtureObservationV2, ResultObservationV2))
            and o.fixture.provider_native_id == selected["native_fixture_id"]
        ]
        scores = [o for o in observations if isinstance(o, ResultObservationV2)]
        if len(observations) != 2 or len(scores) != 1 or scores[0].score_basis != "REGULATION_90":
            raise ValueError("normalizer did not produce one exact fixture and regulation result")
        reports.append(
            {
                "fixture_id": selected["fixture_id"],
                "native_fixture_id": selected["native_fixture_id"],
                "competition_id": selected["competition_id"],
                "season_id": selected["season_id"],
                "source_resource_id": str(resource),
                "source_sha256": context.provenance.source_sha256,
                "source_record_key": f"json:/response/{index}",
                "kickoff_utc": history["kickoff_at"],
                "source_known_at": context.time.known_at.isoformat(),
                "history_known_at": history["known_at"],
                "history_decision_id": selected["history_decision"]["decision_id"],
                "regulation_goals": native["goals"],
                "native_halftime": native["score"]["halftime"],
                "observations": [o.to_dict() for o in observations],
                "observation_sha256": [o.sha256 for o in observations],
                "label_qualification": "RESEARCH_TARGET_QUALIFIED",
                "research_target_contract": "ResultObservationV2 / FINISHED / REGULATION_90",
                "bookmaker_settlement_equivalent": False,
                "same_fixture_pre_match_feature_eligible": False,
            }
        )
    return {
        "pilot_sha256": pilot_sha256,
        "knowledge_cutoff": cutoff.astimezone(UTC).isoformat(),
        "fixtures": reports,
        "qualified_canonical_fixtures": len(reports),
        "qualified_score_pairs": len(reports),
        "qualified_scalar_goal_labels": 2 * len(reports),
        "source_native_halftime_scalar_labels": sum(
            value is not None for row in reports for value in row["native_halftime"].values()
        ),
        "bookmaker_equivalent_labels": 0,
        "new_identity_admissions": 0,
        "operating_writes": 0,
        "provider_requests": 0,
        "models_fitted": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--pilot-sha256", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args(argv)
    raw = args.pilot.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.pilot_sha256:
        raise ValueError("frozen pilot checksum mismatch")
    pilot = json.loads(raw)
    with psycopg.connect(args.database_url, options="-c default_transaction_read_only=on") as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        report = audit_pilot(c, args.source_root, pilot, args.pilot_sha256)
    payload = canonical_json_bytes(report) + b"\n"
    artifact = ImmutableFileStore(args.artifact_root).publish(
        "accepted-history/" + hashlib.sha256(payload).hexdigest() + ".json", payload
    )
    print(json.dumps({"path": str(artifact.path), "sha256": artifact.sha256}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
