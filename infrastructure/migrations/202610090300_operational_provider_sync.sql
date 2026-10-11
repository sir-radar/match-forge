-- +goose Up

ALTER TABLE football.product_sync_runs
    DROP CONSTRAINT product_sync_runs_sync_type_check;

ALTER TABLE football.product_sync_runs
    ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (sync_type IN (
        'MVP_SYNC', 'OPENFOOTBALL', 'FOOTBALL_DATA_UK', 'HISTORY_BACKFILL',
        'FORECAST_REFRESH', 'EXTERNAL_PREDICTIONS', 'FOTMOB_SYNC',
        'PITCHAPI_SYNC', 'ALL_DATA'
    ));

ALTER TABLE football.product_fixtures
    DROP CONSTRAINT product_fixtures_status_check;

ALTER TABLE football.product_fixtures
    ADD CONSTRAINT product_fixtures_status_check CHECK (status IN (
        'SCHEDULED', 'LIVE', 'HALF_TIME', 'FINISHED', 'POSTPONED',
        'CANCELLED', 'ABANDONED', 'SUSPENDED', 'INTERRUPTED', 'AWARDED'
    ));

ALTER TABLE football.product_fixtures
    DROP CONSTRAINT product_fixtures_check1;

ALTER TABLE football.product_fixtures
    ADD CONSTRAINT product_fixtures_score_state_check CHECK (
        status <> 'FINISHED' OR (home_score IS NOT NULL AND away_score IS NOT NULL)
    );

CREATE TABLE football.product_provider_fixture_observations (
    observation_id uuid PRIMARY KEY DEFAULT uuidv7(),
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    provider_code text NOT NULL CHECK (provider_code <> ''),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    canonical_fixture_id uuid REFERENCES football.product_fixtures (fixture_id),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    kickoff_at timestamptz NOT NULL,
    canonical_status text NOT NULL CHECK (canonical_status IN (
        'SCHEDULED', 'LIVE', 'HALF_TIME', 'FINISHED', 'POSTPONED',
        'CANCELLED', 'ABANDONED', 'SUSPENDED', 'INTERRUPTED', 'AWARDED'
    )),
    provider_status text,
    home_score smallint CHECK (home_score >= 0),
    away_score smallint CHECK (away_score >= 0),
    match_minute smallint CHECK (match_minute >= 0 AND match_minute <= 180),
    added_time smallint CHECK (added_time >= 0 AND added_time <= 30),
    period text,
    source_updated_at timestamptz,
    observed_at timestamptz NOT NULL,
    cache_expires_at timestamptz,
    stale_after timestamptz NOT NULL,
    CHECK ((home_score IS NULL) = (away_score IS NULL)),
    CHECK (source_updated_at IS NULL OR source_updated_at <= observed_at + interval '5 minutes')
);

CREATE INDEX product_provider_fixture_latest_idx
    ON football.product_provider_fixture_observations (
        canonical_fixture_id, observed_at DESC, observation_id DESC
    ) WHERE canonical_fixture_id IS NOT NULL;

CREATE INDEX product_provider_fixture_provider_idx
    ON football.product_provider_fixture_observations (
        provider_code, provider_match_id, observed_at DESC
    );

CREATE TABLE football.product_provider_resource_observations (
    resource_observation_id uuid PRIMARY KEY DEFAULT uuidv7(),
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    provider_code text NOT NULL CHECK (provider_code <> ''),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    canonical_fixture_id uuid REFERENCES football.product_fixtures (fixture_id),
    resource_type text NOT NULL CHECK (resource_type IN (
        'MATCH_DETAILS', 'EVENTS', 'STATISTICS', 'SHOTS', 'MOMENTUM',
        'LINEUPS', 'PLAYER_RATINGS', 'H2H'
    )),
    availability_status text NOT NULL CHECK (availability_status IN (
        'AVAILABLE', 'PARTIAL', 'UNAVAILABLE'
    )),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    source_checksum football.sha256_hex NOT NULL,
    observed_at timestamptz NOT NULL,
    known_at timestamptz,
    point_in_time_eligibility text NOT NULL CHECK (point_in_time_eligibility IN (
        'ELIGIBLE', 'UNKNOWN', 'INELIGIBLE_POST_MATCH'
    )),
    development_only boolean NOT NULL DEFAULT true CHECK (development_only),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload) IN ('object', 'array'))
);

CREATE INDEX product_provider_resource_fixture_idx
    ON football.product_provider_resource_observations (
        canonical_fixture_id, resource_type, observed_at DESC
    ) WHERE canonical_fixture_id IS NOT NULL;

ALTER TABLE football.external_predictions
    ADD COLUMN source_kickoff_at timestamptz,
    ADD COLUMN source_timezone text,
    ADD COLUMN provider_code text,
    ADD COLUMN provider_fixture_id text,
    ADD COLUMN mapping_provenance jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(mapping_provenance) = 'object'),
    ADD CONSTRAINT external_predictions_provider_identity_pair_check CHECK (
        (provider_code IS NULL) = (provider_fixture_id IS NULL)
    );

CREATE TABLE football.external_prediction_result_revisions (
    result_revision_id uuid PRIMARY KEY DEFAULT uuidv7(),
    prediction_id uuid NOT NULL REFERENCES football.external_predictions (prediction_id),
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    settlement_state text NOT NULL CHECK (settlement_state IN (
        'WON', 'LOST', 'VOID', 'PENDING'
    )),
    fixture_status text NOT NULL,
    home_score smallint,
    away_score smallint,
    score_basis text NOT NULL CHECK (score_basis IN ('REGULATION_90', 'NOT_SETTLED')),
    provider_code text,
    provider_updated_at timestamptz,
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    settled_at timestamptz NOT NULL,
    CHECK ((home_score IS NULL) = (away_score IS NULL))
);

CREATE INDEX external_prediction_result_revision_latest_idx
    ON football.external_prediction_result_revisions (
        prediction_id, settled_at DESC, result_revision_id DESC
    );

-- +goose Down

DROP TABLE football.external_prediction_result_revisions;
ALTER TABLE football.external_predictions
    DROP COLUMN mapping_provenance,
    DROP COLUMN provider_fixture_id,
    DROP COLUMN provider_code,
    DROP COLUMN source_timezone,
    DROP COLUMN source_kickoff_at;
DROP TABLE football.product_provider_resource_observations;
DROP TABLE football.product_provider_fixture_observations;
ALTER TABLE football.product_fixtures DROP CONSTRAINT product_fixtures_score_state_check;
ALTER TABLE football.product_fixtures ADD CONSTRAINT product_fixtures_check1 CHECK (
    (status = 'FINISHED') = (home_score IS NOT NULL AND away_score IS NOT NULL)
);
ALTER TABLE football.product_fixtures DROP CONSTRAINT product_fixtures_status_check;
ALTER TABLE football.product_fixtures ADD CONSTRAINT product_fixtures_status_check CHECK (
    status IN ('SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', 'CANCELLED', 'ABANDONED')
);
ALTER TABLE football.product_sync_runs DROP CONSTRAINT product_sync_runs_sync_type_check;
ALTER TABLE football.product_sync_runs ADD CONSTRAINT product_sync_runs_sync_type_check CHECK (
    sync_type IN ('MVP_SYNC', 'OPENFOOTBALL', 'FOOTBALL_DATA_UK', 'HISTORY_BACKFILL',
                  'FORECAST_REFRESH', 'EXTERNAL_PREDICTIONS', 'ALL_DATA')
);
