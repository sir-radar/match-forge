-- +goose Up
-- Ordered after the external settlement migrations (202611130400-0600). The sync type
-- list keeps EXTERNAL_PREDICTION_SETTLEMENT so either delivery order ends with both.
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC','OPENFOOTBALL','FOOTBALL_DATA_UK','HISTORY_BACKFILL',
        'FORECAST_REFRESH','CONTEXT_REPORTS','PUBLIC_REPORTS','EXTERNAL_PREDICTIONS',
        'EXTERNAL_PREDICTION_SETTLEMENT','FOTMOB_SYNC','PITCHAPI_SYNC','ALL_DATA',
        'MANUAL_BACKUP','STORAGE_LIFECYCLE','RESULT_RECOVERY')
);

-- Current recovery candidates. This view never supplies a historical forecast input.
-- A finished score that already qualified history is not a candidate merely because
-- its source states no match duration (Football-Data.co.uk and OpenFootball full-time
-- scores). Each branch is index- or anti-join-friendly, so the census does not
-- become a per-row history probe over every finished fixture.
CREATE VIEW football.product_result_recovery_candidates AS
WITH candidate AS (
    SELECT f.fixture_id,'OVERDUE_UNFINISHED'::text AS recovery_reason
    FROM football.product_fixtures f
    WHERE f.status IN ('SCHEDULED','LIVE','HALF_TIME','SUSPENDED','INTERRUPTED','POSTPONED')
      AND f.kickoff_at < statement_timestamp()-interval '4 hours'
    UNION ALL
    SELECT f.fixture_id,'MISSING_SCORE'
    FROM football.product_fixtures f
    WHERE f.status='FINISHED' AND (f.home_score IS NULL OR f.away_score IS NULL)
    UNION ALL
    SELECT f.fixture_id,
           CASE f.result_score_basis WHEN 'UNKNOWN' THEN 'SCORE_BASIS_UNKNOWN'
                ELSE 'HISTORY_UNQUALIFIED' END
    FROM football.product_fixtures f
    WHERE f.status='FINISHED' AND f.home_score IS NOT NULL AND f.away_score IS NOT NULL
      AND f.result_score_basis IN ('UNKNOWN','REGULATION_90')
      AND NOT EXISTS (
          SELECT 1 FROM football.product_team_match_history h WHERE h.fixture_id=f.fixture_id
      )
)
SELECT f.fixture_id,f.kickoff_at,f.status,f.identity_status,c.recovery_reason
FROM candidate c
JOIN football.product_fixtures f ON f.fixture_id=c.fixture_id
WHERE NOT EXISTS (
    SELECT 1 FROM football.fixture_identity_resolutions r
    WHERE r.member_fixture_id=c.fixture_id AND r.active
      AND (r.resolution_status NOT IN ('UNIQUE','DUPLICATE_RESOLVED')
           OR r.representative_fixture_id<>c.fixture_id)
);

-- Durable per-fixture, per-provider next action. Date fetches are shared, but
-- eligibility is decided here, so a checked fixture never suppresses a newly eligible
-- fixture on the same UTC date. Provider-enforced deadlines stay where the provider
-- clients already enforce them (football.provider_request_budgets and the
-- API-Football budget); this table only records the consequence for each fixture.
CREATE TABLE football.product_result_recovery_state (
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures(fixture_id) ON DELETE CASCADE,
    provider_code text NOT NULL CHECK (provider_code IN ('fotmob','pitchapi','api_football')),
    purpose text NOT NULL CHECK (purpose IN ('RECOVERY','CORRECTION')),
    outcome text NOT NULL CHECK (outcome IN (
        'RECOVERED','CORRECTED','VERIFIED_UNCHANGED','NOT_RETURNED','NOT_YET_PUBLISHED',
        'SCORE_BASIS_UNAVAILABLE','IDENTITY_UNRESOLVED','RESULT_CONFLICT',
        'QUALIFICATION_FAILED','PROVIDER_UNAVAILABLE','PROVIDER_RATE_LIMITED'
    )),
    attempts integer NOT NULL DEFAULT 1 CHECK (attempts > 0),
    first_checked_at timestamptz NOT NULL,
    last_checked_at timestamptz NOT NULL,
    next_check_at timestamptz NOT NULL,
    last_snapshot_id uuid REFERENCES football.source_snapshots(id),
    detail text,
    PRIMARY KEY (fixture_id, provider_code),
    CHECK (first_checked_at <= last_checked_at)
);
CREATE INDEX product_result_recovery_state_due_idx
    ON football.product_result_recovery_state (provider_code, next_check_at);

-- +goose Down
-- Disable scheduling (MATCHFORGE_RESULT_RECOVERY_INTERVAL=0) and restore the prior
-- worker to roll back. Run history, recovery state and acquired evidence are kept.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'result recovery run history requires a forward repair'; END $$;
-- +goose StatementEnd
