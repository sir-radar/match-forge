-- +goose Up

-- Import progress only. Shared operator/history work retains scheduling ownership.
-- Legacy resources without a row retain their existing cache behavior.
CREATE TABLE football.product_history_resource_imports (
    source_resource_id uuid PRIMARY KEY REFERENCES football.source_resources(id),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    CHECK (completed_at IS NULL OR completed_at >= started_at)
);

-- +goose Down

DROP TABLE football.product_history_resource_imports;
