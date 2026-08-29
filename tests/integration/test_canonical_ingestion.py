from __future__ import annotations

import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import UUID

import psycopg
import pytest
from football.contracts import SourceResource, SourceSnapshot
from football.ingestion import (
    AcquisitionResult,
    CanonicalIngestionError,
    SourceAcquirer,
    SourceIntegrityError,
    StatsBombCanonicalIngestor,
)
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


def _match_payload(*, home_name: str = "Argentina") -> list[dict[str, object]]:
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
            "home_score": 3,
            "away_score": 3,
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
                            "from": "00:00",
                            "to": "115:32",
                            "from_period": 1,
                            "to_period": 4,
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


def _acquire_bundle(
    data_root: Path,
    *,
    source_git_sha: str,
    acquired_at: datetime,
    home_name: str = "Argentina",
    home_team_id: int = 779,
    nickname: str = "Lionel Messi",
) -> AcquisitionResult:
    payloads = {
        "data/competitions.json": _json_bytes(_competition_payload()),
        "data/matches/43/106.json": _json_bytes(_match_payload(home_name=home_name)),
        "data/lineups/3869685.json": _json_bytes(
            _lineup_payload(
                home_team_id=home_team_id,
                home_name=home_name,
                nickname=nickname,
            )
        ),
    }
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
