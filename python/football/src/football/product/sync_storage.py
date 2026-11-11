"""Competition, fixture, history and standings persistence for the product sync."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from football.product.api_football import (
    context_capability,
    continent_for_country,
    fixture_status,
    inferred_division,
)
from football.product.domain import (
    fixture_identity,
    stable_id,
)
from football.product.identity_crosswalks import FOOTBALL_DATA_COMPETITIONS
from football.product.sync_identity import ProductIdentityMixin
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    PROVIDER_CODE,
    _api_football_score_basis,
    _empty_standing,
    _football_data_fixture_season,
    _football_data_score_basis,
    _football_data_status,
    _integer,
    _mapping,
    _season_date_bounds,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks


class ProductStorageMixin(ProductIdentityMixin):
    """Persist competitions, fixtures, history and standings."""

    def _store_competitions(
        self, rows: Sequence[Mapping[str, Any]], snapshot_id: UUID, observed_at: datetime
    ) -> int:
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
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
            season_start, season_end = _season_date_bounds(
                current.get("start"), current.get("end"), provider_id, season, snapshot_id
            )
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
                    (season_id, competition_id, season_start, season_end),
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
                for resource in ("INJURIES", "SUSPENSIONS", "LINEUPS"):
                    cursor.execute(
                        """
                        INSERT INTO football.product_context_capabilities (
                            competition_id, provider, resource, status,
                            observed_at, source_snapshot_id
                        ) VALUES (%s, 'api_football', %s, %s, %s, %s)
                        ON CONFLICT (competition_id, provider, resource) DO UPDATE SET
                            status = CASE
                                WHEN football.product_context_capabilities.status =
                                     'PLAN_RESTRICTION'
                                 AND EXCLUDED.status <> 'UNSUPPORTED_BY_COMPETITION'
                                THEN football.product_context_capabilities.status
                                ELSE EXCLUDED.status
                            END,
                            observed_at = EXCLUDED.observed_at,
                            source_snapshot_id = EXCLUDED.source_snapshot_id
                        """,
                        (
                            competition_id,
                            resource,
                            context_capability(current, resource).value,
                            observed_at,
                            snapshot_id,
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
                FROM football.product_eligible_match_history history
                JOIN football.matches m ON m.id = history.fixture_id
                WHERE history.competition_id = %s AND m.season_id = %s
                  AND history.known_at <= %s
                ORDER BY history.kickoff_at, history.fixture_id
                """,
                (competition_id, season_id, observed_at),
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
        self._reset_standings(competition_id)
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
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
            self._ensure_season(competition_id, season_id)
            if not self._competition_exists(competition_id):
                self._store_fixture_competition(row, competition_id, observed_at)
            country = str(league.get("country") or "World")
            home_id = self._team_id(home, country, snapshot_id, observed_at)
            away_id = self._team_id(away, country, snapshot_id, observed_at)
            kickoff = datetime.fromisoformat(str(fixture["date"])).astimezone(UTC)
            provider_fixture_id = str(_integer(fixture, "id"))
            match_id = self._mapped_match_id(
                PROVIDER_CODE, provider_fixture_id
            ) or fixture_identity(competition_id, str(season), kickoff, home_id, away_id)
            provider_status = str(_mapping(fixture, "status")["short"])
            status = fixture_status(provider_status)
            score_basis = _api_football_score_basis(provider_status)
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
                        forecast_availability, updated_at, result_score_basis
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'NOT_ENOUGH_HISTORY', %s, %s)
                    ON CONFLICT (fixture_id) DO UPDATE SET
                        competition_id = EXCLUDED.competition_id,
                        home_team_id = EXCLUDED.home_team_id,
                        away_team_id = EXCLUDED.away_team_id,
                        kickoff_at = EXCLUDED.kickoff_at,
                        status = EXCLUDED.status, home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score, venue = EXCLUDED.venue,
                        round_name = EXCLUDED.round_name, updated_at = EXCLUDED.updated_at,
                        result_score_basis = EXCLUDED.result_score_basis
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
                        score_basis,
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        reverse_codes = {code: league_id for league_id, code in FOOTBALL_DATA_COMPETITIONS.items()}
        count = 0
        league_seasons: set[tuple[int, int]] = set()
        for row in rows:
            competition = _mapping(row, "competition")
            league_id = reverse_codes.get(str(competition.get("code")))
            if league_id is None:
                continue
            competition_id = self._competition_id(str(league_id), snapshot_id)
            self._fallback_competition_mapping(
                str(competition["code"]), competition_id, snapshot_id, observed_at
            )
            if not self._competition_exists(competition_id):
                continue
            season = _football_data_fixture_season(row)
            season_id = stable_id("season", competition_id, season)
            self._ensure_season(competition_id, season_id)
            home = _mapping(row, "homeTeam")
            away = _mapping(row, "awayTeam")
            home_id = self._fallback_team_id(home, snapshot_id, observed_at)
            away_id = self._fallback_team_id(away, snapshot_id, observed_at)
            kickoff = datetime.fromisoformat(str(row["utcDate"]).replace("Z", "+00:00")).astimezone(
                UTC
            )
            provider_fixture_id = str(_integer(row, "id"))
            mapped = self._mapped_match_id(FALLBACK_PROVIDER_CODE, provider_fixture_id)
            if mapped is not None:
                registered = self.connection.execute(
                    "SELECT competition_id,season_id FROM football.matches WHERE id=%s",
                    (mapped,),
                ).fetchone()
                if registered != (competition_id, season_id):
                    raise ValueError(
                        "football-data.org fixture season contradicts registered match"
                    )
            match_id = mapped or fixture_identity(
                competition_id, str(season), kickoff, home_id, away_id
            )
            status = _football_data_status(str(row.get("status")))
            score_basis = _football_data_score_basis(row)
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
                    provider_fixture_id,
                    snapshot_id,
                    observed_at,
                    FALLBACK_PROVIDER_CODE,
                )
                cursor.execute(
                    """
                    INSERT INTO football.product_fixtures (
                        fixture_id, competition_id, home_team_id, away_team_id, kickoff_at,
                        status, home_score, away_score, venue, round_name,
                        forecast_availability, updated_at, result_score_basis
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'NOT_ENOUGH_HISTORY', %s, %s)
                    ON CONFLICT (fixture_id) DO UPDATE SET
                        kickoff_at = EXCLUDED.kickoff_at,
                        status = EXCLUDED.status, home_score = EXCLUDED.home_score,
                        away_score = EXCLUDED.away_score, venue = EXCLUDED.venue,
                        round_name = EXCLUDED.round_name, updated_at = EXCLUDED.updated_at,
                        result_score_basis = EXCLUDED.result_score_basis
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
                        score_basis,
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
                      AND mpm.valid_to IS NULL
                      AND (mpm.valid_from IS NULL OR mpm.valid_from <= clock_timestamp())
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
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
            if (
                row.get("status") != "FINISHED"
                or _football_data_score_basis(row) != "REGULATION_90"
            ):
                continue
            home = _mapping(row, "homeTeam")
            away = _mapping(row, "awayTeam")
            score = _mapping(_mapping(row, "score"), "fullTime")
            home_goals = score.get("home")
            away_goals = score.get("away")
            if not isinstance(home_goals, int) or not isinstance(away_goals, int):
                continue
            home_id = self._fallback_team_id(home, snapshot_id, observed_at)
            away_id = self._fallback_team_id(away, snapshot_id, observed_at)
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        if rows:
            self._reset_standings(competition_id)
        count = 0
        for row in rows:
            team = _mapping(row, "team")
            team_id = self._fallback_team_id(team, snapshot_id, observed_at)
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
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        count = 0
        for envelope in rows:
            league = _mapping(envelope, "league")
            competition_id = self._competition_id(str(_integer(league, "id")), snapshot_id)
            groups = cast(list[list[Mapping[str, Any]]], league.get("standings", []))
            if not groups:
                continue
            self._reset_standings(competition_id)
            for row in groups[0]:
                team = _mapping(row, "team")
                team_id = self._team_id(
                    team,
                    str(league.get("country") or ""),
                    snapshot_id,
                    observed_at,
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

    def _reset_standings(self, competition_id: UUID) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM football.product_standings WHERE competition_id = %s",
                (competition_id,),
            )
