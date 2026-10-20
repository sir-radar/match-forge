-- +goose Up

-- Current operational analytics inputs extend the existing selection owner.
-- Forecast bytes, historical evaluation criteria and model artifacts stay unchanged.
-- +goose StatementBegin
CREATE FUNCTION football.public_performance_rows(competition_key uuid,horizon_seconds integer)
RETURNS TABLE (
    competition_id uuid,fixture_id uuid,kickoff_at timestamptz,
    home_score smallint,away_score smallint,outcome_known_at timestamptz,
    forecast_id uuid,issued_at timestamptz,knowledge_cutoff timestamptz,
    probabilities jsonb,score_matrix jsonb,score_matrix_version text,model_algorithm_version text,
    forecast_payload_sha256 football.sha256_hex,model_artifact_sha256 football.sha256_hex,
    football_cutoff timestamptz
) LANGUAGE sql STABLE AS $$
    SELECT p.*,f.payload_sha256,f.model_artifact_sha256,f.football_cutoff
    FROM football.product_performance_forecasts(ARRAY[competition_key],horizon_seconds) p
    JOIN football.product_forecasts f ON f.forecast_id=p.forecast_id
$$;
-- +goose StatementEnd

-- This SQL fingerprint invalidates a derived read report. It is not a model-state
-- hash or a replacement for MatchForge's canonical artifact serialization.
-- +goose StatementBegin
CREATE FUNCTION football.public_performance_source(competition_key uuid,horizon_seconds integer)
RETURNS TABLE (source_fingerprint football.sha256_hex,record_count bigint)
LANGUAGE sql STABLE SET timezone='UTC' AS $$
    SELECT encode(sha256(convert_to(coalesce(jsonb_agg(jsonb_build_array(
        p.fixture_id,p.forecast_id,p.kickoff_at,p.home_score,p.away_score,p.outcome_known_at,
        p.issued_at,p.knowledge_cutoff,p.football_cutoff,p.score_matrix_version,
        p.model_algorithm_version,p.forecast_payload_sha256,p.model_artifact_sha256
    ) ORDER BY p.kickoff_at,p.fixture_id),'[]'::jsonb)::text,'UTF8')),'hex')::football.sha256_hex,
    count(*) FROM football.public_performance_rows(competition_key,horizon_seconds) p
$$;
-- +goose StatementEnd

-- Eligible facts only: the target fixture is excluded even if an older revision
-- gives it an earlier kickoff. Display names are metadata, never identity keys.
-- +goose StatementBegin
CREATE FUNCTION football.public_context_source(fixture_key uuid)
RETURNS jsonb LANGUAGE sql STABLE SET timezone='UTC' AS $$
    WITH target AS (
        SELECT fixture_id,competition_id,kickoff_at,
            LEAST(kickoff_at,statement_timestamp()) AS knowledge_cutoff,
            football.product_fixture_team_at(fixture_id,home_team_id,
                LEAST(kickoff_at,statement_timestamp())) AS home_team_id,
            football.product_fixture_team_at(fixture_id,away_team_id,
                LEAST(kickoff_at,statement_timestamp())) AS away_team_id
        FROM football.product_fixtures WHERE fixture_id=fixture_key
    ), history AS (
        SELECT h.*,home.name AS home_team,away.name AS away_team
        FROM target t
        CROSS JOIN LATERAL football.product_eligible_team_history_at(
            t.knowledge_cutoff,ARRAY[t.home_team_id,t.away_team_id]) h
        JOIN football.product_teams home ON home.team_id=h.home_team_id
        JOIN football.product_teams away ON away.team_id=h.away_team_id
        WHERE h.fixture_id<>t.fixture_id AND h.known_at<=t.knowledge_cutoff
          AND ((h.source_kickoff_precision='EXACT' AND h.kickoff_at<t.kickoff_at)
            OR (h.source_kickoff_precision='DATE_ONLY' AND h.kickoff_at::date<t.kickoff_at::date))
    ), teams AS (
        SELECT t.*,unnest(ARRAY[t.home_team_id,t.away_team_id]) AS team_id FROM target t
    ), coaches AS (
        SELECT team.team_id,coach.coach_id,coach.coach_observation_id,
            coach.effective_at,coach.observed_at,coach.known_at,coach.provider,
            coach.source_snapshot_id,coach.source_checksum,
            (SELECT coalesce(jsonb_agg(jsonb_build_object(
                'lineup_observation_id',l.lineup_observation_id,'kickoff_at',l.kickoff_at,
                'known_at',l.known_at,'source_snapshot_id',l.source_snapshot_id,
                'source_checksum',l.source_checksum
             ) ORDER BY l.kickoff_at,l.lineup_observation_id),'[]')
             FROM football.product_lineup_observations l
             WHERE l.team_id=team.team_id AND l.coach_id=coach.coach_id
               AND l.fixture_id<>team.fixture_id AND l.lineup_mode='CONFIRMED'
               AND l.kickoff_at<team.kickoff_at AND l.known_at<=team.knowledge_cutoff
            ) AS prior_lineups
        FROM teams team JOIN LATERAL (
            SELECT c.* FROM football.product_coach_observations c
            WHERE c.team_id=team.team_id AND c.effective_at<team.kickoff_at
              AND c.known_at<=team.knowledge_cutoff
            ORDER BY c.effective_at DESC,c.known_at DESC,c.coach_observation_id DESC LIMIT 1
        ) coach ON true
    ), upcoming AS (
        SELECT team.team_id,f.kickoff_at AS next_kickoff,f.fixture_id,f.updated_at
        FROM teams team LEFT JOIN LATERAL (
            SELECT pf.fixture_id,pf.kickoff_at,pf.updated_at FROM football.product_fixtures pf
            WHERE (pf.home_team_id=team.team_id OR pf.away_team_id=team.team_id)
              AND pf.fixture_id<>team.fixture_id AND pf.kickoff_at>team.kickoff_at
              AND pf.updated_at<=team.knowledge_cutoff
            ORDER BY pf.kickoff_at,pf.fixture_id LIMIT 1
        ) f ON true
    )
    SELECT jsonb_build_object(
        'fixture_id',t.fixture_id,'competition_id',t.competition_id,
        'kickoff_at',t.kickoff_at,'home_team_id',t.home_team_id,'away_team_id',t.away_team_id,
        'history',(SELECT coalesce(jsonb_agg(to_jsonb(h) ORDER BY h.kickoff_at DESC,h.fixture_id),'[]') FROM history h),
        'coaches',(SELECT coalesce(jsonb_agg(to_jsonb(c) ORDER BY c.team_id),'[]') FROM coaches c),
        'upcoming',(SELECT coalesce(jsonb_agg(to_jsonb(u) ORDER BY u.team_id),'[]') FROM upcoming u)
    ) FROM target t
$$;
-- +goose StatementEnd

-- Current descriptive comparison, not an authoritative historical evaluation.
-- Forecast selection preserves the existing operational latest-revision policy.
-- +goose StatementBegin
CREATE FUNCTION football.public_comparison_source(prediction_key uuid)
RETURNS jsonb LANGUAGE sql STABLE SET timezone='UTC' AS $$
    SELECT jsonb_build_object('prediction_id',ep.prediction_id,'market',ep.market,
        'selection',ep.selection,'fixture_id',ep.fixture_id,'forecast_id',f.forecast_id,
        'forecast_payload_sha256',f.payload_sha256,'probabilities',f.probabilities)
    FROM football.external_predictions ep
    LEFT JOIN LATERAL (
        SELECT forecast_id,payload_sha256,probabilities FROM football.product_forecasts
        WHERE fixture_id=ep.fixture_id ORDER BY created_at DESC,forecast_id DESC LIMIT 1
    ) f ON true WHERE ep.prediction_id=prediction_key
$$;
-- +goose StatementEnd

CREATE TABLE football.product_read_reports (
    input_sha256 football.sha256_hex PRIMARY KEY,
    work_id uuid NOT NULL REFERENCES football.work_items(work_id),
    report_kind text NOT NULL CHECK (report_kind IN ('PERFORMANCE','CONTEXT','COMPARISON')),
    scope_id uuid NOT NULL,
    horizon text NOT NULL CHECK (horizon IN ('LATEST','7D','3D','24H','6H','1H','15M')),
    source_fingerprint football.sha256_hex NOT NULL,
    source_observed_at timestamptz NOT NULL CHECK (isfinite(source_observed_at)),
    input_bytes bytea NOT NULL,
    record_bytes bytea NOT NULL,
    record_sha256 football.sha256_hex NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (isfinite(registered_at) AND registered_at>=source_observed_at),
    CHECK (encode(sha256(input_bytes),'hex')=input_sha256),
    CHECK (encode(sha256(record_bytes),'hex')=record_sha256),
    CHECK (convert_from(input_bytes,'UTF8')::jsonb->>'report_kind' IS NOT DISTINCT FROM report_kind),
    CHECK (convert_from(input_bytes,'UTF8')::jsonb->>'scope_id' IS NOT DISTINCT FROM scope_id::text),
    CHECK (convert_from(input_bytes,'UTF8')::jsonb->>'horizon' IS NOT DISTINCT FROM horizon),
    CHECK (convert_from(input_bytes,'UTF8')::jsonb->>'source_fingerprint' IS NOT DISTINCT FROM source_fingerprint),
    CHECK ((convert_from(input_bytes,'UTF8')::jsonb->>'policy_version') IS NOT DISTINCT FROM 'pre-match-revisions-v2'),
    CHECK (coalesce(convert_from(input_bytes,'UTF8')::jsonb->>'code_commit_sha' ~ '^[0-9a-f]{40}$',false)),
    CHECK (coalesce(convert_from(input_bytes,'UTF8')::jsonb->>'dependency_lock_sha256' ~ '^[0-9a-f]{64}$',false))
);
CREATE INDEX product_read_report_current_idx ON football.product_read_reports
    (report_kind,scope_id,horizon,source_fingerprint,source_observed_at DESC,registered_at DESC,input_sha256);
CREATE TRIGGER read_report_immutable BEFORE UPDATE OR DELETE
    ON football.product_read_reports FOR EACH ROW
    EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER read_report_no_truncate BEFORE TRUNCATE
    ON football.product_read_reports FOR EACH STATEMENT
    EXECUTE FUNCTION football.guard_multi_model_immutable();
CREATE TRIGGER read_report_worker_publication BEFORE INSERT
    ON football.product_read_reports FOR EACH STATEMENT
    EXECUTE FUNCTION football.check_worker_publication();

-- +goose Down
-- +goose StatementBegin
DO $$ BEGIN
    RAISE EXCEPTION 'registered read reports retain source and work references; roll forward';
END $$;
-- +goose StatementEnd
