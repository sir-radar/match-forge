-- +goose Up
-- Current product analytics; immutable forecast revisions remain unchanged.
-- +goose StatementBegin
CREATE FUNCTION football.product_performance_forecasts(
    competition_keys uuid[], horizon_seconds integer DEFAULT 0
) RETURNS TABLE (
    competition_id uuid, fixture_id uuid, kickoff_at timestamptz,
    home_score smallint, away_score smallint, outcome_known_at timestamptz,
    forecast_id uuid, issued_at timestamptz, knowledge_cutoff timestamptz,
    probabilities jsonb, score_matrix jsonb, score_matrix_version text,
    model_algorithm_version text
) LANGUAGE sql STABLE AS $$
    SELECT fixture.competition_id,fixture.fixture_id,fixture.kickoff_at,
           fixture.home_score,fixture.away_score,
           CASE WHEN fixture.updated_at > fixture.kickoff_at THEN fixture.updated_at END,
           forecast.forecast_id,forecast.created_at,forecast.knowledge_cutoff,
           forecast.probabilities,forecast.score_matrix,
           COALESCE(forecast.score_matrix_version,'legacy-compact-index-v1'),
           forecast.model_algorithm_version
    FROM football.product_fixtures fixture
    JOIN LATERAL (
        SELECT f.* FROM football.product_forecasts f
        WHERE f.fixture_id=fixture.fixture_id AND f.model_label='MVP_FORECAST'
          AND f.created_at < fixture.kickoff_at
          AND f.created_at <= fixture.kickoff_at - make_interval(secs=>horizon_seconds)
          AND f.football_cutoff <= f.created_at AND f.knowledge_cutoff <= f.created_at
          AND f.football_cutoff < fixture.kickoff_at AND f.knowledge_cutoff < fixture.kickoff_at
        ORDER BY f.created_at DESC,f.forecast_id DESC LIMIT 1
    ) forecast ON true
    WHERE fixture.competition_id=ANY(competition_keys)
      AND horizon_seconds >= 0
      AND fixture.status='FINISHED' AND fixture.result_score_basis='REGULATION_90'
      AND fixture.identity_status='VERIFIED'
      AND NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions resolution
                      WHERE resolution.member_fixture_id=fixture.fixture_id AND resolution.active)
$$;
-- +goose StatementEnd

-- Select candidate fixture IDs with the existing native UUID indexes, then
-- resolve the latest decision at the cutoff, including subsequent revocations.
-- +goose StatementBegin
CREATE FUNCTION football.product_eligible_team_history_at(
    knowledge_time timestamptz, team_keys uuid[]
) RETURNS TABLE (
    fixture_id uuid, competition_id uuid, home_team_id uuid, away_team_id uuid,
    kickoff_at timestamptz, home_goals smallint, away_goals smallint,
    home_xg double precision, away_xg double precision, source_provider_code text,
    source_snapshot_id uuid, source_kickoff_precision text, known_at timestamptz
) LANGUAGE sql STABLE AS $$
    SELECT latest.fixture_id,latest.competition_id,latest.home_team_id,latest.away_team_id,
           latest.kickoff_at,latest.home_goals,latest.away_goals,latest.home_xg,latest.away_xg,
           latest.source_provider_code,latest.source_snapshot_id,latest.source_kickoff_precision,
           GREATEST(latest.source_known_at,latest.decided_at)
    FROM (SELECT DISTINCT d.fixture_id FROM football.product_match_history_decisions d
          WHERE d.decided_at<=knowledge_time
            AND (d.home_team_id=ANY(team_keys) OR d.away_team_id=ANY(team_keys))) candidates
    JOIN LATERAL (
        SELECT d.* FROM football.product_match_history_decisions d
        WHERE d.fixture_id=candidates.fixture_id AND d.decided_at<=knowledge_time
        ORDER BY d.decided_at DESC,d.decision_id DESC LIMIT 1
    ) latest ON true
    WHERE latest.eligible AND latest.source_known_at<=knowledge_time
      AND (latest.home_team_id=ANY(team_keys) OR latest.away_team_id=ANY(team_keys))
$$;
-- +goose StatementEnd

-- +goose Down
DROP FUNCTION football.product_eligible_team_history_at(timestamptz,uuid[]);
DROP FUNCTION football.product_performance_forecasts(uuid[],integer);
