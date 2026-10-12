-- +goose Up

DROP INDEX football.product_sync_runs_one_active_idx;

CREATE UNIQUE INDEX product_sync_runs_one_active_lane_idx
    ON football.product_sync_runs ((CASE
        WHEN sync_type = 'FOTMOB_SYNC' THEN 'LIVE_FOTMOB'
        WHEN sync_type = 'PITCHAPI_SYNC' THEN 'LIVE_PITCHAPI'
        ELSE 'BULK'
    END))
    WHERE status IN ('QUEUED', 'RUNNING');

ALTER TABLE football.product_provider_fixture_observations
    ADD COLUMN result_score_basis text NOT NULL DEFAULT 'UNKNOWN'
        CHECK (result_score_basis IN (
            'REGULATION_90', 'EXTRA_TIME', 'PENALTY_SHOOTOUT', 'UNKNOWN'
        ));

-- +goose Down

DROP INDEX football.product_sync_runs_one_active_lane_idx;

ALTER TABLE football.product_provider_fixture_observations
    DROP COLUMN result_score_basis;

CREATE UNIQUE INDEX product_sync_runs_one_active_idx
    ON football.product_sync_runs ((true))
    WHERE status IN ('QUEUED', 'RUNNING');
