"""Forecast preparation and publication for the product sync."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from football.forecasting.pitchapi_v3 import TransferableParametersV1
from football.forecasting.revisions import RevisionReason, classify_horizon
from football.product.domain import (
    FinishedMatch,
    forecast_from_history,
    forecast_history_window,
    forecast_input_sha,
    forecast_payload,
    sha256_json,
    stable_id,
)
from football.product.forecast_work import claim_forecast_generations, complete_forecast_generations
from football.product.identity_admission import admit_provider_mappings, fixture_identity_blockers
from football.product.sync_support import (
    FALLBACK_PROVIDER_CODE,
    PRODUCT_FORECAST_ALGORITHM_VERSION,
    PROVIDER_CODE,
    ProductSyncBase,
    _PreparedForecast,
)
from football.storage.transactions import require_idle_connection


class ProductForecastMixin(ProductSyncBase):
    """Prepare, publish and refresh pre-match forecasts."""

    def refresh_forecasts(
        self,
        now: datetime | None = None,
        fixture_ids: Sequence[UUID] | None = None,
        *,
        admit_mappings: bool = True,
        commit_batches: bool = False,
    ) -> int:
        """Publish missing future forecasts; busy competition/fixture rows remain queued."""
        if commit_batches:
            require_idle_connection(self.connection, "bounded forecast refresh")
        if admit_mappings:
            for provider in (PROVIDER_CODE, FALLBACK_PROVIDER_CODE):
                admit_provider_mappings(
                    self.connection, self.data_root, provider, commit_each=commit_batches
                )
        now = now or self._database_now()
        artifact_sha, prepared = self._prepare_forecasts(now, fixture_ids)
        if not commit_batches:
            return sum(
                self._publish_prepared_forecast(item, now, artifact_sha) for item in prepared
            )
        self.connection.commit()
        count = 0
        for item in prepared:
            with self.connection.transaction():
                count += self._publish_prepared_forecast(item, now, artifact_sha)
        return count

    def _prepare_forecasts(
        self, now: datetime, fixture_ids: Sequence[UUID] | None
    ) -> tuple[str, list[_PreparedForecast]]:
        """Read immutable inputs and compute before taking canonical or work locks."""
        artifact_bytes = self.artifact_path.read_bytes()
        artifact_sha = hashlib.sha256(artifact_bytes).hexdigest()
        parameters = TransferableParametersV1(**json.loads(artifact_bytes)["parameters"])
        prepared = []
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture_id,
                       football.product_fixture_team_at(fixture_id, home_team_id, %s),
                       football.product_fixture_team_at(fixture_id, away_team_id, %s), kickoff_at
                FROM football.product_fixtures
                WHERE status = 'SCHEDULED' AND kickoff_at > %s
                  AND identity_status = 'VERIFIED'
                  AND (%s::uuid[] IS NULL OR fixture_id = ANY(%s::uuid[]))
                ORDER BY kickoff_at, fixture_id
                """,
                (now, now, now, fixture_ids, fixture_ids),
            )
            targets = cursor.fetchall()
        blockers = fixture_identity_blockers(self.connection, [row[0] for row in targets], now)
        for start in range(0, len(targets), 32):
            batch = targets[start : start + 32]
            history_by_team = self._batch_history(batch, now)
            for fixture_id, home_id, away_id, kickoff_at in batch:
                history = self._target_history(history_by_team, home_id, away_id, kickoff_at)
                window = forecast_history_window(history, kickoff_at, home_id, away_id)
                forecast = (
                    forecast_from_history(
                        artifact_path=self.artifact_path,
                        target_kickoff=kickoff_at,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        history=window or (),
                        parameters=parameters,
                    )
                    if blockers.get(fixture_id) is None
                    else None
                )
                prepared.append(
                    _PreparedForecast(
                        fixture_id,
                        home_id,
                        away_id,
                        kickoff_at,
                        window,
                        forecast,
                        blockers.get(fixture_id) is not None,
                    )
                )
        return artifact_sha, prepared

    def refresh_pending_forecasts(self, limit: int = 32) -> dict[str, object]:
        """Refresh one transaction-sized batch of durable affected fixtures."""
        if limit <= 0 or limit > 32:
            raise ValueError("pending forecast batch limit must be between 1 and 32")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT fixture_id,generation FROM football.product_forecast_refresh_work
                WHERE generation>completed_generation ORDER BY requested_at,fixture_id LIMIT 32"""
            )
            generations = dict(cursor.fetchall())
        if not generations:
            return {"forecasts_created": 0, "fixtures_processed": 0, "fixtures_pending": 0}
        knowledge_cutoff = self._database_now()
        artifact_sha, prepared = self._prepare_forecasts(knowledge_cutoff, list(generations))
        self.connection.execute("SELECT football.authorize_worker_publication()")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture.fixture_id FROM football.product_competitions competition
                JOIN football.product_fixtures fixture USING (competition_id)
                JOIN football.product_forecast_refresh_work work USING (fixture_id)
                WHERE work.generation > work.completed_generation
                  AND fixture.fixture_id=ANY(%s::uuid[])
                ORDER BY competition.competition_id, fixture.fixture_id
                FOR UPDATE OF competition, fixture SKIP LOCKED LIMIT %s
                """,
                (list(generations), limit),
            )
            fixture_ids = [row[0] for row in cursor.fetchall()]
        claims = claim_forecast_generations(
            self.connection, fixture_ids, expected_generations=generations
        )
        selected = {fixture for fixture, _generation, _claim in claims}
        created = sum(
            self._publish_prepared_forecast(item, knowledge_cutoff, artifact_sha)
            for item in prepared
            if item.fixture_id in selected
        )
        complete_forecast_generations(self.connection, claims)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT count(*) FROM football.product_forecast_refresh_work
                   WHERE generation > completed_generation"""
            )
            remaining = cursor.fetchone()
        return {
            "forecasts_created": created,
            "fixtures_processed": len(claims),
            "fixtures_pending": remaining[0] if remaining is not None else 0,
        }

    def _publish_forecast(
        self,
        fixture_id: UUID,
        home_id: UUID,
        away_id: UUID,
        kickoff_at: datetime,
        now: datetime,
        history: list[FinishedMatch],
        artifact_sha: str,
        parameters: TransferableParametersV1,
    ) -> int:
        if any(match.fixture_id == fixture_id for match in history):
            raise ValueError("forecast history must not contain the target fixture")
        window = forecast_history_window(history, kickoff_at, home_id, away_id)
        forecast = forecast_from_history(
            artifact_path=self.artifact_path,
            target_kickoff=kickoff_at,
            home_team_id=home_id,
            away_team_id=away_id,
            history=window or (),
            parameters=parameters,
        )
        return self._publish_prepared_forecast(
            _PreparedForecast(fixture_id, home_id, away_id, kickoff_at, window, forecast, False),
            now,
            artifact_sha,
        )

    def _publish_prepared_forecast(
        self, item: _PreparedForecast, now: datetime, artifact_sha: str
    ) -> int:
        fixture_id, home_id, away_id, kickoff_at = (
            item.fixture_id,
            item.home_id,
            item.away_id,
            item.kickoff_at,
        )
        window, forecast = item.window, item.forecast
        self.connection.execute("SELECT football.authorize_worker_publication()")
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT 1 FROM football.product_competitions competition
                   JOIN football.product_fixtures fixture USING (competition_id)
                   WHERE fixture_id = %s
                     AND football.product_fixture_team_at(fixture_id, home_team_id, %s)
                         IS NOT DISTINCT FROM %s
                     AND football.product_fixture_team_at(fixture_id, away_team_id, %s)
                         IS NOT DISTINCT FROM %s
                     AND kickoff_at = %s AND (%s OR kickoff_at > clock_timestamp())
                     AND status = 'SCHEDULED' AND identity_status = 'VERIFIED'
                   FOR UPDATE OF competition, fixture SKIP LOCKED""",
                (fixture_id, now, home_id, now, away_id, kickoff_at, item.blocked),
            )
            if cursor.fetchone() is None:
                return 0
        if item.blocked:
            self.connection.execute(
                "UPDATE football.product_fixtures "
                "SET forecast_availability='SOURCE_DATA_INCOMPLETE' "
                "WHERE fixture_id=%s",
                (fixture_id,),
            )
            return 0
        if forecast is None:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE football.product_fixtures
                          SET forecast_availability = 'NOT_ENOUGH_HISTORY'
                        WHERE fixture_id = %s AND kickoff_at > clock_timestamp()""",
                    (fixture_id,),
                )
            return 0
        payload = forecast_payload(forecast)
        payload_sha = sha256_json(payload)
        assert window is not None
        predictive_input_sha = forecast_input_sha(fixture_id, kickoff_at, home_id, away_id, window)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT forecast_id, model_artifact_sha256, model_algorithm_version,
                       score_matrix_version
                FROM football.product_forecasts
                WHERE fixture_id = %s AND model_algorithm_version IN (
                    'transferable-rolling-goals-poisson-v1',
                    'transferable-rolling-goals-poisson-v1-rolling10-v2')
                ORDER BY created_at DESC, forecast_id DESC LIMIT 1
                """,
                (fixture_id,),
            )
            previous = cursor.fetchone()
            cursor.execute(
                """
                SELECT context_snapshot_sha256, source_information_ids
                FROM football.product_context_snapshots
                WHERE fixture_id = %s AND knowledge_cutoff <= %s
                ORDER BY knowledge_cutoff DESC, context_snapshot_id DESC LIMIT 1
                """,
                (fixture_id, now),
            )
            context_row = cursor.fetchone()
        context_sha = context_row[0] if context_row is not None else sha256_json({})
        context_information_ids = context_row[1] if context_row is not None else []
        new_information_ids = sorted(
            {str(value) for value in context_information_ids}
            | {str(match.fixture_id) for match in window}
        )
        if previous is None:
            revision_reasons = [RevisionReason.INITIAL_FORECAST.value]
        elif previous[1] != artifact_sha:
            revision_reasons = [RevisionReason.MODEL_ARTIFACT_CHANGED.value]
        elif previous[2] != PRODUCT_FORECAST_ALGORITHM_VERSION:
            revision_reasons = [RevisionReason.PREDICTIVE_INPUT_CONTRACT_CHANGED.value]
        elif previous[3] != forecast.score_matrix_version:
            revision_reasons = [RevisionReason.SERIALIZATION_CONTRACT_CHANGED.value]
        else:
            revision_reasons = [RevisionReason.BASELINE_HISTORY_CHANGED.value]
        semantic_sha = sha256_json(
            {
                "fixture_id": str(fixture_id),
                "artifact_sha256": artifact_sha,
                "predictive_input_snapshot_sha256": predictive_input_sha,
                "score_matrix_version": forecast.score_matrix_version,
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
            "total_over_1_5": sum(forecast.total_goal_distribution[2:]),
            "total_over_2_5": sum(forecast.total_goal_distribution[3:]),
            "total_under_3_5": sum(forecast.total_goal_distribution[:4]),
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
                    , forecast_horizon, supersedes_forecast_id,
                    predictive_input_snapshot_sha256, context_snapshot_sha256,
                    revision_reason_codes, new_information_ids, score_matrix_version
                ) SELECT %s, %s, %s, 'MVP_FORECAST',
                    %s, %s, %s, %s, %s,
                    'bitemporal', %s, %s, %s::jsonb, %s::jsonb, %s,
                    'MVP_OWNER_AUTHORIZED', %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s
                WHERE %s > clock_timestamp()
                ON CONFLICT (semantic_sha256) DO NOTHING
                """,
                (
                    forecast_id,
                    semantic_sha,
                    fixture_id,
                    PRODUCT_FORECAST_ALGORITHM_VERSION,
                    artifact_sha,
                    now,
                    now,
                    now,
                    forecast.expected_home_goals,
                    forecast.expected_away_goals,
                    json.dumps(probabilities),
                    json.dumps(forecast.score_matrix),
                    payload_sha,
                    classify_horizon(now, kickoff_at).value,
                    previous[0] if previous is not None else None,
                    predictive_input_sha,
                    context_sha,
                    json.dumps(revision_reasons),
                    json.dumps(new_information_ids),
                    forecast.score_matrix_version,
                    kickoff_at,
                ),
            )
            created = cursor.rowcount
            cursor.execute(
                """
                UPDATE football.product_fixtures
                SET forecast_availability = 'FORECAST_AVAILABLE'
                WHERE fixture_id = %s AND kickoff_at > clock_timestamp()
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
                  AND pf.kickoff_at > clock_timestamp()
                """,
                (now, fixture_id),
            )
        return created

    def _batch_history(
        self, targets: Sequence[tuple[UUID, UUID, UUID, datetime]], now: datetime
    ) -> dict[UUID, list[tuple[FinishedMatch, str]]]:
        teams = sorted({team for _, home, away, _ in targets for team in (home, away)}, key=str)
        latest_kickoff = max(kickoff for _, _, _, kickoff in targets)
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture_id, kickoff_at, home_team_id, away_team_id,
                       home_goals, away_goals, home_xg, away_xg,
                       source_kickoff_precision
                FROM football.product_eligible_history_at(%s)
                WHERE kickoff_at < %s
                  AND fixture_id <> ALL(%s::uuid[])
                  AND (home_team_id = ANY(%s::uuid[])
                       OR away_team_id = ANY(%s::uuid[]))
                  AND known_at <= %s
                ORDER BY kickoff_at, fixture_id
                """,
                (now, latest_kickoff, [fixture for fixture, _, _, _ in targets], teams, teams, now),
            )
            rows = cursor.fetchall()
        by_team: dict[UUID, list[tuple[FinishedMatch, str]]] = {}
        for *match_fields, precision in rows:
            match = FinishedMatch(*match_fields)
            for team in (match.home_team_id, match.away_team_id):
                if team in teams:
                    by_team.setdefault(team, []).append((match, precision))
        return by_team

    @staticmethod
    def _target_history(
        by_team: Mapping[UUID, list[tuple[FinishedMatch, str]]],
        home_id: UUID,
        away_id: UUID,
        cutoff: datetime,
    ) -> list[FinishedMatch]:
        matches: dict[UUID, FinishedMatch] = {}
        for match, precision in by_team.get(home_id, []) + by_team.get(away_id, []):
            if (precision == "EXACT" and match.kickoff_at < cutoff) or (
                precision == "DATE_ONLY" and match.kickoff_at.date() < cutoff.date()
            ):
                matches[match.fixture_id] = match
        return sorted(matches.values(), key=lambda match: (match.kickoff_at, match.fixture_id))

    def _history_before(
        self,
        cutoff: datetime,
        home_team_id: UUID,
        away_team_id: UUID,
        *,
        knowledge_cutoff: datetime | None = None,
    ) -> list[FinishedMatch]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT fixture_id, kickoff_at, home_team_id, away_team_id,
                       home_goals, away_goals, home_xg, away_xg
                FROM football.product_eligible_history_at(%s)
                WHERE (
                    (source_kickoff_precision = 'EXACT' AND kickoff_at < %s)
                    OR (
                        source_kickoff_precision = 'DATE_ONLY'
                        AND kickoff_at::date < %s::date
                    )
                )
                AND (
                    home_team_id IN (%s, %s) OR away_team_id IN (%s, %s)
                )
                AND known_at <= %s
                ORDER BY kickoff_at, fixture_id
                """,
                (
                    knowledge_cutoff or cutoff,
                    cutoff,
                    cutoff,
                    home_team_id,
                    away_team_id,
                    home_team_id,
                    away_team_id,
                    knowledge_cutoff or cutoff,
                ),
            )
            return [FinishedMatch(*row) for row in cursor.fetchall()]
