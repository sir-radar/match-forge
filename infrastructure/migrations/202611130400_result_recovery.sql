-- +goose Up
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
        'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
        'FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA','MANUAL_BACKUP','STORAGE_LIFECYCLE','RESULT_RECOVERY')
);

-- Current recovery candidates. This view never supplies a historical forecast input.
CREATE VIEW football.product_result_recovery_candidates AS
SELECT f.fixture_id,f.kickoff_at,f.status,f.identity_status
FROM football.product_fixtures f
WHERE (
    (f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED')
     AND f.kickoff_at < statement_timestamp()-interval '4 hours')
    OR (f.status='FINISHED' AND (
        f.home_score IS NULL OR f.away_score IS NULL OR f.result_score_basis='UNKNOWN'
        OR (f.result_score_basis='REGULATION_90' AND NOT EXISTS (
            SELECT 1 FROM football.product_team_match_history h WHERE h.fixture_id=f.fixture_id
        ))
    ))
) AND NOT EXISTS (
    SELECT 1 FROM football.fixture_identity_resolutions r
    WHERE r.member_fixture_id=f.fixture_id AND r.active
      AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
           OR r.representative_fixture_id<>f.fixture_id)
);

-- +goose Down
-- Disable scheduling and restore the prior worker to roll back while preserving run history.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'result recovery run history requires a forward repair'; END $$;
-- +goose StatementEnd
