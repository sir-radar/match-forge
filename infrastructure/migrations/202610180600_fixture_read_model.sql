-- +goose Up

-- Current serving cache only. Existing dated contracts and original fixture IDs
-- remain authoritative for historical reconstruction and immutable references.
-- Do not route production reads here before the shadow parity/cutover gates.
CREATE MATERIALIZED VIEW football.fixture_read_model AS
SELECT fixture_id,competition_id,home_team_id,away_team_id,kickoff_at,status,
       home_score,away_score,venue,round_name,forecast_availability,updated_at,
       result_score_basis,identity_status
FROM football.product_serving_fixtures
WITH NO DATA;

CREATE UNIQUE INDEX fixture_read_model_fixture_idx
    ON football.fixture_read_model(fixture_id);
CREATE INDEX fixture_read_model_date_idx
    ON football.fixture_read_model(kickoff_at,competition_id);

COMMENT ON MATERIALIZED VIEW football.fixture_read_model IS
    'Rebuildable current fixture projection; product_serving_fixtures remains the serving baseline until cutover.';

-- +goose Down
-- This derived cache contains no authoritative facts or historical identifiers.
DROP MATERIALIZED VIEW football.fixture_read_model;
