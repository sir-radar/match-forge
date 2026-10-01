"""Persist real MVP fixtures, context, standings, and pre-match forecasts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from psycopg import Connection

from football.product.api_football import (
    ApiFootballClient,
    ApiResponse,
    continent_for_country,
    fixture_status,
    inferred_division,
)
from football.product.domain import (
    FinishedMatch,
    external_selection_correct,
    fixture_identity,
    forecast_from_history,
    forecast_payload,
    normalize_team_name,
    sha256_json,
    stable_id,
)
from football.product.football_data_org import (
    FootballDataOrgClient,
    FootballDataOrgError,
    FootballDataResponse,
)

PROVIDER_CODE = "api_football"
FALLBACK_PROVIDER_CODE = "football_data_org"

# Explicit cross-provider competition mapping. No fuzzy competition matching is permitted.
FOOTBALL_DATA_COMPETITIONS = {
    1: "WC",
    2: "CL",
    4: "EC",
    13: "CLI",
    39: "PL",
    40: "ELC",
    61: "FL1",
    71: "BSA",
    78: "BL1",
    88: "DED",
    94: "PPL",
    135: "SA",
    140: "PD",
}


def _empty_standing() -> dict[str, int]:
    return {
        "played": 0,
        "won": 0,
        "drawn": 0,
        "lost": 0,
        "goals_for": 0,
        "goals_against": 0,
        "points": 0,
    }


class ProductSync:
    def __init__(
        self,
        connection: Connection[Any],
        client: ApiFootballClient,
        data_root: Path,
        artifact_path: Path,
        history_fallback: FootballDataOrgClient | None = None,
    ) -> None:
        self.connection = connection
        self.client = client
        self.data_root = data_root
        self.artifact_path = artifact_path
        self.history_fallback = history_fallback

    def run(self, requested_date: date, *, max_history_leagues: int = 20) -> dict[str, int]:
        if max_history_leagues < 0:
            raise ValueError("max_history_leagues must be non-negative")
        competition_response = self.client.competitions()
        competition_snapshot = self._record_response("competitions", competition_response)
        competition_count = self._store_competitions(
            competition_response.rows, competition_snapshot, competition_response.fetched_at
        )
        fixture_count, league_seasons = self._store_requested_fixtures(requested_date)
        league_seasons = league_seasons[:max_history_leagues]
        history_count = 0
        standings_count = 0
        for league_id, season in league_seasons:
            history_observed_at: datetime
            try:
                history_response = self.client.finished_fixtures(league_id, season)
            except RuntimeError:
                history_response = None
            if history_response is not None and history_response.rows:
                history_snapshot = self._record_response(
                    f"history-{league_id}-{season}", history_response
                )
                history_count += self._store_history(
                    history_response.rows, history_snapshot, history_response.fetched_at
                )
                history_observed_at = history_response.fetched_at
            else:
                fallback = self._fallback_history(league_id, season)
                if fallback is None:
                    continue
                history_snapshot = self._record_fallback_response(
                    f"history-{league_id}-{season}", fallback
                )
                competition_id = self._competition_id(str(league_id), history_snapshot)
                history_count += self._store_fallback_history(
                    fallback.rows,
                    competition_id,
                    season,
                    history_snapshot,
                    fallback.fetched_at,
                )
                previous = self._fallback_history(league_id, season - 1)
                if previous is not None:
                    previous_snapshot = self._record_fallback_response(
                        f"history-{league_id}-{season - 1}", previous
                    )
                    history_count += self._store_fallback_history(
                        previous.rows,
                        competition_id,
                        season - 1,
                        previous_snapshot,
                        previous.fetched_at,
                    )
                history_observed_at = fallback.fetched_at
            try:
                standings_response = self.client.standings(league_id, season)
            except RuntimeError:
                standings_response = None
            if standings_response is None or not standings_response.rows:
                competition_id = self._competition_id(str(league_id), history_snapshot)
                fallback_standings = self._fallback_standings(league_id, season)
                if fallback_standings is not None:
                    snapshot = self._record_fallback_response(
                        f"standings-{league_id}-{season}", fallback_standings
                    )
                    standings_count += self._store_fallback_standings(
                        fallback_standings.rows,
                        competition_id,
                        snapshot,
                        fallback_standings.fetched_at,
                    )
                else:
                    standings_count += self._calculate_standings(
                        competition_id, season, history_observed_at
                    )
                continue
            standings_snapshot = self._record_response(
                f"standings-{league_id}-{season}", standings_response
            )
            standings_count += self._store_standings(
                standings_response.rows, standings_snapshot, standings_response.fetched_at
            )
        completed_at = datetime.now(UTC)
        settled_count = self._settle_external_predictions(completed_at)
        forecast_count = self.refresh_forecasts(completed_at)
        self.connection.commit()
        return {
            "competitions": competition_count,
            "fixtures": fixture_count,
            "history_matches": history_count,
            "standings_rows": standings_count,
            "forecasts": forecast_count,
            "settled_external_predictions": settled_count,
        }

    def _store_requested_fixtures(self, requested_date: date) -> tuple[int, list[tuple[int, int]]]:
        try:
            response = self.client.fixtures_for_date(requested_date)
        except RuntimeError:
            response = None
        if response is not None and response.rows:
            snapshot = self._record_response(f"fixtures-{requested_date}", response)
            fixtures = self._store_fixtures(response.rows, snapshot, response.fetched_at)
            return len(fixtures), _league_seasons(fixtures)
        fallback = self._fallback_fixtures(requested_date)
        if fallback is None:
            raise ValueError("fixture providers unavailable")
        snapshot = self._record_fallback_response(f"fixtures-{requested_date}", fallback)
        return self._store_fallback_fixtures(fallback.rows, snapshot, fallback.fetched_at)

    def _settle_external_predictions(self, settled_at: datetime) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT ep.prediction_id, ep.market, ep.selection,
                       pf.home_score, pf.away_score
                FROM football.external_predictions ep
                JOIN football.product_fixtures pf ON pf.fixture_id = ep.fixture_id
                LEFT JOIN football.external_prediction_results result
                  ON result.prediction_id = ep.prediction_id
                WHERE pf.status = 'FINISHED' AND result.prediction_id IS NULL
                ORDER BY ep.prediction_id
                """
            )
            pending = cursor.fetchall()
        count = 0
        with self.connection.cursor() as cursor:
            for prediction_id, market, selection, home_goals, away_goals in pending:
                correct = external_selection_correct(market, selection, home_goals, away_goals)
                if correct is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO football.external_prediction_results (
                        prediction_id, correct, settled_at
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT (prediction_id) DO NOTHING
                    """,
                    (prediction_id, correct, settled_at),
                )
                count += cursor.rowcount
        return count

    def _record_response(self, resource_name: str, response: ApiResponse) -> UUID:
        digest = hashlib.sha256(response.raw).hexdigest()
        provider_id = stable_id("provider", PROVIDER_CODE)
        snapshot_id = stable_id("source-snapshot", PROVIDER_CODE, resource_name, digest)
        resource_id = stable_id("source-resource", snapshot_id, resource_name)
        relative_path = (
            Path("mvp")
            / PROVIDER_CODE
            / response.fetched_at.strftime("%Y/%m/%d")
            / f"{digest}.json"
        )
        destination = self.data_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(response.raw)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, 'API-Football', 'http_api')
                ON CONFLICT (code) DO NOTHING
                """,
                (provider_id, PROVIDER_CODE),
            )
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, acquired_at,
                    manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    resource_name,
                    digest,
                    response.fetched_at,
                    str(relative_path),
                    digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes,
                    media_type, parse_status, validation_status, acquired_at
                ) VALUES (%s, %s, %s, %s, %s, 'application/json', 'parsed', 'valid', %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                """,
                (
                    resource_id,
                    snapshot_id,
                    response.path.lstrip("/"),
                    digest,
                    len(response.raw),
                    response.fetched_at,
                ),
            )
        return snapshot_id

    def _record_fallback_response(self, resource_name: str, response: FootballDataResponse) -> UUID:
        digest = hashlib.sha256(response.raw).hexdigest()
        provider_id = stable_id("provider", FALLBACK_PROVIDER_CODE)
        snapshot_id = stable_id("source-snapshot", FALLBACK_PROVIDER_CODE, resource_name, digest)
        resource_id = stable_id("source-resource", snapshot_id, resource_name)
        relative_path = (
            Path("mvp")
            / FALLBACK_PROVIDER_CODE
            / response.fetched_at.strftime("%Y/%m/%d")
            / f"{digest}.json"
        )
        destination = self.data_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            destination.write_bytes(response.raw)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.providers (id, code, name, source_type)
                VALUES (%s, %s, 'football-data.org', 'http_api')
                ON CONFLICT (code) DO NOTHING
                """,
                (provider_id, FALLBACK_PROVIDER_CODE),
            )
            cursor.execute(
                """
                INSERT INTO football.source_snapshots (
                    id, provider_id, source_identity, source_revision, acquired_at,
                    manifest_path, manifest_sha256, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'validated')
                ON CONFLICT (provider_id, source_identity, source_revision) DO NOTHING
                """,
                (
                    snapshot_id,
                    provider_id,
                    resource_name,
                    digest,
                    response.fetched_at,
                    str(relative_path),
                    digest,
                ),
            )
            cursor.execute(
                """
                INSERT INTO football.source_resources (
                    id, source_snapshot_id, provider_path, sha256, size_bytes,
                    media_type, parse_status, validation_status, acquired_at
                ) VALUES (%s, %s, %s, %s, %s, 'application/json', 'parsed', 'valid', %s)
                ON CONFLICT (source_snapshot_id, provider_path) DO NOTHING
                """,
                (
                    resource_id,
                    snapshot_id,
                    response.path.lstrip("/"),
                    digest,
                    len(response.raw),
                    response.fetched_at,
                ),
            )
        return snapshot_id

    def _fallback_history(self, league_id: int, season: int) -> FootballDataResponse | None:
        competition_code = FOOTBALL_DATA_COMPETITIONS.get(league_id)
        if self.history_fallback is None or competition_code is None:
            return None
        try:
            return self.history_fallback.finished_matches(competition_code, season)
        except FootballDataOrgError:
            return None

    def _fallback_fixtures(self, requested_date: date) -> FootballDataResponse | None:
        if self.history_fallback is None:
            return None
        try:
            return self.history_fallback.fixtures_for_date(requested_date)
        except FootballDataOrgError:
            return None

    def _fallback_standings(self, league_id: int, season: int) -> FootballDataResponse | None:
        competition_code = FOOTBALL_DATA_COMPETITIONS.get(league_id)
        if self.history_fallback is None or competition_code is None:
            return None
        try:
            return self.history_fallback.standings(competition_code, season)
        except FootballDataOrgError:
            return None

    def _store_competitions(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        count = 0
        for row in rows:
            league = _mapping(row, "league")
            country_data = _mapping(row, "country")
            seasons = cast(list[Mapping[str, Any]], row.get("seasons", []))
            current = next((item for item in seasons if item.get("current") is True), None)
            if current is None:
                continue
            provider_id = str(_integer(league, "id"))
            competition_id = self._competition_id(provider_id, snapshot_id)
            season = int(str(current["year"]))
            season_id = stable_id("season", competition_id, season)
            country = str(country_data.get("name") or league.get("country") or "World")
            competition_type = str(league.get("type") or "Cup")
            name = str(league["name"])
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (competition_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO football.seasons (id, competition_id, start_date, end_date)
                    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (season_id, competition_id, current.get("start"), current.get("end")),
                )
                cursor.execute(
                    """
                    INSERT INTO football.product_competitions (
                        competition_id, name, country, continent, division, competition_type,
                        season_label, fixtures_available, results_available, standings_available,
                        h2h_available, forecast_available, xg_available, team_stats_available,
                        availability_status, source_roles, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, true, true, %s,
                        false, false, false, false, 'NOT_ENOUGH_HISTORY', %s::jsonb, %s
                    )
                    ON CONFLICT (competition_id) DO UPDATE SET
                        name = EXCLUDED.name, country = EXCLUDED.country,
                        continent = EXCLUDED.continent, division = EXCLUDED.division,
                        season_label = EXCLUDED.season_label,
                        standings_available = EXCLUDED.standings_available,
                        source_roles = EXCLUDED.source_roles, updated_at = EXCLUDED.updated_at
                    """,
                    (
                        competition_id,
                        name,
                        country,
                        continent_for_country(country),
                        inferred_division(name, competition_type),
                        competition_type.upper(),
                        str(season),
                        bool(current.get("coverage", {}).get("standings")),
                        json.dumps(
                            {
                                "fixtures": [PROVIDER_CODE],
                                "results": [PROVIDER_CODE],
                                "standings": [PROVIDER_CODE],
                                "h2h": [],
                                "team_stats": [],
                            }
                        ),
                        observed_at,
                    ),
                )
            count += 1
        return count

    def _calculate_standings(self, competition_id: UUID, season: int, observed_at: datetime) -> int:
        """Fall back to completed results when provider standings are unavailable."""
        season_id = stable_id("season", competition_id, season)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history.home_team_id, history.away_team_id,
                       history.home_goals, history.away_goals
                FROM football.product_team_match_history history
                JOIN football.matches m ON m.id = history.fixture_id
                WHERE history.competition_id = %s AND m.season_id = %s
                ORDER BY history.kickoff_at, history.fixture_id
                """,
                (competition_id, season_id),
            )
            matches = cursor.fetchall()
        if not matches:
            return 0
        table: dict[UUID, dict[str, int]] = {}
        for home_id, away_id, home_goals, away_goals in matches:
            home = table.setdefault(home_id, _empty_standing())
            away = table.setdefault(away_id, _empty_standing())
            home["played"] += 1
            away["played"] += 1
            home["goals_for"] += home_goals
            home["goals_against"] += away_goals
            away["goals_for"] += away_goals
            away["goals_against"] += home_goals
            if home_goals > away_goals:
                home["won"] += 1
                home["points"] += 3
                away["lost"] += 1
            elif away_goals > home_goals:
                away["won"] += 1
                away["points"] += 3
                home["lost"] += 1
            else:
                home["drawn"] += 1
                away["drawn"] += 1
                home["points"] += 1
                away["points"] += 1
        ranked = sorted(
            table.items(),
            key=lambda item: (
                -item[1]["points"],
                -(item[1]["goals_for"] - item[1]["goals_against"]),
                -item[1]["goals_for"],
                str(item[0]),
            ),
        )
        with self.connection.cursor() as cursor:
            for position, (team_id, row) in enumerate(ranked, start=1):
                cursor.execute(
                    """
                    INSERT INTO football.product_standings (
                        competition_id, team_id, position, played, won, drawn, lost,
                        goals_for, goals_against, goal_difference, points,
                        source_provider_code, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'matchforge_results', %s)
                    ON CONFLICT (competition_id, team_id) DO UPDATE SET
                        position = EXCLUDED.position, played = EXCLUDED.played,
                        won = EXCLUDED.won, drawn = EXCLUDED.drawn, lost = EXCLUDED.lost,
                        goals_for = EXCLUDED.goals_for, goals_against = EXCLUDED.goals_against,
                        goal_difference = EXCLUDED.goal_difference, points = EXCLUDED.points,
                        source_provider_code = EXCLUDED.source_provider_code,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        competition_id,
                        team_id,
                        position,
                        row["played"],
                        row["won"],
                        row["drawn"],
                        row["lost"],
                        row["goals_for"],
                        row["goals_against"],
                        row["goals_for"] - row["goals_against"],
                        row["points"],
                        observed_at,
                    ),
                )
            cursor.execute(
                """
                UPDATE football.product_competitions
                SET standings_available = true,
                    source_roles = jsonb_set(source_roles, '{standings}',
                        '["api_football", "matchforge_results"]'::jsonb),
                    updated_at = %s
                WHERE competition_id = %s
                """,
                (observed_at, competition_id),
            )
        return len(ranked)

    def _store_fixtures(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> list[Mapping[str, Any]]:
        stored: list[Mapping[str, Any]] = []
        for row in rows:
            league = _mapping(row, "league")
            fixture = _mapping(row, "fixture")
            teams = _mapping(row, "teams")
            home = _mapping(teams, "home")
            away = _mapping(teams, "away")
            competition_id = self._competition_id(str(_integer(league, "id")), snapshot_id)
            season = int(league["season"])
            season_id = stable_id("season", competition_id, season)
            if not self._competition_exists(competition_id):
                self._store_fixture_competition(
                    row, competition_id, season_id, snapshot_id, observed_at
                )
            country = str(league.get("country") or "World")
            home_id = self._team_id(home, country, snapshot_id, observed_at)
            away_id = self._team_id(away, country, snapshot_id, observed_at)
            kickoff = datetime.fromisoformat(str(fixture["date"])).astimezone(UTC)
            match_id = fixture_identity(competition_id, str(season), kickoff, home_id, away_id)
            provider_fixture_id = str(_integer(fixture, "id"))
            status = fixture_status(str(_mapping(fixture, "status")["short"]))
            goals = _mapping(row, "goals")
            home_score = goals.get("home") if status == "FINISHED" else None
            away_score = goals.get("away") if status == "FINISHED" else None
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.matches (id, competition_id, season_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (match_id, competition_id, season_id),
                )
                self._ensure_match_mapping(
                    cursor, match_id, provider_fixture_id, snapshot_id, observed_at
                )
                cursor.execute(
                    """
                    INSERT INTO football.product_fixtures (
                        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                        status, home_score, away_score, venue, round_name,
                        forecast_availability, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'NOT_ENOUGH_HISTORY', %s)
                    ON CONFLICT (fixture_id) DO UPDATE SET
                        status = EXCLUDED.status, home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score, venue = EXCLUDED.venue,
                        round_name = EXCLUDED.round_name, updated_at = EXCLUDED.updated_at
                    """,
                    (
                        match_id,
                        competition_id,
                        home_id,
                        away_id,
                        kickoff,
                        status,
                        home_score,
                        away_score,
                        _mapping(fixture, "venue").get("name"),
                        league.get("round"),
                        observed_at,
                    ),
                )
            stored.append(row)
        return stored

    def _store_fallback_fixtures(
        self,
        rows: Sequence[Mapping[str, Any]],
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> tuple[int, list[tuple[int, int]]]:
        reverse_codes = {code: league_id for league_id, code in FOOTBALL_DATA_COMPETITIONS.items()}
        count = 0
        league_seasons: set[tuple[int, int]] = set()
        for row in rows:
            competition = _mapping(row, "competition")
            league_id = reverse_codes.get(str(competition.get("code")))
            if league_id is None:
                continue
            competition_id = self._competition_id(str(league_id), snapshot_id)
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT season_label FROM football.product_competitions
                    WHERE competition_id = %s
                    """,
                    (competition_id,),
                )
                season_row = cursor.fetchone()
            if season_row is None:
                continue
            season = int(season_row[0])
            season_id = stable_id("season", competition_id, season)
            home = _mapping(row, "homeTeam")
            away = _mapping(row, "awayTeam")
            home_id = self._fallback_team_id(home, competition_id, snapshot_id, observed_at)
            away_id = self._fallback_team_id(away, competition_id, snapshot_id, observed_at)
            kickoff = datetime.fromisoformat(str(row["utcDate"]).replace("Z", "+00:00")).astimezone(
                UTC
            )
            match_id = fixture_identity(competition_id, str(season), kickoff, home_id, away_id)
            status = _football_data_status(str(row.get("status")))
            score = _mapping(_mapping(row, "score"), "fullTime")
            home_score = score.get("home") if status == "FINISHED" else None
            away_score = score.get("away") if status == "FINISHED" else None
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.matches (id, competition_id, season_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (match_id, competition_id, season_id),
                )
                self._ensure_provider_match_mapping(
                    cursor,
                    match_id,
                    str(_integer(row, "id")),
                    snapshot_id,
                    observed_at,
                    FALLBACK_PROVIDER_CODE,
                )
                cursor.execute(
                    """
                    INSERT INTO football.product_fixtures (
                        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                        status, home_score, away_score, venue, round_name,
                        forecast_availability, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'NOT_ENOUGH_HISTORY', %s)
                    ON CONFLICT (fixture_id) DO UPDATE SET
                        status = EXCLUDED.status, home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score, venue = EXCLUDED.venue,
                        round_name = EXCLUDED.round_name, updated_at = EXCLUDED.updated_at
                    """,
                    (
                        match_id,
                        competition_id,
                        home_id,
                        away_id,
                        kickoff,
                        status,
                        home_score,
                        away_score,
                        row.get("venue"),
                        str(row.get("matchday") or row.get("stage") or ""),
                        observed_at,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE football.product_competitions
                    SET fixtures_available = true,
                        source_roles = jsonb_set(source_roles, '{fixtures}',
                            '["football_data_org"]'::jsonb),
                        updated_at = %s
                    WHERE competition_id = %s
                    """,
                    (observed_at, competition_id),
                )
            count += 1
            league_seasons.add((league_id, season))
        return count, sorted(league_seasons)

    def _store_history(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        fixtures = self._store_fixtures(rows, snapshot_id, observed_at)
        count = 0
        with self.connection.cursor() as cursor:
            for row in fixtures:
                fixture = _mapping(row, "fixture")
                provider_fixture_id = str(_integer(fixture, "id"))
                cursor.execute(
                    """
                    SELECT pf.fixture_id, pf.competition_id, pf.home_team_id, pf.away_team_id,
                           pf.kickoff_at, pf.home_score, pf.away_score
                    FROM football.product_fixtures pf
                    JOIN football.match_provider_mappings mpm ON mpm.match_id = pf.fixture_id
                    JOIN football.providers p ON p.id = mpm.provider_id
                    WHERE p.code = %s AND mpm.provider_match_id = %s
                    """,
                    (PROVIDER_CODE, provider_fixture_id),
                )
                stored = cursor.fetchone()
                if stored is None or stored[5] is None or stored[6] is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO football.product_team_match_history (
                        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                        home_goals, away_goals, source_provider_code, source_snapshot_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fixture_id) DO NOTHING
                    """,
                    (*stored[:7], PROVIDER_CODE, snapshot_id),
                )
                count += cursor.rowcount
        if count:
            self._mark_context_available(
                {_mapping(row, "league").get("id") for row in fixtures}, observed_at
            )
        return count

    def _store_fallback_history(
        self,
        rows: Sequence[Mapping[str, Any]],
        competition_id: UUID,
        season: int,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> int:
        season_label = str(season)
        season_id = stable_id("season", competition_id, season)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.seasons (id, competition_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (season_id, competition_id),
            )
        count = 0
        for row in rows:
            if row.get("status") != "FINISHED":
                continue
            home = _mapping(row, "homeTeam")
            away = _mapping(row, "awayTeam")
            score = _mapping(_mapping(row, "score"), "fullTime")
            home_goals = score.get("home")
            away_goals = score.get("away")
            if not isinstance(home_goals, int) or not isinstance(away_goals, int):
                continue
            home_id = self._fallback_team_id(home, competition_id, snapshot_id, observed_at)
            away_id = self._fallback_team_id(away, competition_id, snapshot_id, observed_at)
            kickoff = datetime.fromisoformat(str(row["utcDate"]).replace("Z", "+00:00")).astimezone(
                UTC
            )
            match_id = fixture_identity(competition_id, season_label, kickoff, home_id, away_id)
            provider_match_id = str(_integer(row, "id"))
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.matches (id, competition_id, season_id)
                    VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """,
                    (match_id, competition_id, season_id),
                )
                self._ensure_provider_match_mapping(
                    cursor,
                    match_id,
                    provider_match_id,
                    snapshot_id,
                    observed_at,
                    FALLBACK_PROVIDER_CODE,
                )
                cursor.execute(
                    """
                    INSERT INTO football.product_team_match_history (
                        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                        home_goals, away_goals, source_provider_code, source_snapshot_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (fixture_id) DO NOTHING
                    """,
                    (
                        match_id,
                        competition_id,
                        home_id,
                        away_id,
                        kickoff,
                        home_goals,
                        away_goals,
                        FALLBACK_PROVIDER_CODE,
                        snapshot_id,
                    ),
                )
                count += cursor.rowcount
        if count:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE football.product_competitions
                    SET results_available = true, h2h_available = true,
                        team_stats_available = true,
                        source_roles = source_roles
                            || '{"results":["football_data_org"],
                                  "h2h":["football_data_org"],
                                  "team_stats":["matchforge_results"]}'::jsonb,
                        updated_at = %s
                    WHERE competition_id = %s
                    """,
                    (observed_at, competition_id),
                )
        return count

    def _store_fallback_standings(
        self,
        rows: Sequence[Mapping[str, Any]],
        competition_id: UUID,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> int:
        count = 0
        for row in rows:
            team = _mapping(row, "team")
            team_id = self._fallback_team_id(team, competition_id, snapshot_id, observed_at)
            values = (
                row.get("position"),
                row.get("playedGames"),
                row.get("won"),
                row.get("draw"),
                row.get("lost"),
                row.get("goalsFor"),
                row.get("goalsAgainst"),
                row.get("goalDifference"),
                row.get("points"),
            )
            if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
                continue
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.product_standings (
                        competition_id, team_id, position, played, won, drawn, lost,
                        goals_for, goals_against, goal_difference, points,
                        source_provider_code, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (competition_id, team_id) DO UPDATE SET
                        position = EXCLUDED.position, played = EXCLUDED.played,
                        won = EXCLUDED.won, drawn = EXCLUDED.drawn, lost = EXCLUDED.lost,
                        goals_for = EXCLUDED.goals_for, goals_against = EXCLUDED.goals_against,
                        goal_difference = EXCLUDED.goal_difference, points = EXCLUDED.points,
                        source_provider_code = EXCLUDED.source_provider_code,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (competition_id, team_id, *values, FALLBACK_PROVIDER_CODE, observed_at),
                )
                count += 1
        if count:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE football.product_competitions
                    SET standings_available = true,
                        source_roles = jsonb_set(source_roles, '{standings}',
                            '["football_data_org"]'::jsonb),
                        updated_at = %s
                    WHERE competition_id = %s
                    """,
                    (observed_at, competition_id),
                )
        return count

    def _mark_context_available(self, league_ids: set[object], observed_at: datetime) -> None:
        for league_id in league_ids:
            if not isinstance(league_id, int):
                continue
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE football.product_competitions pc
                    SET h2h_available = true, team_stats_available = true,
                        source_roles = source_roles
                            || '{"h2h":["api_football"],
                                  "team_stats":["matchforge_results"]}'::jsonb,
                        updated_at = %s
                    FROM football.competition_provider_mappings cpm
                    JOIN football.providers p ON p.id = cpm.provider_id
                    WHERE pc.competition_id = cpm.competition_id
                      AND p.code = %s AND cpm.provider_competition_id = %s
                    """,
                    (observed_at, PROVIDER_CODE, str(league_id)),
                )

    def _store_standings(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        count = 0
        for envelope in rows:
            league = _mapping(envelope, "league")
            competition_id = self._competition_id(str(_integer(league, "id")), snapshot_id)
            groups = cast(list[list[Mapping[str, Any]]], league.get("standings", []))
            if not groups:
                continue
            for row in groups[0]:
                team = _mapping(row, "team")
                team_id = self._team_id(
                    team, str(league.get("country") or ""), snapshot_id, observed_at
                )
                all_results = _mapping(row, "all")
                goals = _mapping(all_results, "goals")
                with self.connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO football.product_standings (
                            competition_id, team_id, position, played, won, drawn, lost,
                            goals_for, goals_against, goal_difference, points,
                            source_provider_code, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (competition_id, team_id) DO UPDATE SET
                            position = EXCLUDED.position, played = EXCLUDED.played,
                            won = EXCLUDED.won, drawn = EXCLUDED.drawn, lost = EXCLUDED.lost,
                            goals_for = EXCLUDED.goals_for, goals_against = EXCLUDED.goals_against,
                            goal_difference = EXCLUDED.goal_difference, points = EXCLUDED.points,
                            source_provider_code = EXCLUDED.source_provider_code,
                            updated_at = EXCLUDED.updated_at
                        """,
                        (
                            competition_id,
                            team_id,
                            row["rank"],
                            all_results["played"],
                            all_results["win"],
                            all_results["draw"],
                            all_results["lose"],
                            goals["for"],
                            goals["against"],
                            row["goalsDiff"],
                            row["points"],
                            PROVIDER_CODE,
                            observed_at,
                        ),
                    )
                    count += 1
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE football.product_competitions
                    SET standings_available = true, updated_at = %s
                    WHERE competition_id = %s
                    """,
                    (observed_at, competition_id),
                )
        return count

    def refresh_forecasts(self, now: datetime | None = None) -> int:
        """Publish only missing future forecasts from already stored canonical history."""
        now = now or datetime.now(UTC)
        artifact_sha = hashlib.sha256(self.artifact_path.read_bytes()).hexdigest()
        count = 0
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture_id, home_team_id, away_team_id, kickoff_at
                FROM football.product_fixtures
                WHERE status = 'SCHEDULED' AND kickoff_at > %s
                  AND NOT EXISTS (
                      SELECT 1 FROM football.product_forecasts forecast
                      WHERE forecast.fixture_id = football.product_fixtures.fixture_id
                  )
                ORDER BY kickoff_at, fixture_id
                """,
                (now,),
            )
            targets = cursor.fetchall()
        for fixture_id, home_id, away_id, kickoff_at in targets:
            history = self._history_before(kickoff_at)
            forecast = forecast_from_history(
                artifact_path=self.artifact_path,
                target_kickoff=kickoff_at,
                home_team_id=home_id,
                away_team_id=away_id,
                history=history,
            )
            if forecast is None:
                continue
            payload = forecast_payload(forecast)
            payload_sha = sha256_json(payload)
            semantic_sha = sha256_json(
                {
                    "fixture_id": str(fixture_id),
                    "artifact_sha256": artifact_sha,
                    "knowledge_cutoff": now.isoformat(),
                    "payload_sha256": payload_sha,
                }
            )
            forecast_id = stable_id("product-forecast", semantic_sha)
            probabilities = {
                "home": forecast.home_probability,
                "draw": forecast.draw_probability,
                "away": forecast.away_probability,
                "btts_yes": forecast.btts_yes,
                "home_clean_sheet": forecast.home_clean_sheet,
                "away_clean_sheet": forecast.away_clean_sheet,
                "total_over_2_5": sum(forecast.total_goal_distribution[3:]),
            }
            probabilities["total_under_2_5"] = 1.0 - probabilities["total_over_2_5"]
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO football.product_forecasts (
                        forecast_id, semantic_sha256, fixture_id, model_label,
                        model_algorithm_version, model_artifact_sha256, created_at,
                        football_cutoff, knowledge_cutoff, knowledge_mode,
                        expected_home_goals, expected_away_goals, probabilities,
                        score_matrix, payload_sha256, publication_mode
                    ) VALUES (%s, %s, %s, 'MVP_FORECAST',
                        'transferable-rolling-goals-poisson-v1', %s, %s, %s, %s,
                        'bitemporal', %s, %s, %s::jsonb, %s::jsonb, %s,
                        'MVP_OWNER_AUTHORIZED')
                    ON CONFLICT (semantic_sha256) DO NOTHING
                    """,
                    (
                        forecast_id,
                        semantic_sha,
                        fixture_id,
                        artifact_sha,
                        now,
                        now,
                        now,
                        forecast.expected_home_goals,
                        forecast.expected_away_goals,
                        json.dumps(probabilities),
                        json.dumps(forecast.score_matrix),
                        payload_sha,
                    ),
                )
                count += cursor.rowcount
                cursor.execute(
                    """
                    UPDATE football.product_fixtures
                    SET forecast_availability = 'FORECAST_AVAILABLE'
                    WHERE fixture_id = %s
                    """,
                    (fixture_id,),
                )
                cursor.execute(
                    """
                    UPDATE football.product_competitions pc
                    SET forecast_available = true,
                        availability_status = 'FORECAST_AVAILABLE',
                        updated_at = %s
                    FROM football.product_fixtures pf
                    WHERE pf.fixture_id = %s AND pc.competition_id = pf.competition_id
                    """,
                    (now, fixture_id),
                )
        return count

    def _history_before(self, cutoff: datetime) -> list[FinishedMatch]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture_id, kickoff_at, home_team_id, away_team_id,
                       home_goals, away_goals, home_xg, away_xg
                FROM football.product_team_match_history
                WHERE (
                    source_kickoff_precision = 'EXACT' AND kickoff_at < %s
                ) OR (
                    source_kickoff_precision = 'DATE_ONLY'
                    AND kickoff_at::date < %s::date
                )
                ORDER BY kickoff_at, fixture_id
                """,
                (cutoff, cutoff),
            )
            return [FinishedMatch(*row) for row in cursor.fetchall()]

    def _competition_id(self, provider_competition_id: str, snapshot_id: UUID) -> UUID:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT cpm.competition_id
                FROM football.competition_provider_mappings cpm
                JOIN football.providers p ON p.id = cpm.provider_id
                WHERE p.code = %s AND cpm.provider_competition_id = %s
                ORDER BY cpm.first_seen_at LIMIT 1
                """,
                (PROVIDER_CODE, provider_competition_id),
            )
            found = cursor.fetchone()
        if found is not None:
            return cast(UUID, found[0])
        competition_id = stable_id("competition", PROVIDER_CODE, provider_competition_id)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO football.competitions (id) VALUES (%s) ON CONFLICT DO NOTHING",
                (competition_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.competition_provider_mappings (
                    competition_id, provider_id, provider_competition_id, first_seen_at,
                    last_seen_at, mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, clock_timestamp(), clock_timestamp(),
                    'deterministic', 1.0, %s FROM football.providers WHERE code = %s
                """,
                (competition_id, provider_competition_id, snapshot_id, PROVIDER_CODE),
            )
        return competition_id

    def _team_id(
        self,
        row: Mapping[str, Any],
        country: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> UUID:
        provider_team_id = str(_integer(row, "id"))
        normalized_name = normalize_team_name(str(row["name"]))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = %s AND provider_team_id = %s
                """,
                (PROVIDER_CODE, provider_team_id),
            )
            found = cursor.fetchone()
        team_id = (
            cast(UUID, found[0])
            if found is not None
            else stable_id("team", PROVIDER_CODE, provider_team_id)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.teams (id, entity_kind)
                VALUES (%s, 'club') ON CONFLICT DO NOTHING
                """,
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, country, crest_url, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (team_id) DO UPDATE SET name = EXCLUDED.name,
                    crest_url = EXCLUDED.crest_url, updated_at = EXCLUDED.updated_at
                """,
                (team_id, row["name"], country or None, row.get("logo"), observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, country, team_id
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (provider_code, provider_team_id) DO NOTHING
                """,
                (PROVIDER_CODE, provider_team_id, normalized_name, country or None, team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
                  FROM football.providers p
                 WHERE p.code = %s
                   AND NOT EXISTS (
                       SELECT 1 FROM football.team_provider_mappings existing
                       WHERE existing.provider_id = p.id
                         AND existing.provider_team_id = %s
                   )
                """,
                (
                    team_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    PROVIDER_CODE,
                    provider_team_id,
                ),
            )
        return team_id

    def _fallback_team_id(
        self,
        row: Mapping[str, Any],
        competition_id: UUID,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> UUID:
        provider_team_id = str(_integer(row, "id"))
        normalized_name = normalize_team_name(str(row["name"]))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT team_id FROM football.product_team_aliases
                WHERE provider_code = %s AND provider_team_id = %s
                """,
                (FALLBACK_PROVIDER_CODE, provider_team_id),
            )
            found = cursor.fetchone()
            if found is None:
                cursor.execute(
                    """
                    SELECT DISTINCT pta.team_id
                    FROM football.product_team_aliases pta
                    WHERE pta.provider_code = %s AND pta.normalized_name = %s
                      AND pta.team_id IN (
                          SELECT home_team_id FROM football.product_fixtures
                          WHERE competition_id = %s
                          UNION SELECT away_team_id FROM football.product_fixtures
                          WHERE competition_id = %s
                          UNION SELECT home_team_id FROM football.product_team_match_history
                          WHERE competition_id = %s
                          UNION SELECT away_team_id FROM football.product_team_match_history
                          WHERE competition_id = %s
                      )
                    """,
                    (
                        PROVIDER_CODE,
                        normalized_name,
                        competition_id,
                        competition_id,
                        competition_id,
                        competition_id,
                    ),
                )
                candidates = cursor.fetchall()
                found = candidates[0] if len(candidates) == 1 else None
        team_id = (
            cast(UUID, found[0])
            if found is not None
            else stable_id("team", FALLBACK_PROVIDER_CODE, provider_team_id)
        )
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.teams (id, entity_kind)
                VALUES (%s, 'club') ON CONFLICT DO NOTHING
                """,
                (team_id,),
            )
            cursor.execute(
                """
                INSERT INTO football.product_teams (team_id, name, crest_url, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (team_id) DO UPDATE SET
                    crest_url = COALESCE(EXCLUDED.crest_url, football.product_teams.crest_url),
                    updated_at = EXCLUDED.updated_at
                """,
                (team_id, row["name"], row.get("crest"), observed_at),
            )
            cursor.execute(
                """
                INSERT INTO football.product_team_aliases (
                    provider_code, provider_team_id, normalized_name, team_id
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (provider_code, provider_team_id) DO NOTHING
                """,
                (FALLBACK_PROVIDER_CODE, provider_team_id, normalized_name, team_id),
            )
            cursor.execute(
                """
                INSERT INTO football.team_provider_mappings (
                    team_id, provider_id, provider_team_id, first_seen_at, last_seen_at,
                    mapping_method, mapping_confidence, source_snapshot_id
                ) SELECT %s, id, %s, %s, %s, 'explicit_crosswalk',
                    1.0, %s FROM football.providers p
                WHERE p.code = %s AND NOT EXISTS (
                    SELECT 1 FROM football.team_provider_mappings existing
                    WHERE existing.provider_id = p.id
                      AND existing.provider_team_id = %s
                )
                """,
                (
                    team_id,
                    provider_team_id,
                    observed_at,
                    observed_at,
                    snapshot_id,
                    FALLBACK_PROVIDER_CODE,
                    provider_team_id,
                ),
            )
        return team_id

    def _ensure_match_mapping(
        self,
        cursor: Any,
        match_id: UUID,
        provider_match_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO football.match_provider_mappings (
                match_id, provider_id, provider_match_id, first_seen_at, last_seen_at,
                mapping_method, mapping_confidence, source_snapshot_id
            ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
              FROM football.providers p
             WHERE p.code = %s
               AND NOT EXISTS (
                   SELECT 1 FROM football.match_provider_mappings existing
                   WHERE existing.provider_id = p.id AND existing.provider_match_id = %s
               )
            """,
            (
                match_id,
                provider_match_id,
                observed_at,
                observed_at,
                snapshot_id,
                PROVIDER_CODE,
                provider_match_id,
            ),
        )

    def _ensure_provider_match_mapping(
        self,
        cursor: Any,
        match_id: UUID,
        provider_match_id: str,
        snapshot_id: UUID,
        observed_at: datetime,
        provider_code: str,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO football.match_provider_mappings (
                match_id, provider_id, provider_match_id, first_seen_at, last_seen_at,
                mapping_method, mapping_confidence, source_snapshot_id
            ) SELECT %s, id, %s, %s, %s, 'deterministic', 1.0, %s
              FROM football.providers p
             WHERE p.code = %s
               AND NOT EXISTS (
                   SELECT 1 FROM football.match_provider_mappings existing
                   WHERE existing.provider_id = p.id AND existing.provider_match_id = %s
               )
            """,
            (
                match_id,
                provider_match_id,
                observed_at,
                observed_at,
                snapshot_id,
                provider_code,
                provider_match_id,
            ),
        )

    def _competition_exists(self, competition_id: UUID) -> bool:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM football.product_competitions WHERE competition_id = %s",
                (competition_id,),
            )
            return cursor.fetchone() is not None

    def _store_fixture_competition(
        self,
        row: Mapping[str, Any],
        competition_id: UUID,
        season_id: UUID,
        snapshot_id: UUID,
        observed_at: datetime,
    ) -> None:
        league = _mapping(row, "league")
        name = str(league["name"])
        country = str(league.get("country") or "World")
        season = int(league["season"])
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO football.seasons (id, competition_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
                """,
                (season_id, competition_id),
            )
            cursor.execute(
                """
                INSERT INTO football.product_competitions (
                    competition_id, name, country, continent, division, competition_type,
                    season_label, fixtures_available, results_available, standings_available,
                    h2h_available, forecast_available, xg_available, team_stats_available,
                    availability_status, source_roles, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 'LEAGUE', %s, true, true, %s,
                    false, false, false, false, 'NOT_ENOUGH_HISTORY', %s::jsonb, %s)
                ON CONFLICT (competition_id) DO NOTHING
                """,
                (
                    competition_id,
                    name,
                    country,
                    continent_for_country(country),
                    inferred_division(name, "League"),
                    str(season),
                    bool(league.get("standings")),
                    json.dumps({"fixtures": [PROVIDER_CODE], "results": [PROVIDER_CODE]}),
                    observed_at,
                ),
            )


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    found = value.get(key)
    if not isinstance(found, Mapping):
        raise ValueError(f"provider field {key} must be an object")
    return cast(Mapping[str, Any], found)


def _integer(value: Mapping[str, Any], key: str) -> int:
    found = value.get(key)
    if isinstance(found, bool) or not isinstance(found, int):
        raise ValueError(f"provider field {key} must be an integer")
    return found


def _league_seasons(fixtures: Iterable[Mapping[str, Any]]) -> list[tuple[int, int]]:
    values = {
        (_integer(_mapping(row, "league"), "id"), int(_mapping(row, "league")["season"]))
        for row in fixtures
    }
    return sorted(values, key=lambda item: (item[0] not in FOOTBALL_DATA_COMPETITIONS, item))


def _football_data_status(value: str) -> str:
    if value in {"IN_PLAY", "PAUSED", "EXTRA_TIME", "PENALTY_SHOOTOUT"}:
        return "LIVE"
    if value in {"FINISHED", "AWARDED"}:
        return "FINISHED"
    if value == "POSTPONED":
        return "POSTPONED"
    if value == "CANCELLED":
        return "CANCELLED"
    if value == "SUSPENDED":
        return "ABANDONED"
    return "SCHEDULED"
