import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from football.product.identity_admission import RetainedIdentityVerifier, _identity_index
from football.product.identity_trust import MappingEvidence, qualify_mapping


def match() -> dict[str, Any]:
    return {
        "match_id": 42,
        "competition": {"competition_id": 2, "competition_name": "Premier League"},
        "season": {"season_id": 27, "season_name": "2015/2016"},
        "match_date": "2015-08-08",
        "kick_off": "15:00:00.000",
        "home_team": {"home_team_id": 1, "home_team_name": "Home"},
        "away_team": {"away_team_id": 22, "away_team_name": "Away"},
        "home_score": 0,
        "away_score": 1,
    }


def test_statsbomb_exact_resource_scopes_and_entity_types() -> None:
    raw = json.dumps([match()]).encode()
    index = _identity_index("statsbomb_open_data", raw, "data/matches/2/27.json", "source")
    assert index == {
        ("competition", None): {"2"},
        ("team", None): {"1", "22"},
        ("match", None): {"42"},
    }
    assert index == _identity_index("statsbomb_open_data", raw, "data/matches/2/27.json", "source")
    assert _identity_index("statsbomb_open_data", raw, "api/matches/2/27.json", "source") == {}
    with pytest.raises(ValueError, match="source path"):
        _identity_index("statsbomb_open_data", raw, "data/matches/2/28.json", "source")


@pytest.mark.parametrize("rows", [[match(), match()], [{**match(), "match_id": True}], [{}]])
def test_statsbomb_rejects_ambiguous_or_malformed_native_rows(rows: list[dict[str, Any]]) -> None:
    with pytest.raises(ValueError):
        _identity_index(
            "statsbomb_open_data", json.dumps(rows).encode(), "data/matches/2/27.json", "x"
        )


def test_statsbomb_lineups_preserve_player_namespace() -> None:
    raw = json.dumps(
        [
            {
                "team_id": 1,
                "team_name": "Home",
                "lineup": [
                    {"player_id": 22, "player_name": "Player", "positions": [], "cards": []}
                ],
            },
            {"team_id": 2, "team_name": "Away", "lineup": []},
        ]
    ).encode()
    index = _identity_index("statsbomb_open_data", raw, "data/lineups/42.json", "source")
    assert index[("team", None)] == {"1", "2"}
    assert index[("player", None)] == {"22"}
    assert "22" not in index[("team", None)]
    assert ("competition", None) not in index


def registered_row(root: Path) -> tuple[Any, ...]:
    from football.contracts.source import (
        ManifestResource,
        SourceManifest,
        SourceResource,
        SourceSnapshot,
    )
    from football.storage.raw import ImmutableFileStore, ImmutableRawStore

    snapshot = SourceSnapshot(
        "statsbomb_open_data",
        "https://github.com/statsbomb/open-data",
        "a" * 40,
        "license",
        "https://example.com/license",
        "StatsBomb",
    )
    raw = json.dumps([match()]).encode()
    resource = SourceResource("data/matches/2/27.json")
    written = ImmutableRawStore(root).publish(snapshot, resource, raw)
    manifest = SourceManifest(
        snapshot,
        datetime(2026, 9, 1, tzinfo=UTC),
        (
            ManifestResource(
                resource.path,
                len(raw),
                written.sha256,
                written.relative_path,
                "application/json",
                "acquired",
            ),
        ),
    )
    file = ImmutableFileStore(root).publish("manifests/test.json", manifest.to_bytes())
    return (
        file.relative_path,
        file.sha256,
        "source",
        snapshot.source_git_sha,
        snapshot.source_git_sha,
        UUID(int=1),
        resource.path,
        written.sha256,
        len(raw),
        manifest.acquired_at,
    )


def test_statsbomb_registered_bytes_verify_without_granting_canonical_origin(
    tmp_path: Path,
) -> None:
    row = registered_row(tmp_path)
    verifier = RetainedIdentityVerifier(tmp_path)
    assert verifier.contains("statsbomb_open_data", "team", "1", None, row)
    assert not verifier.contains("statsbomb_open_data", "team", "42", None, row)
    assert verifier.contains("statsbomb_open_data", "competition", "2", None, row)
    verifier.seal()
    assert verifier.contains("statsbomb_open_data", "team", "1", None, row)
    evidence = MappingEvidence(
        "team", UUID(int=1), "statsbomb_open_data", "1", "deterministic", 1, "England", True, True
    )
    assert qualify_mapping(evidence) == ("UNRESOLVED", "UNSUPPORTED_ORIGIN_ALGORITHM")
    from dataclasses import replace

    assert qualify_mapping(replace(evidence, method="explicit_crosswalk"))[0] == "UNRESOLVED"


@pytest.mark.parametrize(
    "field,value", [(1, "f" * 64), (7, "f" * 64), (8, 1), (6, "data/matches/2/28.json")]
)
def test_statsbomb_registration_tampering_is_unverified(
    tmp_path: Path, field: int, value: object
) -> None:
    row = list(registered_row(tmp_path))
    row[field] = value
    assert not RetainedIdentityVerifier(tmp_path).contains(
        "statsbomb_open_data", "team", "1", None, tuple(row)
    )


def test_statsbomb_evidence_changed_after_preparation_requires_new_preview(tmp_path: Path) -> None:
    from football.product.identity_admission import RetainedEvidenceChanged

    row = registered_row(tmp_path)
    verifier = RetainedIdentityVerifier(tmp_path)
    assert verifier.contains("statsbomb_open_data", "team", "1", None, row)
    verifier.seal()
    with pytest.raises(RetainedEvidenceChanged):
        verifier.contains("statsbomb_open_data", "team", "1", None, (*row[:7], "b" * 64, *row[8:]))
    raw_file = next(tmp_path.rglob("27.json"))
    raw_file.write_bytes(b"[]")
    assert not RetainedIdentityVerifier(tmp_path).contains(
        "statsbomb_open_data", "team", "1", None, row
    )


def test_duplicate_json_identity_key_is_not_last_value_wins() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        _identity_index(
            "statsbomb_open_data",
            b'[{"match_id":42,"match_id":43}]',
            "data/matches/2/27.json",
            "source",
        )


def espn_summary() -> dict[str, Any]:
    return {
        "header": {
            "id": "704279",
            "season": {"year": 2024},
            "league": {"id": "700", "slug": "eng.1", "name": "Premier League"},
            "competitions": [
                {
                    "id": "704279",
                    "date": "2024-08-16T19:00Z",
                    "status": {
                        "type": {"name": "STATUS_FULL_TIME", "state": "post", "completed": True}
                    },
                    "competitors": [
                        {"id": "1", "homeAway": "home", "team": {"id": "1", "displayName": "Home"}},
                        {
                            "id": "22",
                            "homeAway": "away",
                            "team": {"id": "22", "displayName": "Away"},
                        },
                    ],
                }
            ],
        }
    }


def test_espn_summary_reads_exact_header_ids_only() -> None:
    value = espn_summary()
    value["news"] = {"team": {"id": "999"}, "league": {"id": "888"}}
    raw = json.dumps(value).encode()
    assert _identity_index("espn", raw, "eng.1/summary?event=704279", "source") == {
        ("competition", None): {"700"},
        ("team", None): {"1", "22"},
        ("match", None): {"704279"},
    }
    assert _identity_index("espn", raw, "eng.1/scoreboard", "source") == {}


@pytest.mark.parametrize(
    "path",
    ["eng.1/summary?event=42", "esp.1/summary?event=704279", "eng.1/summary?event=704279&event=42"],
)
def test_espn_summary_rejects_conflicting_resource_scope(path: str) -> None:
    with pytest.raises(ValueError):
        _identity_index("espn", json.dumps(espn_summary()).encode(), path, "source")


def test_espn_competitor_ids_cannot_be_taken_from_unrelated_nested_objects() -> None:
    value = espn_summary()
    value["header"]["competitions"][0]["competitors"][0]["team"]["id"] = "99"
    with pytest.raises(ValueError):
        _identity_index("espn", json.dumps(value).encode(), "eng.1/summary?event=704279", "source")


def test_registered_statsbomb_verification_returns_exact_immutable_resource_proof(
    tmp_path: Path,
) -> None:
    from typing import cast
    from unittest.mock import MagicMock

    from football.product.identity_admission import verify_source_identifier
    from psycopg import Connection

    row = registered_row(tmp_path)
    connection = MagicMock()
    connection.execute.return_value.fetchall.return_value = [row]
    verifier = RetainedIdentityVerifier(tmp_path)
    proof = verify_source_identifier(
        cast(Connection[Any], connection),
        tmp_path,
        UUID(int=2),
        "statsbomb_open_data",
        "team",
        "1",
        "England",
        verifier,
    )
    assert proof is not None
    assert proof["source_resource_id"] == str(row[5])
    assert proof["sha256"] == row[7]
    assert proof["manifest_classification"] == "BYTE_VERIFIED"
    assert proof == verify_source_identifier(
        cast(Connection[Any], connection),
        tmp_path,
        UUID(int=2),
        "statsbomb_open_data",
        "team",
        "1",
        "England",
        verifier,
    )
