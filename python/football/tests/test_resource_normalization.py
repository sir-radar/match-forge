from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult, count
from football.providers.normalization.pipeline import normalize_resource

NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)
SOURCE = UUID("794637be-a42e-4f7b-a06c-869bf010a4bf")


def normalize(
    provider: str,
    resource: str,
    payload: object,
    *,
    v3_contracts: tuple[str, ...] = (),
    **scope: str,
) -> NormalizationResult:
    raw = json.dumps(payload).encode()
    context = NormalizationContext(
        provenance=ObservationProvenance(
            provider, None, SOURCE, SOURCE, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        resource_key=(
            f"data/events/{scope.get('fixture_native_id')}.json"
            if provider == "statsbomb_open_data"
            else f"fixture-{scope.get('fixture_native_id')}-injuries"
            if provider == "api_football"
            else f"match-{scope.get('fixture_native_id')}-players"
            if provider == "pitchapi"
            else "test-resource"
        ),
        **scope,
    )
    result = normalize_resource(context, resource, raw)
    assert result == normalize_resource(context, resource, raw)
    for item in result.observations:
        assert item.provenance.source_resource_id == SOURCE
        assert item.provenance.source_sha256 == hashlib.sha256(raw).hexdigest()
        assert item.versions.observation_contract_version == (
            "3" if item.CONTRACT in v3_contracts else "2"
        )
        assert item.versions.normalizer_version
        assert item.time.known_at == NOW
    return result


def test_pitchapi_fixture_and_result_are_separate_and_retain_provider_time() -> None:
    updated = (NOW - timedelta(hours=1)).isoformat()
    row = {
        "id": "m_abcdef",
        "time_utc": NOW.isoformat(),
        "status": "finished",
        "league": {"id": "l_abcdef", "name": "League"},
        "home_team": {"id": "t_abcdef", "name": "Home"},
        "away_team": {"id": "t_ghijkl", "name": "Away"},
        "score_home": 2,
        "score_away": 0,
        "updated_at": updated,
    }
    result = normalize("pitchapi", "fixtures", {"data": {"matches": [row]}})
    fixture = next(item for item in result.observations if item.CONTRACT == "FixtureObservationV2")
    score = next(item for item in result.observations if item.CONTRACT == "ResultObservationV2")
    assert "home_goals" not in fixture.to_dict()
    assert score.to_dict()["home_goals"] == 2
    assert score.to_dict()["score_basis"] == "UNKNOWN"
    assert fixture.time.provider_updated_at == datetime.fromisoformat(updated)
    assert json.loads(fixture.to_bytes())["home_team"]["canonical_id"] is None
    row["status"] = "new-provider-status"
    rejected = normalize("pitchapi", "fixtures", {"data": {"matches": [row]}})
    assert not rejected.observations and rejected.findings


def test_shots_keep_missing_coordinates_and_zero_xg_and_quarantine_invalid_xg() -> None:
    shots = [
        {"id": "s_one", "team_id": "t_abcdef", "expected_goals": 0, "x": 43.2, "y": 10},
        {"id": "s_two", "team_id": "t_abcdef", "expected_goals": 1.1},
        {"id": "s_three", "team_id": "t_abcdef"},
    ]
    result = normalize(
        "pitchapi",
        "shots",
        {"data": {"periods": [{"period": "FirstHalf", "shots": shots}]}},
        fixture_native_id="m_abcdef",
    )
    items = [o.to_dict() for o in result.observations if o.CONTRACT == "ShotObservationV2"]
    assert len(items) == 2
    assert items[0]["expected_goals"] == 0 and items[1]["expected_goals"] is None
    assert all(item["x_norm"] is None and item["y_norm"] is None for item in items)
    xg = [o for o in result.observations if o.CONTRACT == "ExpectedGoalsObservationV2"]
    assert len(xg) == 1 and xg[0].to_dict()["scope"] == "SHOT"
    assert {f.rule_code for f in result.findings} >= {
        "MF_NORM_COORDINATE_FRAME_UNKNOWN",
        "MF_NORM_OBSERVATION_CONTRACT_INVALID",
    }


def test_pitchapi_lineup_coach_without_id_uses_source_field_and_unknown_prediction() -> None:
    side = {
        "confirmed": False,
        "formation": "4-3-3",
        "coach": {"name": "Coach"},
        "starters": [{"player_id": "p_abcdef", "name": "Player", "position_id": 11}],
        "subs": [],
    }
    result = normalize(
        "pitchapi",
        "lineups",
        {"data": {"home_team": {"id": "t_abcdef", "name": "Home"}, "home": side}},
        fixture_native_id="m_abcdef",
    )
    lineup = next(
        json.loads(o.to_bytes()) for o in result.observations if o.CONTRACT == "LineupObservationV2"
    )
    assert lineup["lineup_mode"] == "UNKNOWN"
    assert lineup["coach"]["provider_native_id"] is None
    assert lineup["coach"]["source_record_key"] == "json:/data/home/coach"
    assert lineup["players"][0]["position"] is None
    assert not any(o.CONTRACT == "FormationObservationV2" for o in result.observations)
    assert any(f.rule_code == "MF_NORM_POSITION_MAPPING_UNKNOWN" for f in result.findings)


def test_pitchapi_statistics_are_named_and_unknown_measurements_are_reported() -> None:
    payload = {
        "data": {
            "home_team": {"id": "t_abcdef"},
            "away_team": {"id": "t_ghijkl"},
            "periods": [
                {
                    "period": "All",
                    "groups": [
                        {
                            "items": [
                                {"key": "ball_possession", "home": "60%", "away": "40%"},
                                {"key": "corners", "home": "0", "away": None},
                                {"key": "new_metric", "home": "1", "away": "2"},
                            ]
                        }
                    ],
                }
            ],
        }
    }
    result = normalize("pitchapi", "statistics", payload, fixture_native_id="m_abcdef")
    stats = [o.to_dict() for o in result.observations]
    assert len(stats) == 2 and stats[0]["possession"] == 60 and stats[0]["corners"] == 0
    assert stats[1]["corners"] is None
    assert all("metric" not in o and "value" not in o for o in stats)
    assert any(f.rule_code == "MF_NORM_STATISTIC_UNSUPPORTED" for f in result.findings)


@pytest.mark.parametrize("value", [True, -1, "1.5", "NaN", "Infinity", "bad"])
def test_invalid_counts_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        count(value)


def test_counts_preserve_large_integers_without_float_rounding() -> None:
    assert count("9007199254740993") == 9007199254740993


def test_source_checksum_unknown_route_and_duplicate_json_are_not_silently_accepted() -> None:
    context = NormalizationContext(
        provenance=ObservationProvenance("pitchapi", None, SOURCE, SOURCE, "a" * 64),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        resource_key="test",
    )
    with pytest.raises(ValueError, match="checksum"):
        normalize_resource(context, "fixtures", b"{}")
    unsupported = normalize("pitchapi", "unknown", {})
    assert (
        not unsupported.observations
        and unsupported.findings[0].rule_code == "MF_NORM_RESOURCE_UNSUPPORTED"
    )
    raw = b'{"data":{},"data":{}}'
    with pytest.raises(ValueError, match="duplicate"):
        normalize_resource(
            replace(
                context,
                provenance=replace(
                    context.provenance, source_sha256=hashlib.sha256(raw).hexdigest()
                ),
            ),
            "fixtures",
            raw,
        )


def test_api_football_availability_uses_nested_native_fields_without_inventing_injury() -> None:
    rows = [
        {
            "player": {
                "id": 7,
                "name": "Player",
                "type": "Missing Fixture",
                "reason": "Personal reasons",
            },
            "team": {"id": 1},
            "fixture": {"id": 42},
        },
        {"player": {"id": 8, "type": "Doubtful"}, "team": {"id": 1}},
        {"player": {"id": 9, "type": "new reason"}, "team": {"id": 1}},
    ]
    result = normalize("api_football", "availability", {"response": rows}, fixture_native_id="42")
    items = [o.to_dict() for o in result.observations if o.CONTRACT == "AvailabilityObservationV2"]
    assert len(items) == 2
    assert items[0]["availability_type"] == "OTHER"
    assert items[0]["availability_state"] == "UNAVAILABLE_OTHER"
    assert items[1]["availability_state"] == "AVAILABILITY_UNVERIFIED"
    assert any(f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID" for f in result.findings)


def test_api_football_errors_and_wrong_fixture_are_quarantined() -> None:
    result = normalize(
        "api_football",
        "lineups",
        {"errors": {"plan": "unavailable"}, "response": []},
        fixture_native_id="42",
    )
    assert not result.observations and result.findings
    result = normalize(
        "api_football",
        "availability",
        {
            "response": [
                {
                    "player": {"id": 7, "type": "Missing Fixture"},
                    "team": {"id": 1},
                    "fixture": {"id": 43},
                }
            ]
        },
        fixture_native_id="42",
    )
    assert not result.observations and result.findings


def test_fotmob_detail_uses_actual_source_fields_and_keeps_missing_resources_empty() -> None:
    payload = {
        "general": {
            "matchId": "42",
            "leagueId": 47,
            "homeTeam": {"id": 1, "name": "Home"},
            "awayTeam": {"id": 2, "name": "Away"},
        },
        "header": {
            "status": {
                "utcTime": NOW.isoformat(),
                "started": True,
                "finished": True,
                "cancelled": False,
                "scoreStr": "2 - 0",
                "reason": {"short": "FT"},
            }
        },
        "content": {"lineup": None, "stats": None, "shotmap": None, "matchFacts": None},
    }
    result = normalize("fotmob", "fixtures", payload)
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["home_team"]["source_record_key"] == "json:/general/homeTeam"
    score = next(o.to_dict() for o in result.observations if o.CONTRACT == "ResultObservationV2")
    assert score["score_basis"] == "REGULATION_90" and score["away_goals"] == 0
    for resource in ("lineups", "statistics", "shots", "events"):
        empty = normalize("fotmob", resource, payload, fixture_native_id="42")
        assert not empty.observations and not empty.findings


def test_fotmob_nullable_event_player_is_native_missing_identity() -> None:
    payload = {
        "general": {"matchId": "42", "homeTeam": {"id": 1}, "awayTeam": {"id": 2}},
        "content": {
            "matchFacts": {
                "events": {
                    "events": [
                        {
                            "type": "Substitution",
                            "eventId": 9,
                            "time": 60,
                            "isHome": False,
                            "player": {"id": None},
                        },
                        {"type": "new type", "eventId": 10, "player": None},
                    ]
                }
            }
        },
    }
    result = normalize("fotmob", "events", payload, fixture_native_id="42")
    events = [json.loads(o.to_bytes()) for o in result.observations]
    assert len(events) == 1 and events[0]["event_type"] == "SUBSTITUTION"
    assert events[0]["team"]["provider_native_id"] == "2"
    assert events[0]["player"]["provider_native_id"] is None
    assert any(f.rule_code == "MF_NORM_EVENT_TYPE_UNKNOWN" for f in result.findings)


def test_openfootball_never_uses_names_as_identity_and_keeps_result_separate() -> None:
    result = normalize(
        "openfootball",
        "results",
        {
            "name": "League",
            "matches": [
                {
                    "date": "2026-10-15",
                    "team1": "Home",
                    "team2": {"name": "Away"},
                    "score": {"ft": [0, 0]},
                }
            ],
        },
        competition_native_id="eng.1",
        season_label="2026-27",
    )
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["home_team"]["provider_native_id"] is None
    assert fixture["away_team"]["provider_native_id"] is None
    assert fixture["fixture"]["provider_native_id"] is None
    assert fixture["kickoff_precision"] == "DATE_ONLY"
    assert fixture["fixture"]["source_record_key"] == "json:/matches/0"
    assert any(o.CONTRACT == "ResultObservationV2" for o in result.observations)


def normalize_csv(resource: str, raw: bytes) -> NormalizationResult:
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "football_data_uk", None, SOURCE, SOURCE, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        resource_key="mmz4281/2526/E0.csv",
        competition_native_id="E0",
        season_label="2025-26",
    )
    return normalize_resource(context, resource, raw)


def test_csv_preserves_cp1252_names_and_never_uses_names_as_native_ids() -> None:
    raw = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HC,AC,B365H,B365D,B365A\n"
        "E0,15/10/2026,Caf\xe9,Away,0,1,A,0,,2.0,3.0,4.0\n"
    ).encode("cp1252")
    result = normalize_csv("results", raw)
    assert not result.findings
    team = next(o.to_dict() for o in result.observations if o.CONTRACT == "TeamObservationV2")
    assert team["name"] == "Caf\xe9"
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["home_team"]["provider_native_id"] is None
    assert fixture["home_team"]["source_record_key"] == "csv:record/1/HomeTeam"
    stats = normalize_csv("statistics", raw)
    assert len(stats.observations) == 1 and stats.observations[0].to_dict()["corners"] == 0
    odds = normalize_csv("odds", raw)
    assert len(odds.observations) == 1 and odds.observations[0].CONTRACT == "OddsObservationV2"
    assert "home_goals" not in odds.observations[0].to_dict()


@pytest.mark.parametrize(
    "raw",
    [
        b"Div,Div\nE0,E0\n",
        b"Div,Date\nE0\n",
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,15/10/2026,Home,Away,1,0,A\n",
    ],
)
def test_invalid_csv_shapes_or_contradictory_results_have_findings(raw: bytes) -> None:
    result = normalize_csv("results", raw)
    assert not result.observations and result.findings


def test_matching_duplicate_statistics_corroborate_but_conflicts_remove_the_field() -> None:
    payload = {
        "data": {
            "home_team": {"id": "t_a"},
            "away_team": {"id": "t_b"},
            "periods": [
                {
                    "period": "All",
                    "groups": [
                        {
                            "items": [
                                {"key": "corners", "home": 2, "away": 3},
                                {"key": "corners", "home": 2, "away": 4},
                            ]
                        }
                    ],
                }
            ],
        }
    }
    result = normalize("pitchapi", "statistics", payload, fixture_native_id="m_abcdef")
    assert len(result.observations) == 1
    assert result.observations[0].to_dict()["corners"] == 2
    assert {f.rule_code for f in result.findings} == {
        "MF_NORM_STATISTIC_REPEATED",
        "MF_NORM_STATISTIC_DUPLICATE",
    }


def test_football_data_org_awarded_result_does_not_become_played_regulation() -> None:
    row = {
        "id": 42,
        "utcDate": NOW.isoformat(),
        "status": "AWARDED",
        "competition": {"id": 7},
        "homeTeam": {"id": 1},
        "awayTeam": {"id": 2},
        "score": {"duration": "REGULAR", "fullTime": {"home": None, "away": None}},
    }
    result = normalize("football_data_org", "fixtures", {"matches": [row]})
    score = next(o.to_dict() for o in result.observations if o.CONTRACT == "ResultObservationV2")
    assert score["status"] == "AWARDED" and score["home_goals"] is None


def test_football_data_org_standing_preserves_negative_points_and_total_scope() -> None:
    row = {
        "position": 1,
        "team": {"id": 1},
        "playedGames": 0,
        "won": 0,
        "draw": 0,
        "lost": 0,
        "points": -3,
        "goalsFor": 0,
        "goalsAgainst": 0,
        "goalDifference": 0,
    }
    result = normalize(
        "football_data_org",
        "standings",
        {
            "competition": {"id": 7},
            "standings": [{"type": "TOTAL", "table": [row]}, {"type": "HOME", "table": [row]}],
        },
        season_label="2026-27",
    )
    assert len(result.observations) == 1 and result.observations[0].to_dict()["points"] == -3
    assert result.findings[0].rule_code == "MF_NORM_STANDING_SCOPE_UNSUPPORTED"


def test_statsbomb_shots_use_verified_120x80_frame_and_keep_event_seconds() -> None:
    row = {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "index": 1,
        "period": 1,
        "timestamp": "00:01:03.000",
        "minute": 1,
        "second": 3,
        "type": {"id": 16, "name": "Shot"},
        "team": {"id": 1, "name": "Team"},
        "player": {"id": 7, "name": "Player"},
        "location": [60, 40],
        "shot": {"statsbomb_xg": 0, "outcome": {"name": "Saved"}},
    }
    result = normalize("statsbomb_open_data", "shots", [row], fixture_native_id="42")
    item = next(o.to_dict() for o in result.observations if o.CONTRACT == "ShotObservationV2")
    assert item["x_norm"] == 0.5 and item["y_norm"] == 0.5 and item["second"] == 3
    assert item["expected_goals"] == 0 and item["outcome"] == "SAVED"
    row["location"] = [121, 40]
    rejected = normalize("statsbomb_open_data", "shots", [row], fixture_native_id="42")
    assert not rejected.observations and rejected.findings


def test_scope_mismatch_and_nonfinite_additive_fields_are_rejected() -> None:
    result = normalize(
        "pitchapi",
        "shots",
        {"data": {"match_id": "m_other", "periods": []}},
        fixture_native_id="m_abcdef",
    )
    assert not result.observations and result.findings
    with pytest.raises(ValueError, match="finite"):
        normalize("pitchapi", "fixtures", {"data": {}, "new_field": float("inf")})


def test_fotmob_unknown_reason_never_defaults_to_scheduled() -> None:
    row = {
        "id": 42,
        "home": {"id": 1, "name": "Home"},
        "away": {"id": 2, "name": "Away"},
        "status": {
            "utcTime": NOW.isoformat(),
            "started": False,
            "finished": False,
            "cancelled": False,
            "reason": {"short": "NEW_STATUS"},
        },
    }
    result = normalize("fotmob", "fixtures", {"leagues": [{"id": 7, "matches": [row]}]})
    assert not result.observations and result.findings


def test_fotmob_league_results_preserve_native_split_season_and_scope() -> None:
    row = {
        "id": 42,
        "home": {"id": 1, "name": "Home"},
        "away": {"id": 2, "name": "Away"},
        "status": {
            "utcTime": NOW.isoformat(),
            "started": True,
            "finished": True,
            "cancelled": False,
            "reason": {"short": "FT"},
            "scoreStr": "0 - 0",
        },
    }
    payload = {
        "details": {"id": 7, "name": "League", "selectedSeason": "2024/2025 - Apertura"},
        "fixtures": {"allMatches": [row]},
    }
    result = normalize(
        "fotmob", "results", payload, competition_native_id="7", season_label="2024/2025 - Apertura"
    )
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["season_label"] == "2024/2025 - Apertura"
    assert fixture["competition"]["source_record_key"] == "json:/details"
    assert fixture["home_team"]["source_record_key"] == "json:/fixtures/allMatches/0/home"
    wrong = normalize(
        "fotmob", "results", payload, competition_native_id="7", season_label="2024/2025 - Clausura"
    )
    assert not wrong.observations and wrong.findings


@pytest.mark.parametrize("provider", ["fotmob", "pitchapi"])
def test_player_statistics_keep_zero_and_report_non_scalar_items(provider: str) -> None:
    stats = [
        {
            "stats": {
                "Goals": {"key": "goals", "stat": {"value": 0}},
                "Minutes played": {"key": "minutes_played", "stat": {"value": 0}},
                "Shotmap": {"data": []},
            }
        }
    ]
    payload: object = {
        "data": [
            {"player": {"id": "p_abcdef", "name": "Player"}, "team_id": "t_abcdef", "stats": stats}
        ]
    }
    if provider == "fotmob":
        payload = {
            "general": {"matchId": "42"},
            "content": {
                "playerStats": {"7": {"id": 7, "name": "Player", "teamId": 1, "stats": stats}}
            },
        }
    result = normalize(
        provider,
        "player_statistics",
        payload,
        fixture_native_id="42" if provider == "fotmob" else "m_abcdef",
    )
    item = next(
        o.to_dict() for o in result.observations if o.CONTRACT == "PlayerStatisticObservationV2"
    )
    assert item["goals"] == 0 and item["minutes_played"] == 0
    assert result.findings[0].rule_code == "MF_NORM_STATISTIC_UNSUPPORTED"


def test_zip_member_lineage_uses_exact_member_and_csv_record() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "E0.csv", "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,15/10/2026,Home,Away,0,0,D\n"
        )
    result = normalize_csv("results", buffer.getvalue())
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["fixture"]["source_record_key"] == "zip:E0.csv#csv:record/1"
    assert fixture["home_team"]["provider_native_id"] is None


def test_unbound_fixture_scope_is_quarantined() -> None:
    raw = b'{"data":{"periods":[{"shots":[{"team_id":"t_abcdef","id":"s_one"}]}]}}'
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "pitchapi", None, SOURCE, SOURCE, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        resource_key="unrelated-request",
        fixture_native_id="m_abcdef",
    )
    result = normalize_resource(context, "shots", raw)
    assert not result.observations and result.findings


def test_canonical_statsbomb_reader_verifies_manifest_and_exact_resource(tmp_path: Path) -> None:
    from dataclasses import replace

    from football.contracts.source import (
        ManifestResource,
        SourceManifest,
        SourceResource,
        SourceSnapshot,
    )
    from football.providers.normalization.cli import _statsbomb_payload
    from football.storage.raw import ImmutableFileStore, ImmutableRawStore

    root = tmp_path / "data"
    snapshot = SourceSnapshot(
        "statsbomb_open_data",
        "https://github.com/statsbomb/open-data",
        "a" * 40,
        "license",
        "https://example.com/license",
        "StatsBomb",
    )
    resource = SourceResource("data/events/42.json")
    raw = b"[]"
    written = ImmutableRawStore(root).publish(snapshot, resource, raw)
    entry = ManifestResource(
        resource.path,
        len(raw),
        written.sha256,
        written.relative_path,
        "application/json",
        "acquired",
    )
    manifest = SourceManifest(snapshot, NOW, (entry,))
    files = ImmutableFileStore(root)
    file = files.publish("manifests/test.json", manifest.to_bytes())
    row = (
        file.relative_path,
        file.sha256,
        "source",
        snapshot.source_git_sha,
        SOURCE,
        SOURCE,
        resource.path,
        written.sha256,
        len(raw),
    )
    assert _statsbomb_payload(root, row) == raw
    with pytest.raises(ValueError, match="manifest checksum"):
        _statsbomb_payload(root, (row[0], "f" * 64, *row[2:]))
    changed = replace(manifest, resources=(replace(entry, raw_path="elsewhere.json"),))
    alternate = files.publish("manifests/changed.json", changed.to_bytes())
    with pytest.raises(ValueError, match="pinned storage"):
        _statsbomb_payload(root, (alternate.relative_path, alternate.sha256, *row[2:]))
    written.path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="resource checksum"):
        _statsbomb_payload(root, row)


def test_normalization_report_preserves_findings_versions_and_determinism() -> None:
    from football.providers.normalization.cli import report_bytes

    raw = b'{"response":[],"errors":{"plan":"unsupported"}}'
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "api_football", None, SOURCE, SOURCE, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=NOW, acquired_at=NOW, known_at=NOW),
        resource_key="/fixtures",
    )
    result = normalize_resource(context, "fixtures", raw)
    report = report_bytes(context, "fixtures", result)
    assert report == report_bytes(context, "fixtures", normalize_resource(context, "fixtures", raw))
    parsed = json.loads(report)
    assert (
        parsed["source_resource_id"] == str(SOURCE)
        and parsed["source_sha256"] == context.provenance.source_sha256
    )
    assert (
        parsed["observations"] == []
        and parsed["findings"][0]["rule_code"] == "MF_NORM_RESOURCE_INVALID"
    )


def test_api_football_lineup_retains_anonymous_coach_and_confirmed_formation() -> None:
    result = normalize(
        "api_football",
        "lineups",
        {
            "response": [
                {
                    "team": {"id": 1},
                    "formation": "4-3-3",
                    "coach": {"id": None, "name": "Coach"},
                    "startXI": [{"player": {"id": 7, "name": "Player"}}],
                    "substitutes": [],
                }
            ]
        },
        fixture_native_id="42",
    )
    lineup = next(
        json.loads(o.to_bytes()) for o in result.observations if o.CONTRACT == "LineupObservationV2"
    )
    assert lineup["coach"]["provider_native_id"] is None and lineup["lineup_mode"] == "CONFIRMED"
    assert any(o.CONTRACT == "FormationObservationV2" for o in result.observations)


def test_statsbomb_competition_and_lineup_reuse_native_parser_rules() -> None:
    competition = {
        "competition_id": 7,
        "season_id": 8,
        "competition_name": "League",
        "country_name": "England",
        "season_name": "2025/2026",
    }
    result = normalize("statsbomb_open_data", "competitions", [competition])
    assert (
        len(result.observations) == 1
        and result.observations[0].to_dict()["season_label"] == "2025/2026"
    )
    squad = {
        "team_id": 1,
        "team_name": "Team",
        "lineup": [
            {
                "player_id": 7,
                "player_name": "Player",
                "positions": [
                    {
                        "position_id": 1,
                        "position": "Goalkeeper",
                        "from": "00:00",
                        "to": None,
                        "from_period": 1,
                        "to_period": None,
                        "start_reason": "Starting XI",
                        "end_reason": None,
                    }
                ],
                "cards": [],
            }
        ],
    }
    result = normalize("statsbomb_open_data", "lineups", [squad], fixture_native_id="42")
    lineup = next(
        json.loads(o.to_bytes()) for o in result.observations if o.CONTRACT == "LineupObservationV2"
    )
    assert lineup["players"][0]["role"] == "STARTER" and lineup["lineup_mode"] == "CONFIRMED"


def test_statsbomb_results_do_not_invent_utc_kickoffs() -> None:
    row = {
        "match_id": 42,
        "competition": {"competition_id": 7, "competition_name": "League"},
        "season": {"season_id": 8, "season_name": "2025/2026"},
        "home_team": {"home_team_id": 1, "home_team_name": "Home"},
        "away_team": {"away_team_id": 2, "away_team_name": "Away"},
        "home_score": 1,
        "away_score": 0,
        "match_date": "2026-10-15",
        "kick_off": "19:00:00.000",
        "last_updated": "2026-10-16T01:00:00",
    }
    result = normalize("statsbomb_open_data", "results", [row], competition_native_id="7")
    assert any(o.CONTRACT == "ResultObservationV2" for o in result.observations)
    assert not any(o.CONTRACT == "FixtureObservationV2" for o in result.observations)
    assert {f.rule_code for f in result.findings} == {
        "MF_NORM_PROVIDER_TIMESTAMP_UNRESOLVED",
        "MF_NORM_KICKOFF_TIMEZONE_UNRESOLVED",
    }


def test_statsbomb_unknown_event_and_shootout_stay_out_of_regulation_events() -> None:
    row = {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "index": 1,
        "period": 5,
        "timestamp": "00:00:01.000",
        "minute": 120,
        "second": 1,
        "type": {"id": 19, "name": "Substitution"},
        "team": {"id": 1, "name": "Team"},
    }
    result = normalize("statsbomb_open_data", "events", [row], fixture_native_id="42")
    assert (
        not result.observations
        and result.findings[0].rule_code == "MF_NORM_SHOOTOUT_EVENT_UNSUPPORTED"
    )
    row["period"] = 1
    row["type"] = {"id": 999, "name": "New event"}
    result = normalize("statsbomb_open_data", "events", [row], fixture_native_id="42")
    assert not result.observations and result.findings[0].rule_code == "MF_NORM_EVENT_TYPE_UNKNOWN"


def test_inherited_pitchapi_league_keeps_its_actual_source_pointer() -> None:
    row = {
        "id": "m_abcdef",
        "time_utc": NOW.isoformat(),
        "status": "scheduled",
        "home_team": {"id": "t_abcdef", "name": "Home"},
        "away_team": {"id": "t_ghijkl", "name": "Away"},
    }
    payload = {"data": {"league": {"id": "l_abcdef", "name": "League"}, "matches": [row]}}
    result = normalize("pitchapi", "fixtures", payload, competition_native_id="l_abcdef")
    fixture = next(
        json.loads(o.to_bytes())
        for o in result.observations
        if o.CONTRACT == "FixtureObservationV2"
    )
    assert fixture["competition"]["source_record_key"] == "json:/data/league"
    wrong = normalize("pitchapi", "fixtures", payload, competition_native_id="l_other")
    assert not wrong.observations and wrong.findings


def test_openfootball_unknown_local_timezone_is_quarantined() -> None:
    result = normalize(
        "openfootball",
        "fixtures",
        {"matches": [{"date": "2026-10-15", "time": "19:00", "team1": "Home", "team2": "Away"}]},
        competition_native_id="unknown.1",
    )
    assert not any(o.CONTRACT == "FixtureObservationV2" for o in result.observations)
    assert any("timezone" in f.message for f in result.findings)


def test_repeated_catalog_facts_keep_unique_identities_and_distinct_rows() -> None:
    row = {"date": "2026-10-15", "team1": "Home", "team2": "Away", "score": {"ft": [0, 0]}}
    result = normalize(
        "openfootball",
        "results",
        {"name": "League", "matches": [row, row]},
        competition_native_id="en.1",
    )
    assert len({o.observation_id for o in result.observations}) == len(result.observations)
    assert len([o for o in result.observations if o.CONTRACT == "CompetitionObservationV2"]) == 1
    assert len([o for o in result.observations if o.CONTRACT == "ResultObservationV2"]) == 2
    assert result.records_seen == 2


def test_statsbomb_unbooked_foul_does_not_require_optional_card_metadata() -> None:
    row = {
        "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "index": 1,
        "period": 1,
        "timestamp": "00:01:00.000",
        "minute": 1,
        "second": 0,
        "type": {"id": 22, "name": "Foul Committed"},
        "team": {"id": 1, "name": "Team"},
    }
    result = normalize("statsbomb_open_data", "events", [row], fixture_native_id="42")
    assert not result.observations
    assert [(f.rule_code, f.severity) for f in result.findings] == [
        ("MF_NORM_EVENT_TYPE_UNSUPPORTED", "INFO")
    ]
    row["foul_committed"] = None
    result = normalize("statsbomb_open_data", "events", [row], fixture_native_id="42")
    assert not result.observations
    assert result.findings[0].rule_code == "MF_NORM_SOURCE_RECORD_INVALID"
    row["foul_committed"] = {"card": {"name": "Yellow Card"}}
    result = normalize("statsbomb_open_data", "events", [row], fixture_native_id="42")
    assert result.observations[0].event_type == "YELLOW_CARD"
    assert not result.findings


def test_statsbomb_retained_match_context_keeps_referee_and_fixture_scoped_managers() -> None:
    row = {
        "match_id": 42,
        "competition": {"competition_id": 7, "competition_name": "League"},
        "season": {"season_id": 8, "season_name": "2015/2016"},
        "home_team": {
            "home_team_id": 1,
            "home_team_name": "Home",
            "managers": [
                {"id": 12, "name": "Same name"},
                {"id": True, "name": "Invalid ID"},
            ],
        },
        "away_team": {
            "away_team_id": 2,
            "away_team_name": "Away",
            "managers": [
                {"id": 13, "name": "Same name"},
            ],
        },
        "referee": {"id": 223, "name": "Reported referee"},
        "home_score": 1,
        "away_score": 0,
    }
    result = normalize(
        "statsbomb_open_data",
        "results",
        [row],
        competition_native_id="7",
        v3_contracts=("RefereeObservationV3",),
    )
    referee = next(o for o in result.observations if o.CONTRACT == "RefereeObservationV3")
    assert referee.fixture.provider_native_id == "42"
    assert referee.referee.provider_native_id == "223"
    assert referee.name == "Reported referee" and referee.time.event_time is None
    managers = [o for o in result.observations if o.CONTRACT == "CoachObservationV2"]
    assert [(o.coach.provider_native_id, o.team.provider_native_id) for o in managers] == [
        ("12", "1"),
        ("13", "2"),
    ]
    assert all(o.time.valid_from is None and o.time.valid_to is None for o in managers)
    assert len([f for f in result.findings if f.rule_code == "MF_NORM_SOURCE_RECORD_INVALID"]) == 1
    assert any(o.CONTRACT == "ResultObservationV2" for o in result.observations)
