from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Any, cast
from uuid import UUID

import psycopg
import pyarrow.parquet as pq
import pytest
from football.contracts import SourceResource, SourceSnapshot
from football.datasets import DatasetPublicationError, StatsBombEventDatasetPublisher
from football.forecasting.gate import Sprint2GateService
from football.forecasting.governance import EvaluationCorpusV1
from football.forecasting.lifecycle import LifecycleClaimError, Sprint2LifecycleClaimPublisher
from football.ingestion import (
    AcquisitionResult,
    CanonicalIngestionError,
    SourceAcquirer,
    SourceIntegrityError,
    StatsBombCanonicalIngestor,
)
from football.validation import QualityPolicy, StatsBombDatasetValidator
from jsonschema import validate as validate_json
from psycopg import Connection

DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest.fixture
def connection() -> Iterator[Connection[Any]]:
    with (
        psycopg.connect(DATABASE_URL) as database_connection,
        database_connection.transaction(force_rollback=True),
    ):
        yield database_connection


@dataclass
class FixtureProvider:
    source_git_sha: str
    payloads: dict[str, bytes]

    @property
    def snapshot(self) -> SourceSnapshot:
        return SourceSnapshot(
            provider="statsbomb_open_data",
            repository="https://github.com/statsbomb/open-data",
            source_git_sha=self.source_git_sha,
            license="StatsBomb Open Data license",
            license_url=(
                f"https://github.com/statsbomb/open-data/blob/{self.source_git_sha}/LICENSE.pdf"
            ),
            attribution="Data provided by StatsBomb",
        )

    def fetch(self, resource: SourceResource) -> bytes:
        return self.payloads[resource.path]


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _competition_payload() -> list[dict[str, object]]:
    return [
        {
            "competition_id": 43,
            "season_id": 106,
            "country_name": "International",
            "competition_name": "FIFA World Cup",
            "competition_gender": "male",
            "competition_youth": False,
            "competition_international": True,
            "season_name": "2022",
            "match_updated": "2026-05-04T01:48:57.914346",
            "match_updated_360": "2026-05-04T01:53:40.309717",
            "match_available_360": "2026-05-04T01:53:40.309717",
            "match_available": "2026-05-04T01:48:57.914346",
        }
    ]


def _match_payload(
    *,
    home_name: str = "Argentina",
    home_score: int = 3,
    away_score: int = 3,
) -> list[dict[str, object]]:
    return [
        {
            "match_id": 3869685,
            "match_date": "2022-12-18",
            "kick_off": "17:00:00.000",
            "competition": {
                "competition_id": 43,
                "country_name": "International",
                "competition_name": "FIFA World Cup",
            },
            "season": {"season_id": 106, "season_name": "2022"},
            "home_team": {
                "home_team_id": 779,
                "home_team_name": home_name,
                "home_team_gender": "male",
                "country": {"id": 11, "name": "Argentina"},
            },
            "away_team": {
                "away_team_id": 771,
                "away_team_name": "France",
                "away_team_gender": "male",
                "country": {"id": 78, "name": "France"},
            },
            "home_score": home_score,
            "away_score": away_score,
            "match_status": "available",
            "match_status_360": "available",
            "last_updated": "2024-12-16T10:15:11.055845",
            "last_updated_360": "2024-12-16T10:21:13.710934",
            "metadata": {
                "data_version": "1.1.0",
                "shot_fidelity_version": "2",
                "xy_fidelity_version": "2",
            },
            "match_week": 7,
            "competition_stage": {"id": 26, "name": "Final"},
        }
    ]


def _lineup_payload(
    *,
    home_team_id: int = 779,
    home_name: str = "Argentina",
    nickname: str = "Lionel Messi",
    nonmonotonic_position: bool = False,
) -> list[dict[str, object]]:
    return [
        {
            "team_id": home_team_id,
            "team_name": home_name,
            "lineup": [
                {
                    "player_id": 5503,
                    "player_name": "Lionel Andrés Messi Cuccittini",
                    "player_nickname": nickname,
                    "jersey_number": 10,
                    "country": {"id": 11, "name": "Argentina"},
                    "cards": [
                        {
                            "time": "51:21",
                            "card_type": "Yellow Card",
                            "reason": "Foul Committed",
                            "period": 1,
                        }
                    ],
                    "positions": [
                        {
                            "position_id": 17,
                            "position": "Right Wing",
                            "from": "115:32" if nonmonotonic_position else "00:00",
                            "to": "28:11" if nonmonotonic_position else "115:32",
                            "from_period": 4 if nonmonotonic_position else 1,
                            "to_period": 1 if nonmonotonic_position else 4,
                            "start_reason": "Starting XI",
                            "end_reason": "Tactical Shift",
                        }
                    ],
                },
                {
                    "player_id": 6312,
                    "player_name": "Franco Armani",
                    "player_nickname": None,
                    "jersey_number": 1,
                    "country": {"id": 11, "name": "Argentina"},
                    "cards": [],
                    "positions": [],
                },
            ],
        },
        {"team_id": 771, "team_name": "France", "lineup": []},
    ]


def _event_payload(*, second_type: str = "Pass") -> list[dict[str, object]]:
    return [
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "index": 2,
            "period": 1,
            "timestamp": "00:00:05.250",
            "minute": 0,
            "second": 5,
            "type": {"id": 30, "name": second_type},
            "possession_team": {"id": 779, "name": "Argentina"},
            "team": {"id": 779, "name": "Argentina"},
            "player": {"id": 5503, "name": "Lionel Andrés Messi Cuccittini"},
            "location": [60.0, 40.0],
        },
        {
            "id": "22222222-2222-4222-8222-222222222222",
            "index": 1,
            "period": 1,
            "timestamp": "00:00:00.000",
            "minute": 0,
            "second": 0,
            "type": {"id": 35, "name": "Starting XI"},
            "possession_team": {"id": 771, "name": "France"},
            "team": {"id": 771, "name": "France"},
        },
    ]


def _terminal_event_payload() -> list[dict[str, object]]:
    events = _event_payload()
    events.extend(
        (
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "index": 3,
                "period": 2,
                "timestamp": "00:50:00.000",
                "minute": 95,
                "second": 0,
                "type": {"id": 34, "name": "Half End"},
                "team": {"id": 779, "name": "Argentina"},
            },
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "index": 4,
                "period": 2,
                "timestamp": "00:50:00.000",
                "minute": 95,
                "second": 0,
                "type": {"id": 34, "name": "Half End"},
                "team": {"id": 771, "name": "France"},
            },
        )
    )
    return events


def _acquire_bundle(
    data_root: Path,
    *,
    source_git_sha: str,
    acquired_at: datetime,
    home_name: str = "Argentina",
    home_team_id: int = 779,
    nickname: str = "Lionel Messi",
    events: list[dict[str, object]] | None = None,
    nonmonotonic_position: bool = False,
    home_score: int = 3,
    away_score: int = 3,
    include_catalog: bool = True,
) -> AcquisitionResult:
    payloads = {
        "data/matches/43/106.json": _json_bytes(
            _match_payload(
                home_name=home_name,
                home_score=home_score,
                away_score=away_score,
            )
        ),
        "data/lineups/3869685.json": _json_bytes(
            _lineup_payload(
                home_team_id=home_team_id,
                home_name=home_name,
                nickname=nickname,
                nonmonotonic_position=nonmonotonic_position,
            )
        ),
    }
    if include_catalog:
        payloads["data/competitions.json"] = _json_bytes(_competition_payload())
    if events is not None:
        payloads["data/events/3869685.json"] = _json_bytes(events)
    provider = FixtureProvider(source_git_sha, payloads)
    resources = tuple(SourceResource(path) for path in payloads)
    return SourceAcquirer(data_root, clock=lambda: acquired_at).acquire(provider, resources)


def _provider_id(connection: Connection[Any]) -> UUID:
    with connection.cursor() as cursor:
        row = cursor.execute(
            "SELECT id FROM football.providers WHERE code = 'statsbomb_open_data'"
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def test_registers_source_and_ingests_canonical_hierarchy_idempotently(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquired_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="a" * 40,
        acquired_at=acquired_at,
    )
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)

    first = ingestor.ingest(acquisition)
    second = ingestor.ingest(acquisition)

    assert second == first
    assert first.competitions_seen == 1
    assert first.seasons_seen == 1
    assert first.teams_seen == 2
    assert first.players_seen == 2
    assert first.matches_seen == 1
    assert first.lineup_players_seen == 2
    assert first.position_stints_seen == 1
    assert first.cards_seen == 1

    provider_id = _provider_id(connection)
    count_queries = {
        "source snapshots": "SELECT count(*) FROM football.source_snapshots WHERE provider_id = %s",
        "source resources": """
            SELECT count(*) FROM football.source_resources AS resource
            JOIN football.source_snapshots AS snapshot ON snapshot.id = resource.source_snapshot_id
            WHERE snapshot.provider_id = %s
        """,
        "competitions": """
            SELECT count(*) FROM football.competition_provider_mappings
            WHERE provider_id = %s
        """,
        "seasons": """
            SELECT count(*) FROM football.season_provider_mappings
            WHERE provider_id = %s
        """,
        "teams": "SELECT count(*) FROM football.team_provider_mappings WHERE provider_id = %s",
        "players": "SELECT count(*) FROM football.player_provider_mappings WHERE provider_id = %s",
        "matches": "SELECT count(*) FROM football.match_provider_mappings WHERE provider_id = %s",
        "competition observations": """
            SELECT count(*) FROM football.competition_observations
            WHERE provider_id = %s
        """,
        "season observations": """
            SELECT count(*) FROM football.season_observations
            WHERE provider_id = %s
        """,
        "team observations": """
            SELECT count(*) FROM football.team_observations WHERE provider_id = %s
        """,
        "player observations": """
            SELECT count(*) FROM football.player_observations WHERE provider_id = %s
        """,
        "match observations": """
            SELECT count(*) FROM football.match_observations WHERE provider_id = %s
        """,
        "match team observations": """
            SELECT count(*) FROM football.match_team_participation_observations
            WHERE provider_id = %s
        """,
        "match player observations": """
            SELECT count(*) FROM football.match_player_participation_observations
            WHERE provider_id = %s
        """,
        "position stints": """
            SELECT count(*) FROM football.player_position_stints AS stint
            JOIN football.match_player_participation_observations AS observation
              ON observation.id = stint.match_player_observation_id
            WHERE observation.provider_id = %s
        """,
        "cards": """
            SELECT count(*) FROM football.player_cards AS card
            JOIN football.match_player_participation_observations AS observation
              ON observation.id = card.match_player_observation_id
            WHERE observation.provider_id = %s
        """,
    }
    expected_counts = [1, 3, 1, 1, 2, 2, 1, 1, 1, 2, 2, 1, 2, 2, 1, 1]
    with connection.cursor() as cursor:
        observed_counts = []
        for query in count_queries.values():
            row = cursor.execute(query, (provider_id,)).fetchone()
            assert row is not None
            observed_counts.append(row[0])
        assert observed_counts == expected_counts

        snapshot = cursor.execute(
            """
            SELECT status, manifest_path, manifest_sha256
            FROM football.source_snapshots
            WHERE provider_id = %s
            """,
            (provider_id,),
        ).fetchone()
        assert snapshot == (
            "validated",
            str(acquisition.manifest_path.relative_to(tmp_path)),
            acquisition.manifest_sha256,
        )
        assert list(
            cursor.execute(
                """
                SELECT resource.provider_path, resource.parse_status,
                       resource.validation_status
                FROM football.source_resources AS resource
                JOIN football.source_snapshots AS snapshot
                  ON snapshot.id = resource.source_snapshot_id
                WHERE snapshot.provider_id = %s
                ORDER BY resource.provider_path
                """,
                (provider_id,),
            )
        ) == [
            ("data/competitions.json", "parsed", "valid"),
            ("data/lineups/3869685.json", "parsed", "valid"),
            ("data/matches/43/106.json", "parsed", "valid"),
        ]
        assert cursor.execute(
            """
            SELECT provider_updated_at, provider_updated_at_raw
            FROM football.match_observations
            WHERE provider_id = %s
            """,
            (provider_id,),
        ).fetchone() == (None, "2024-12-16T10:15:11.055845")


def test_match_list_supplies_catalog_missing_competition_season_with_lineage(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="6" * 40,
        acquired_at=datetime(2026, 8, 30, 10, 0, tzinfo=UTC),
        include_catalog=False,
    )

    result = StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    assert result.competitions_seen == 1
    assert result.seasons_seen == 1
    with connection.cursor() as cursor:
        row = cursor.execute(
            """
            SELECT competition.provider_competition_id,
                   season.provider_season_id,
                   resource.provider_path
            FROM football.competition_observations AS competition
            JOIN football.season_observations AS season
              ON season.provider_id = competition.provider_id
             AND season.provider_competition_id = competition.provider_competition_id
            JOIN football.source_resources AS resource
              ON resource.id = competition.source_resource_id
            WHERE competition.provider_competition_id = '43'
              AND season.provider_season_id = '106'
            """
        ).fetchone()
    assert row == ("43", "106", "data/matches/43/106.json")


def test_preserves_conflicting_player_facts_without_selecting_a_winner(
    connection: Connection[Any], tmp_path: Path
) -> None:
    matches = _match_payload()
    second_match = _match_payload()[0]
    second_match["match_id"] = 3869686
    second_match["match_date"] = "2022-12-17"
    matches.append(second_match)
    for match in matches:
        match["home_score"] = 0
        match["away_score"] = 0

    first_lineup = _lineup_payload()
    second_lineup = _lineup_payload()
    conflicting_lineup = cast(list[dict[str, object]], second_lineup[0]["lineup"])
    conflicting_player = conflicting_lineup[0]
    conflicting_player["player_name"] = "Lionel Messi"
    conflicting_player["country"] = {"id": 68, "name": "England"}
    first_events = _event_payload()
    second_events = _event_payload()
    second_events[0]["id"] = "33333333-3333-4333-8333-333333333333"
    second_events[1]["id"] = "44444444-4444-4444-8444-444444444444"
    payloads = {
        "data/competitions.json": _json_bytes(_competition_payload()),
        "data/matches/43/106.json": _json_bytes(matches),
        "data/events/3869685.json": _json_bytes(first_events),
        "data/events/3869686.json": _json_bytes(second_events),
        "data/lineups/3869685.json": _json_bytes(first_lineup),
        "data/lineups/3869686.json": _json_bytes(second_lineup),
    }
    provider = FixtureProvider("8" * 40, payloads)
    acquisition = SourceAcquirer(
        tmp_path,
        clock=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    ).acquire(provider, tuple(SourceResource(path) for path in payloads))
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)

    first = ingestor.ingest(acquisition)
    second = ingestor.ingest(acquisition)

    assert second == first
    with connection.cursor() as cursor:
        canonical = cursor.execute(
            """
            SELECT full_name, nickname, country_provider_id, fact_status
            FROM football.player_observations
            WHERE source_snapshot_id = %s AND provider_player_id = '5503'
            """,
            (first.source_snapshot_id,),
        ).fetchone()
        variants = list(
            cursor.execute(
                """
                SELECT resource.provider_path, fact.full_name, fact.nickname,
                       fact.country_provider_id, fact.observation_kind
                FROM football.player_source_facts AS fact
                JOIN football.source_resources AS resource
                  ON resource.id = fact.source_resource_id
                WHERE fact.source_snapshot_id = %s
                  AND fact.provider_player_id = '5503'
                  AND fact.observation_kind = 'lineup'
                ORDER BY resource.provider_path
                """,
                (first.source_snapshot_id,),
            )
        )

    assert canonical == (None, "Lionel Messi", None, "conflicting")
    assert variants == [
        (
            "data/lineups/3869685.json",
            "Lionel Andrés Messi Cuccittini",
            "Lionel Messi",
            "11",
            "lineup",
        ),
        (
            "data/lineups/3869686.json",
            "Lionel Messi",
            "Lionel Messi",
            "68",
            "lineup",
        ),
    ]
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"
    validation = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
    ).validate(dataset.dataset_version_id)

    assert validation.status == "warnings"
    assert [finding.rule_code for finding in validation.findings] == [
        "SB_CONFLICTING_PLAYER_FACT",
        "SB_CONFLICTING_PLAYER_FACT",
    ]
    assert {finding.field_path for finding in validation.findings} == {
        "player.country_provider_id",
        "player.full_name",
    }


def test_new_snapshot_closes_current_observations_and_preserves_history(
    connection: Connection[Any], tmp_path: Path
) -> None:
    first_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    second_at = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)
    ingestor.ingest(_acquire_bundle(tmp_path, source_git_sha="b" * 40, acquired_at=first_at))
    ingestor.ingest(
        _acquire_bundle(
            tmp_path,
            source_git_sha="c" * 40,
            acquired_at=second_at,
            home_name="Argentina National Team",
            nickname="L. Messi",
        )
    )

    provider_id = _provider_id(connection)
    with connection.cursor() as cursor:
        team_history = list(
            cursor.execute(
                """
                SELECT name, known_from, known_to
                FROM football.team_observations
                WHERE provider_id = %s AND provider_team_id = '779'
                ORDER BY known_from
                """,
                (provider_id,),
            )
        )
        player_history = list(
            cursor.execute(
                """
                SELECT nickname, known_from, known_to
                FROM football.player_observations
                WHERE provider_id = %s AND provider_player_id = '5503'
                ORDER BY known_from
                """,
                (provider_id,),
            )
        )
        lineup_history = list(
            cursor.execute(
                """
                SELECT observation.known_from, observation.known_to
                FROM football.match_player_participation_observations AS observation
                JOIN football.match_player_participations AS participation
                  ON participation.id = observation.match_player_participation_id
                JOIN football.player_provider_mappings AS mapping
                  ON mapping.player_id = participation.player_id
                WHERE observation.provider_id = %s
                  AND mapping.provider_id = %s
                  AND mapping.provider_player_id = '5503'
                ORDER BY observation.known_from
                """,
                (provider_id, provider_id),
            )
        )

    assert team_history == [
        ("Argentina", first_at, second_at),
        ("Argentina National Team", second_at, None),
    ]
    assert player_history == [
        ("Lionel Messi", first_at, second_at),
        ("L. Messi", second_at, None),
    ]
    assert lineup_history == [(first_at, second_at), (second_at, None)]


def test_ingestion_is_atomic_when_lineup_does_not_belong_to_match(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="d" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        home_team_id=999,
    )

    with pytest.raises(CanonicalIngestionError, match="lineup team 999 does not play"):
        StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    with connection.cursor() as cursor:
        row = cursor.execute(
            "SELECT count(*) FROM football.source_snapshots WHERE source_revision = %s",
            ("d" * 40,),
        ).fetchone()
        assert row is not None and row[0] == 0


def test_ingestion_reverifies_raw_bytes_before_database_registration(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="e" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
    )
    raw_path = tmp_path / next(
        resource.raw_path
        for resource in acquisition.manifest.resources
        if resource.path == "data/competitions.json"
    )
    raw_path.write_bytes(b"[]")

    with pytest.raises(SourceIntegrityError, match="source resource checksum mismatch"):
        StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    with connection.cursor() as cursor:
        row = cursor.execute(
            "SELECT count(*) FROM football.source_snapshots WHERE source_revision = %s",
            ("e" * 40,),
        ).fetchone()
        assert row is not None and row[0] == 0


def test_distinct_manifest_scopes_at_one_revision_are_registered(
    connection: Connection[Any], tmp_path: Path
) -> None:
    source_git_sha = "f" * 40
    first_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    second_at = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    competitions = _json_bytes(_competition_payload())
    competition_provider = FixtureProvider(
        source_git_sha,
        {"data/competitions.json": competitions},
    )
    first = SourceAcquirer(tmp_path, clock=lambda: first_at).acquire(
        competition_provider,
        (SourceResource("data/competitions.json"),),
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(first)

    second = _acquire_bundle(
        tmp_path,
        source_git_sha=source_git_sha,
        acquired_at=second_at,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(second)

    provider_id = _provider_id(connection)
    with connection.cursor() as cursor:
        snapshots = list(
            cursor.execute(
                """
                SELECT source_identity, source_revision
                FROM football.source_snapshots
                WHERE provider_id = %s
                ORDER BY acquired_at
                """,
                (provider_id,),
            )
        )
        competition_count = cursor.execute(
            """
            SELECT count(*) FROM football.competition_provider_mappings
            WHERE provider_id = %s
            """,
            (provider_id,),
        ).fetchone()

    assert len(snapshots) == 2
    assert snapshots[0][0] != snapshots[1][0]
    assert {row[1] for row in snapshots} == {source_git_sha}
    assert competition_count is not None and competition_count[0] == 1


def test_lineup_only_scope_does_not_replace_richer_current_team_facts(
    connection: Connection[Any], tmp_path: Path
) -> None:
    source_git_sha = "1" * 40
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)
    ingestor.ingest(
        _acquire_bundle(
            tmp_path,
            source_git_sha=source_git_sha,
            acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        )
    )
    lineup_payload = _json_bytes(_lineup_payload())
    lineup_provider = FixtureProvider(
        source_git_sha,
        {"data/lineups/3869685.json": lineup_payload},
    )
    lineup_scope = SourceAcquirer(
        tmp_path,
        clock=lambda: datetime(2026, 8, 30, 8, 0, tzinfo=UTC),
    ).acquire(lineup_provider, (SourceResource("data/lineups/3869685.json"),))

    ingestor.ingest(lineup_scope)

    provider_id = _provider_id(connection)
    with connection.cursor() as cursor:
        rows = list(
            cursor.execute(
                """
                SELECT name, gender, country_provider_id, known_to
                FROM football.team_observations
                WHERE provider_id = %s AND provider_team_id = '779'
                ORDER BY known_from
                """,
                (provider_id,),
            )
        )
    assert rows == [("Argentina", "male", "11", None)]


def test_preserves_provider_position_span_when_periods_are_not_monotonic(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="7" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        nonmonotonic_position=True,
    )

    result = StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    with connection.cursor() as cursor:
        position_span = cursor.execute(
            """
            SELECT period_from, clock_from, period_to, clock_to
            FROM football.player_position_stints AS stint
            JOIN football.match_player_participation_observations AS observation
              ON observation.id = stint.match_player_observation_id
            WHERE observation.source_snapshot_id = %s
            """,
            (result.source_snapshot_id,),
        ).fetchone()
    assert position_span == (
        4,
        timedelta(minutes=115, seconds=32),
        1,
        timedelta(minutes=28, seconds=11),
    )


def test_ingests_event_catalog_in_source_order_idempotently(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="3" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
    )
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)

    first = ingestor.ingest(acquisition)
    second = ingestor.ingest(acquisition)

    assert second == first
    assert first.events_seen == 2
    provider_id = _provider_id(connection)
    with connection.cursor() as cursor:
        event_counts = cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM football.event_catalog AS catalog
                 JOIN football.event_provider_mappings AS mapping
                   ON mapping.event_id = catalog.id
                 WHERE mapping.provider_id = %s),
                (SELECT count(*) FROM football.event_provider_mappings
                 WHERE provider_id = %s),
                (SELECT count(*) FROM football.event_observations
                 WHERE provider_id = %s)
            """,
            (provider_id, provider_id, provider_id),
        ).fetchone()
        observations = list(
            cursor.execute(
                """
                SELECT event.provider_event_id, event.event_index,
                       event.provider_event_type, event.period, event.event_clock,
                       team.provider_team_id, player.provider_player_id,
                       possession.provider_team_id
                FROM football.event_observations AS event
                LEFT JOIN football.team_provider_mappings AS team
                  ON team.team_id = event.team_id AND team.provider_id = event.provider_id
                 AND team.valid_to IS NULL
                LEFT JOIN football.player_provider_mappings AS player
                  ON player.player_id = event.player_id
                 AND player.provider_id = event.provider_id AND player.valid_to IS NULL
                LEFT JOIN football.team_provider_mappings AS possession
                  ON possession.team_id = event.possession_team_id
                 AND possession.provider_id = event.provider_id
                 AND possession.valid_to IS NULL
                WHERE event.provider_id = %s
                ORDER BY event.event_index
                """,
                (provider_id,),
            )
        )
        resource_status = cursor.execute(
            """
            SELECT resource.parse_status, resource.validation_status, snapshot.status
            FROM football.source_resources AS resource
            JOIN football.source_snapshots AS snapshot
              ON snapshot.id = resource.source_snapshot_id
            WHERE snapshot.provider_id = %s
              AND resource.provider_path = 'data/events/3869685.json'
            """,
            (provider_id,),
        ).fetchone()
        advisory_locks = cursor.execute(
            """
            SELECT count(*) FROM pg_locks
            WHERE pid = pg_backend_pid() AND locktype = 'advisory'
            """
        ).fetchone()

    assert event_counts == (2, 2, 2)
    assert observations == [
        (
            "22222222-2222-4222-8222-222222222222",
            1,
            "Starting XI",
            1,
            timedelta(0),
            "771",
            None,
            "771",
        ),
        (
            "11111111-1111-4111-8111-111111111111",
            2,
            "Pass",
            1,
            timedelta(seconds=5.25),
            "779",
            "5503",
            "779",
        ),
    ]
    assert resource_status == ("parsed", "valid", "validated")
    assert advisory_locks == (1,)


def test_event_only_scope_preserves_entities_and_versions_event_facts(
    connection: Connection[Any], tmp_path: Path
) -> None:
    source_git_sha = "4" * 40
    first_at = datetime(2026, 8, 29, 8, 0, tzinfo=UTC)
    second_at = datetime(2026, 8, 30, 8, 0, tzinfo=UTC)
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)
    ingestor.ingest(
        _acquire_bundle(
            tmp_path,
            source_git_sha=source_git_sha,
            acquired_at=first_at,
            events=_event_payload(),
        )
    )
    event_provider = FixtureProvider(
        "6" * 40,
        {"data/events/3869685.json": _json_bytes(_event_payload(second_type="Carry"))},
    )
    event_scope = SourceAcquirer(tmp_path, clock=lambda: second_at).acquire(
        event_provider,
        (SourceResource("data/events/3869685.json"),),
    )

    result = ingestor.ingest(event_scope)

    assert result.events_seen == 2
    provider_id = _provider_id(connection)
    with connection.cursor() as cursor:
        entity_observations = cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM football.team_observations WHERE provider_id = %s),
                (SELECT count(*) FROM football.player_observations WHERE provider_id = %s)
            """,
            (provider_id, provider_id),
        ).fetchone()
        event_history = list(
            cursor.execute(
                """
                SELECT provider_event_type, known_from, known_to
                FROM football.event_observations
                WHERE provider_id = %s
                  AND provider_event_id = '11111111-1111-4111-8111-111111111111'
                ORDER BY known_from
                """,
                (provider_id,),
            )
        )

    assert entity_observations == (2, 2)
    assert event_history == [
        ("Pass", first_at, second_at),
        ("Carry", second_at, None),
    ]


def test_duplicate_event_index_rejects_entire_source_before_registration(
    connection: Connection[Any], tmp_path: Path
) -> None:
    events = _event_payload()
    events[0]["index"] = 1
    provider = FixtureProvider(
        "5" * 40,
        {"data/events/3869685.json": _json_bytes(events)},
    )
    acquisition = SourceAcquirer(
        tmp_path,
        clock=lambda: datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
    ).acquire(provider, (SourceResource("data/events/3869685.json"),))

    with pytest.raises(CanonicalIngestionError, match="duplicate event indexes"):
        StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)

    with connection.cursor() as cursor:
        row = cursor.execute(
            "SELECT count(*) FROM football.source_snapshots WHERE source_revision = %s",
            ("5" * 40,),
        ).fetchone()
    assert row is not None and row[0] == 0


def test_publishes_and_registers_normalized_event_dataset_idempotently(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="8" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
    )
    canonical = StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    publisher = StatsBombEventDatasetPublisher(connection, tmp_path)

    first = publisher.publish(acquisition)
    first_file = first.files[0]
    modified_at = first_file.absolute_path.stat().st_mtime_ns
    second = publisher.publish(acquisition)

    assert second.dataset_version_id == first.dataset_version_id
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.files[0].physical_sha256 == first_file.physical_sha256
    assert second.files[0].status == "verified_published"
    assert first_file.absolute_path.stat().st_mtime_ns == modified_at
    table = pq.ParquetFile(first_file.absolute_path).read()
    rows = table.to_pylist()
    assert [row["event_index"] for row in rows] == [1, 2]
    assert rows[1]["x_norm"] == 0.5
    assert rows[1]["y_norm"] == 0.5
    assert rows[1]["canonical_event_type_id"] == "pass"
    assert json.loads(rows[1]["provider_payload_json"])["location"] == [60.0, 40.0]

    manifest = json.loads(first.manifest_path.read_bytes())
    schema_path = Path(__file__).parents[2] / "schemas/contracts/dataset-manifest-v1.schema.json"
    validate_json(manifest, json.loads(schema_path.read_bytes()))
    assert manifest["dataset_version_id"] == str(first.dataset_version_id)
    assert manifest["files"][0]["physical_sha256"] == first_file.physical_sha256

    with connection.cursor() as cursor:
        version = cursor.execute(
            """
            SELECT dataset_name, layer, schema_version, schema_sha256,
                   normalizer_version, status, manifest_path, manifest_sha256
            FROM football.dataset_versions
            WHERE id = %s AND source_snapshot_id = %s
            """,
            (first.dataset_version_id, canonical.source_snapshot_id),
        ).fetchone()
        inputs = list(
            cursor.execute(
                """
                SELECT resource.provider_path, input.input_role
                FROM football.dataset_inputs AS input
                LEFT JOIN football.source_resources AS resource
                  ON resource.id = input.source_resource_id
                WHERE input.dataset_version_id = %s
                ORDER BY resource.provider_path
                """,
                (first.dataset_version_id,),
            )
        )
        files = list(
            cursor.execute(
                """
                SELECT relative_path, physical_sha256, logical_sha256,
                       row_count, size_bytes, schema_sha256
                FROM football.dataset_files
                WHERE dataset_version_id = %s
                """,
                (first.dataset_version_id,),
            )
        )

    assert version == (
        "events",
        "normalized",
        "v1",
        "25869371ba35ed08bafc15c566533153661afacaf9727cc4055cc768482f2f18",
        "statsbomb-normalizer-v1",
        "published",
        str(first.manifest_path.relative_to(tmp_path)),
        first.manifest_sha256,
    )
    assert inputs == [
        ("data/competitions.json", "source"),
        ("data/events/3869685.json", "source"),
        ("data/lineups/3869685.json", "source"),
        ("data/matches/43/106.json", "source"),
    ]
    assert files == [
        (
            first_file.relative_path,
            first_file.physical_sha256,
            first_file.logical_sha256,
            2,
            first_file.size_bytes,
            "25869371ba35ed08bafc15c566533153661afacaf9727cc4055cc768482f2f18",
        )
    ]


def test_dataset_publication_requires_canonical_source_registration(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="9" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
    )

    with pytest.raises(DatasetPublicationError, match="registered canonical source snapshot"):
        StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)

    assert not (tmp_path / "normalized").exists()
    assert not (tmp_path / "manifests/datasets").exists()


def test_dataset_publication_reconciles_files_after_database_rollback(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="0" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    publisher = StatsBombEventDatasetPublisher(connection, tmp_path)

    with connection.transaction(force_rollback=True):
        orphaned = publisher.publish(acquisition)

    with connection.cursor() as cursor:
        absent = cursor.execute(
            "SELECT count(*) FROM football.dataset_versions WHERE id = %s",
            (orphaned.dataset_version_id,),
        ).fetchone()
    assert absent == (0,)

    recovered = publisher.publish(acquisition)

    assert recovered.dataset_version_id == orphaned.dataset_version_id
    assert recovered.status == "verified_published"
    assert recovered.files[0].status == "verified_published"
    with connection.cursor() as cursor:
        registered = cursor.execute(
            "SELECT count(*) FROM football.dataset_versions WHERE id = %s",
            (recovered.dataset_version_id,),
        ).fetchone()
    assert registered == (1,)


def test_validates_normalized_event_dataset_and_registers_idempotent_run(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="1" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
        home_score=0,
        away_score=0,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"
    validation_times = iter(
        (
            datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
            datetime(2026, 8, 29, 9, 1, tzinfo=UTC),
            datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 29, 10, 1, tzinfo=UTC),
        )
    )
    validator = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
        clock=lambda: next(validation_times),
    )

    first = validator.validate(dataset.dataset_version_id)
    second = validator.validate(dataset.dataset_version_id)

    assert first.status == "passed"
    assert first.registration_status == "registered"
    assert first.findings == ()
    assert second.validation_run_id == first.validation_run_id
    assert second.registration_status == "verified_registered"
    with connection.cursor() as cursor:
        run = cursor.execute(
            """
            SELECT dataset_version_id, source_snapshot_id, policy_version,
                   validator_version, status, started_at, completed_at
            FROM football.validation_runs WHERE id = %s
            """,
            (first.validation_run_id,),
        ).fetchone()
        counts = cursor.execute(
            """
            SELECT
                (SELECT count(*) FROM football.validation_runs
                 WHERE dataset_version_id = %s),
                (SELECT count(*) FROM football.validation_findings
                 WHERE validation_run_id = %s)
            """,
            (dataset.dataset_version_id, first.validation_run_id),
        ).fetchone()

    assert run == (
        dataset.dataset_version_id,
        dataset.source_snapshot_id,
        "statsbomb-quality-policy-v1",
        "statsbomb-dataset-validator-v3",
        "passed",
        datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        datetime(2026, 8, 29, 9, 1, tzinfo=UTC),
    )
    assert counts == (1, 0)


def test_publishes_completed_lifecycle_claims_from_exact_validated_lineage(
    connection: Connection[Any], tmp_path: Path
) -> None:
    source_git_sha = "c" * 40
    metadata = _acquire_bundle(
        tmp_path,
        source_git_sha=source_git_sha,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=None,
        home_score=0,
        away_score=0,
    )
    events = _terminal_event_payload()
    detail_payloads = {
        "data/events/3869685.json": _json_bytes(events),
        "data/lineups/3869685.json": _json_bytes(_lineup_payload()),
    }
    details = SourceAcquirer(
        tmp_path,
        clock=lambda: datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    ).acquire(
        FixtureProvider(source_git_sha, detail_payloads),
        tuple(SourceResource(path) for path in detail_payloads),
    )
    ingestor = StatsBombCanonicalIngestor(connection, tmp_path)
    metadata_result = ingestor.ingest(metadata)
    ingestor.ingest(details)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(details)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"
    validation = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
        clock=lambda: datetime(2026, 8, 29, 10, 0, tzinfo=UTC),
    ).validate(dataset.dataset_version_id)
    corpus = EvaluationCorpusV1(
        provider_competition_id=43,
        provider_season_id=106,
        minimum_team_history=1,
        minimum_competition_history=1,
        minimum_scored_targets=1,
    )
    publisher = Sprint2LifecycleClaimPublisher(connection)

    first = publisher.publish(corpus)
    second = publisher.publish(corpus)

    assert first.claims == 1
    assert first.status == "published"
    assert second.claims == 1
    assert second.status == "verified_existing"
    assert second.dataset_version_id == first.dataset_version_id
    assert second.validation_run_id == first.validation_run_id
    with connection.cursor() as cursor:
        claim = cursor.execute(
            """
            SELECT claim.lifecycle, claim.claim_version, claim.terminal_period,
                   claim.terminal_event_count, observation.lifecycle,
                   observation.source_snapshot_id, claim.source_snapshot_id,
                   claim.dataset_version_id, claim.validation_run_id
            FROM football.match_lifecycle_claims AS claim
            JOIN football.match_observations AS observation
              ON observation.id = claim.match_observation_id
            """
        ).fetchone()

    assert claim == (
        "completed",
        "statsbomb-terminal-event-score-v1",
        2,
        2,
        "unknown",
        metadata_result.source_snapshot_id,
        dataset.source_snapshot_id,
        dataset.dataset_version_id,
        validation.validation_run_id,
    )
    gate = Sprint2GateService(connection, tmp_path / "gate").evaluate(corpus)
    assert gate.stage == "walk-forward-execution"


def test_rejects_completed_claim_without_terminal_event_evidence(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="d" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
        home_score=0,
        away_score=0,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"
    validation = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
    ).validate(dataset.dataset_version_id)
    assert validation.status == "passed"
    corpus = EvaluationCorpusV1(
        provider_competition_id=43,
        provider_season_id=106,
        minimum_team_history=1,
        minimum_competition_history=1,
        minimum_scored_targets=1,
    )

    with pytest.raises(LifecycleClaimError, match="lacks exact regulation terminal evidence"):
        Sprint2LifecycleClaimPublisher(connection).publish(corpus)

    with connection.cursor() as cursor:
        assert cursor.execute(
            "SELECT count(*) FROM football.match_lifecycle_claims"
        ).fetchone() == (0,)


def test_rejects_completed_claim_from_quarantined_score_evidence(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="e" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_terminal_event_payload(),
        home_score=1,
        away_score=0,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"
    validation = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
    ).validate(dataset.dataset_version_id)
    assert validation.status == "quarantined"
    corpus = EvaluationCorpusV1(
        provider_competition_id=43,
        provider_season_id=106,
        minimum_team_history=1,
        minimum_competition_history=1,
        minimum_scored_targets=1,
    )

    with pytest.raises(LifecycleClaimError, match="lacks passed or warning validator v3"):
        Sprint2LifecycleClaimPublisher(connection).publish(corpus)


def test_registers_policy_classified_dataset_findings(
    connection: Connection[Any], tmp_path: Path
) -> None:
    events = _event_payload()
    events[0]["type"] = {"id": 999999, "name": "Unknown Test Event"}
    events[0]["player"] = {"id": 9999, "name": "Missing From Lineup"}
    events[0]["location"] = [130.0, 40.0]
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="2" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=events,
        nonmonotonic_position=True,
        home_score=0,
        away_score=0,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"

    result = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
    ).validate(dataset.dataset_version_id)

    assert result.status == "quarantined"
    assert {finding.rule_code for finding in result.findings} == {
        "SB_EVENT_LOCATION_OUT_OF_BOUNDS",
        "SB_LINEUP_INCONSISTENCY",
        "SB_NONMONOTONIC_POSITION_STINT",
        "SB_UNKNOWN_EVENT_TYPE",
    }
    with connection.cursor() as cursor:
        findings = list(
            cursor.execute(
                """
                SELECT finding.rule_code, finding.severity, finding.action,
                       finding.scope_type, file.dataset_version_id,
                       resource.source_snapshot_id
                FROM football.validation_findings AS finding
                JOIN football.dataset_files AS file ON file.id = finding.dataset_file_id
                LEFT JOIN football.source_resources AS resource
                  ON resource.id = finding.source_resource_id
                WHERE finding.validation_run_id = %s
                ORDER BY finding.rule_code
                """,
                (result.validation_run_id,),
            )
        )

    assert findings == [
        (
            "SB_EVENT_LOCATION_OUT_OF_BOUNDS",
            "WARNING",
            "EXCLUDE_FROM_DERIVED_SPATIAL_FEATURES",
            "event",
            dataset.dataset_version_id,
            dataset.source_snapshot_id,
        ),
        (
            "SB_LINEUP_INCONSISTENCY",
            "QUARANTINE",
            "QUARANTINE_MATCH",
            "event",
            dataset.dataset_version_id,
            dataset.source_snapshot_id,
        ),
        (
            "SB_NONMONOTONIC_POSITION_STINT",
            "WARNING",
            "PRESERVE_AND_REVIEW",
            "lineup",
            dataset.dataset_version_id,
            None,
        ),
        (
            "SB_UNKNOWN_EVENT_TYPE",
            "WARNING",
            "PRESERVE_WITH_NULL_CANONICAL_MAPPING",
            "event",
            dataset.dataset_version_id,
            dataset.source_snapshot_id,
        ),
    ]


def test_dataset_validation_fails_on_mutated_registered_parquet(
    connection: Connection[Any], tmp_path: Path
) -> None:
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha="3" * 40,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
        events=_event_payload(),
        home_score=0,
        away_score=0,
    )
    StatsBombCanonicalIngestor(connection, tmp_path).ingest(acquisition)
    dataset = StatsBombEventDatasetPublisher(connection, tmp_path).publish(acquisition)
    dataset.files[0].absolute_path.write_bytes(b"mutated")
    policy_path = Path(__file__).parents[2] / "schemas/quality/statsbomb-quality-policy-v1.json"

    result = StatsBombDatasetValidator(
        connection,
        tmp_path,
        QualityPolicy.from_path(policy_path),
    ).validate(dataset.dataset_version_id)

    assert result.status == "failed"
    assert [finding.rule_code for finding in result.findings] == ["SB_DATASET_FILE_INTEGRITY"]


def test_concurrent_identical_ingestion_publishes_one_canonical_graph(tmp_path: Path) -> None:
    source_git_sha = "2" * 40
    acquisition = _acquire_bundle(
        tmp_path,
        source_git_sha=source_git_sha,
        acquired_at=datetime(2026, 8, 29, 8, 0, tzinfo=UTC),
    )
    barrier = Barrier(2, timeout=10)

    def ingest() -> UUID:
        with psycopg.connect(DATABASE_URL) as worker_connection:
            barrier.wait()
            result = StatsBombCanonicalIngestor(worker_connection, tmp_path).ingest(acquisition)
            return result.source_snapshot_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshot_ids = list(executor.map(lambda _index: ingest(), range(2)))

    assert snapshot_ids[0] == snapshot_ids[1]
    with psycopg.connect(DATABASE_URL) as check_connection, check_connection.cursor() as cursor:
        snapshot_count = cursor.execute(
            "SELECT count(*) FROM football.source_snapshots WHERE source_revision = %s",
            (source_git_sha,),
        ).fetchone()
        mapping_count = cursor.execute(
            """
            SELECT count(*) FROM football.match_provider_mappings AS mapping
            JOIN football.source_snapshots AS snapshot
              ON snapshot.id = mapping.source_snapshot_id
            WHERE snapshot.source_revision = %s
            """,
            (source_git_sha,),
        ).fetchone()
    assert snapshot_count is not None and snapshot_count[0] == 1
    assert mapping_count is not None and mapping_count[0] == 1
