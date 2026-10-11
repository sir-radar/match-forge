-- +goose Up

ALTER TABLE football.product_provider_fixture_observations
    ADD COLUMN provider_competition_name text,
    ADD COLUMN provider_home_team_id text,
    ADD COLUMN provider_home_team_name text,
    ADD COLUMN provider_away_team_id text,
    ADD COLUMN provider_away_team_name text;

CREATE TABLE football.product_provider_mapping_decisions (
    decision_id uuid PRIMARY KEY DEFAULT uuidv7(),
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    provider_code text NOT NULL CHECK (provider_code <> ''),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    candidate_fixture_id uuid REFERENCES football.product_fixtures (fixture_id),
    disposition text NOT NULL CHECK (disposition IN (
        'AUTO_ACCEPTED', 'MANUAL_ACCEPTED', 'REVIEW_REQUIRED', 'CONTRADICTORY'
    )),
    reason text NOT NULL CHECK (reason <> ''),
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX product_provider_mapping_review_idx
    ON football.product_provider_mapping_decisions (
        disposition, provider_code, observed_at DESC, decision_id DESC
    );

CREATE INDEX product_provider_mapping_match_idx
    ON football.product_provider_mapping_decisions (
        provider_code, provider_match_id, observed_at DESC
    );

-- +goose Down

DROP TABLE football.product_provider_mapping_decisions;

ALTER TABLE football.product_provider_fixture_observations
    DROP COLUMN provider_away_team_name,
    DROP COLUMN provider_away_team_id,
    DROP COLUMN provider_home_team_name,
    DROP COLUMN provider_home_team_id,
    DROP COLUMN provider_competition_name;
