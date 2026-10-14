-- +goose Up
-- NULL identifies the immutable legacy compact-index representation without rewriting it.
ALTER TABLE football.product_forecasts ADD COLUMN score_matrix_version text
    CHECK (score_matrix_version = 'compact-buckets-v2');

DROP INDEX football.product_forecasts_predictive_revision_idx;
CREATE UNIQUE INDEX product_forecasts_predictive_revision_idx
    ON football.product_forecasts (
        fixture_id, model_algorithm_version, model_artifact_sha256,
        predictive_input_snapshot_sha256,
        COALESCE(score_matrix_version, 'legacy-compact-index-v1')
    );

SELECT football.enqueue_product_forecast_refresh(fixture_id)
FROM football.product_fixtures
WHERE status = 'SCHEDULED' AND identity_status = 'VERIFIED'
  AND kickoff_at > clock_timestamp()
ORDER BY fixture_id;

-- +goose Down
-- Different serialization revisions must remain distinguishable and immutable.
-- +goose StatementBegin
DO $$ BEGIN RAISE EXCEPTION 'score bucket serialization is a forward-only migration'; END $$;
-- +goose StatementEnd
