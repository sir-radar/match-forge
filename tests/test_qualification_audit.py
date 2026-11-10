from datetime import UTC, datetime
from uuid import UUID

from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext
from football.providers.normalization.pipeline import normalize_resource

from scripts.audit_v4_qualification import resource_matrix


def test_matrix_keeps_native_counts_separate_from_qualification():
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "espn", None, UUID(int=1), UUID(int=2), "a" * 64, "json:/players"
        ),
        time=ObservationTime(
            observed_at=datetime(2026, 11, 1, tzinfo=UTC),
            acquired_at=datetime(2026, 11, 1, tzinfo=UTC),
            known_at=datetime(2026, 11, 1, tzinfo=UTC),
        ),
        resource_key="scoreboard",
    )
    import hashlib
    from dataclasses import replace

    raw = b'{"leagues":[],"events":[]}'
    context = replace(
        context,
        provenance=replace(context.provenance, source_sha256=hashlib.sha256(raw).hexdigest()),
    )
    result = normalize_resource(context, "scoreboard", raw)
    row = resource_matrix("scoreboard", context, result.observations)
    assert row["normalized_records"] == 0
    assert row["historical_eligibility"] == "MISSING_PROOF"
    assert row["market_target_eligibility"] == "MISSING_PROOF"
    assert row["native_fixtures"] == 0
    assert row["player_identity_status"] == "NOT_APPLICABLE"


def test_matrix_does_not_merge_resource_scoped_anonymous_references():
    from football.contracts.observations_v2 import (
        EntityReferenceV2,
        ObservationVersionsV2,
        PlayerObservationV2,
    )

    clock = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "espn", None, UUID(int=1), UUID(int=2), "a" * 64, "json:/players"
        ),
        time=ObservationTime(observed_at=clock, acquired_at=clock, known_at=clock),
        resource_key="players",
    )
    players = tuple(
        PlayerObservationV2(
            provenance=context.provenance,
            time=context.time,
            versions=ObservationVersionsV2(adapter_version="test", normalizer_version="test"),
            player=EntityReferenceV2(native, source_record_key=str(i)),
            name="Same Name",
        )
        for i, native in enumerate(["one", "two", None])
    )
    row = resource_matrix("players", context, players)
    assert row["native_players"] == 2
    assert row["anonymous_player_references"] == 1
    assert row["player_identity_status"] == "MISSING_PROOF"


def test_audit_serializes_postgres_numeric_byte_totals(tmp_path):
    from contextlib import nullcontext
    from decimal import Decimal

    from football.contracts.source import canonical_json_bytes

    from scripts.audit_v4_qualification import audit_database

    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.rows[0]

    class Connection:
        def transaction(self):
            return nullcontext()

        def execute(self, query):
            if isinstance(query, str) and "current_database()" in query:
                return Cursor([("test", datetime(2026, 11, 1, tzinfo=UTC), "on")])
            if isinstance(query, str) and "sum(r.size_bytes)" in query:
                return Cursor([("api_football", 1, Decimal("123"))])
            if isinstance(query, str) and "array_agg" in query:
                return Cursor([])
            return Cursor([(0,)])

    report = audit_database(Connection(), tmp_path, tmp_path)
    assert b'"bytes":123' in canonical_json_bytes(report)


def test_pilot_clocks_keep_local_dates_and_late_knowledge_separate():
    from scripts.inspect_v4_pilot import match_clocks

    clock = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "statsbomb_open_data", None, UUID(int=1), UUID(int=2), "a" * 64, "json:/0"
        ),
        time=ObservationTime(observed_at=clock, acquired_at=clock, known_at=clock),
        resource_key="data/matches/2/27.json",
    )
    match = {
        "match_id": 1,
        "match_date": "2015-08-08",
        "kick_off": "15:00:00.000",
        "last_updated": "2024-01-01T12:00:00",
    }
    report = match_clocks(match, context)
    assert report["verified_utc_kickoff"] is None
    assert report["provider_observation_time"] is None
    assert report["source_publication_time"] is None
    assert report["provider_update_raw"] == match["last_updated"]
    assert report["matchforge_acquisition_time"] == clock.isoformat()
    assert report["own_target_feature_use_allowed"] is False
    match.pop("kick_off")
    match["last_updated"] = "2024-01-01T12:00:00Z"
    report = match_clocks(match, context)
    assert report["native_local_kickoff"] is None
    assert report["verified_utc_kickoff"] is None
    assert report["provider_observation_time"] is None
    assert report["provider_updated_at"] == "2024-01-01T12:00:00+00:00"


def test_player_audit_keeps_missing_roles_minutes_and_team_conflicts_unqualified():
    import json

    from scripts.inspect_v4_pilot import lineup_records

    clock = datetime(2026, 11, 1, tzinfo=UTC)
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "statsbomb_open_data", None, UUID(int=1), UUID(int=2), "a" * 64, "json:/0"
        ),
        time=ObservationTime(observed_at=clock, acquired_at=clock, known_at=clock),
        resource_key="data/lineups/1.json",
    )
    position = {
        "position": "Goalkeeper",
        "from": "00:00",
        "to": "90:00",
        "from_period": 1,
        "to_period": 2,
        "start_reason": "Starting XI",
    }
    lineup = [
        {
            "team_id": 10,
            "team_name": "Home",
            "lineup": [
                {"player_id": 1, "player_name": "Same Name", "positions": [position], "cards": []},
                {
                    "player_id": 3,
                    "player_name": "Sub",
                    "positions": [
                        {
                            **position,
                            "from": "70:00",
                            "from_period": 2,
                            "start_reason": "Substitution - On (Tactical)",
                        }
                    ],
                    "cards": [],
                },
            ],
        },
        {
            "team_id": 20,
            "team_name": "Away",
            "lineup": [
                {"player_id": 2, "player_name": "Same Name", "positions": [], "cards": []},
            ],
        },
    ]
    match = {
        "home_team": {"home_team_id": 10},
        "away_team": {"away_team_id": 20},
        "match_date": "2015-08-08",
    }
    rows = lineup_records("1", context, json.dumps(lineup).encode(), match)
    assert [row["native_appearance"] for row in rows] == [
        "STARTED",
        "SUBSTITUTE_APPEARANCE",
        "UNKNOWN",
    ]
    assert {row["native_player_id"] for row in rows} == {"1", "2", "3"}
    assert all(row["verified_minutes"] is None for row in rows)
    assert all(row["continuous_membership_interval"] is None for row in rows)
    assert all(row["pre_match_lineup_known"] is False for row in rows)
    lineup[1]["team_id"] = 30
    rows = lineup_records("1", context, json.dumps(lineup).encode(), match)
    assert all(row["source_relationship_status"] == "CONTRADICTORY" for row in rows)


def test_blocked_projection_rejects_mismatched_or_qualified_evidence():
    from copy import deepcopy

    import pytest

    from scripts.project_v4_qualification import blocked_population

    header = {
        "status": "BLOCKED_WITH_EVIDENCE",
        "match_resource_id": "01a051db-5a13-7417-b9b5-247d08f3b82f",
    }
    identity = {
        **header,
        "fixtures": [{"native_fixture_id": "one", "current_resolution_decisions": []}],
        "owner_mapping_checks": [{"admitted_proof": None}],
    }
    timing = {**header, "clocks": [{"native_fixture_id": "one"}], "qualified_market_labels": 0}
    players = {
        **header,
        "records": [{"native_fixture_id": "one"}],
        "canonical_identity_admissions": 0,
    }
    assert blocked_population(identity, timing, players) == {"one"}
    changed = deepcopy(timing)
    changed["clocks"][0]["native_fixture_id"] = "another"
    with pytest.raises(ValueError, match="same nonempty"):
        blocked_population(identity, changed, players)
    changed = deepcopy(identity)
    changed["owner_mapping_checks"][0]["admitted_proof"] = {"id": "accepted"}
    with pytest.raises(ValueError, match="admitted evidence"):
        blocked_population(changed, timing, players)
    changed = {**timing, "qualified_market_labels": 1}
    with pytest.raises(ValueError, match="cannot be replaced"):
        blocked_population(identity, changed, players)
