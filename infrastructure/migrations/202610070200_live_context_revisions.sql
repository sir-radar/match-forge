-- +goose Up

CREATE TABLE football.product_context_capabilities (
    competition_id uuid NOT NULL REFERENCES football.product_competitions (competition_id),
    provider text NOT NULL CHECK (provider <> ''),
    resource text NOT NULL CHECK (resource IN ('INJURIES', 'SUSPENSIONS', 'LINEUPS')),
    status text NOT NULL CHECK (status IN (
        'SUPPORTED', 'UNSUPPORTED_BY_COMPETITION', 'PLAN_RESTRICTION', 'UNKNOWN'
    )),
    observed_at timestamptz NOT NULL,
    source_snapshot_id uuid REFERENCES football.source_snapshots (id),
    PRIMARY KEY (competition_id, provider, resource)
);

CREATE TABLE football.product_availability_observations (
    observation_id uuid PRIMARY KEY,
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures (fixture_id),
    team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    canonical_player_id uuid REFERENCES football.players (id),
    provider_player_id text NOT NULL CHECK (provider_player_id <> ''),
    availability_type text NOT NULL CHECK (availability_type IN ('INJURY', 'SUSPENSION', 'OTHER')),
    availability_state text NOT NULL CHECK (availability_state IN (
        'AVAILABLE_CONFIRMED', 'UNAVAILABLE_INJURY', 'UNAVAILABLE_SUSPENSION',
        'UNAVAILABLE_OTHER', 'ASSUMED_AVAILABLE_NO_REPORTED_ISSUE',
        'AVAILABILITY_UNVERIFIED', 'UNKNOWN'
    )),
    reason text,
    observed_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    provider text NOT NULL CHECK (provider <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    source_checksum football.sha256_hex NOT NULL,
    CHECK (known_at >= observed_at),
    UNIQUE (
        fixture_id, team_id, provider_player_id, availability_type,
        availability_state, source_checksum
    )
);

CREATE INDEX product_availability_point_in_time_idx
    ON football.product_availability_observations (
        fixture_id, team_id, known_at DESC, observed_at DESC
    );

CREATE TABLE football.product_coach_observations (
    coach_observation_id uuid PRIMARY KEY,
    team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    coach_id uuid NOT NULL,
    provider_coach_id text,
    effective_at timestamptz NOT NULL,
    observed_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    provider text NOT NULL CHECK (provider <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    source_checksum football.sha256_hex NOT NULL,
    CHECK (known_at >= observed_at),
    UNIQUE (team_id, coach_id, effective_at, source_checksum)
);

CREATE INDEX product_coach_point_in_time_idx
    ON football.product_coach_observations (team_id, effective_at DESC, known_at DESC);

CREATE TABLE football.product_lineup_observations (
    lineup_observation_id uuid PRIMARY KEY,
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures (fixture_id),
    team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    kickoff_at timestamptz NOT NULL,
    lineup_mode text NOT NULL CHECK (lineup_mode IN (
        'CONFIRMED', 'PREDICTED_REPEAT_XI', 'UNKNOWN'
    )),
    formation text,
    coach_id uuid,
    provider_coach_id text,
    prediction_confidence text CHECK (prediction_confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    coach_context text CHECK (coach_context IN ('KNOWN', 'UNKNOWN')),
    preference_sample_size smallint CHECK (preference_sample_size >= 0),
    based_on_lineup_id uuid REFERENCES football.product_lineup_observations (lineup_observation_id),
    supersedes_predicted_lineup_id uuid
        REFERENCES football.product_lineup_observations (lineup_observation_id),
    observed_at timestamptz NOT NULL,
    known_at timestamptz NOT NULL,
    provider text NOT NULL CHECK (provider <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    source_checksum football.sha256_hex NOT NULL,
    CHECK (known_at >= observed_at),
    CHECK (lineup_mode <> 'CONFIRMED' OR prediction_confidence IS NULL),
    CHECK (lineup_mode <> 'PREDICTED_REPEAT_XI' OR prediction_confidence IS NOT NULL),
    CHECK (
        supersedes_predicted_lineup_id IS NULL
        OR lineup_mode = 'CONFIRMED'
    ),
    UNIQUE (fixture_id, team_id, lineup_mode, source_checksum)
);

CREATE INDEX product_lineup_point_in_time_idx
    ON football.product_lineup_observations (
        team_id, kickoff_at DESC, known_at DESC, lineup_mode
    );

CREATE TABLE football.product_lineup_players (
    lineup_observation_id uuid NOT NULL
        REFERENCES football.product_lineup_observations (lineup_observation_id),
    canonical_player_id uuid REFERENCES football.players (id),
    provider_player_id text NOT NULL CHECK (provider_player_id <> ''),
    role text NOT NULL CHECK (role IN ('STARTER', 'BENCH')),
    position text NOT NULL CHECK (position <> ''),
    normalized_position text NOT NULL CHECK (normalized_position <> ''),
    grid_position text,
    slot_order smallint NOT NULL CHECK (slot_order >= 0),
    availability_state text NOT NULL CHECK (availability_state IN (
        'AVAILABLE_CONFIRMED', 'UNAVAILABLE_INJURY', 'UNAVAILABLE_SUSPENSION',
        'UNAVAILABLE_OTHER', 'ASSUMED_AVAILABLE_NO_REPORTED_ISSUE',
        'AVAILABILITY_UNVERIFIED', 'UNKNOWN'
    )),
    selection_reason text,
    replaced_player_id uuid REFERENCES football.players (id),
    replacement_reason text,
    preference_score double precision,
    historical_start_count smallint CHECK (historical_start_count >= 0),
    slot_status text NOT NULL DEFAULT 'RESOLVED' CHECK (slot_status IN ('RESOLVED', 'UNRESOLVED')),
    PRIMARY KEY (lineup_observation_id, provider_player_id),
    UNIQUE (lineup_observation_id, slot_order)
);

CREATE TABLE football.product_lineup_accuracy (
    predicted_lineup_id uuid PRIMARY KEY
        REFERENCES football.product_lineup_observations (lineup_observation_id),
    confirmed_lineup_id uuid NOT NULL UNIQUE
        REFERENCES football.product_lineup_observations (lineup_observation_id),
    correct_starting_players smallint NOT NULL CHECK (
        correct_starting_players BETWEEN 0 AND 11
    ),
    xi_precision double precision NOT NULL CHECK (xi_precision BETWEEN 0 AND 1),
    xi_recall double precision NOT NULL CHECK (xi_recall BETWEEN 0 AND 1),
    formation_match boolean NOT NULL,
    replacement_player_accuracy double precision CHECK (
        replacement_player_accuracy BETWEEN 0 AND 1
    ),
    exact_position_replacement_accuracy double precision CHECK (
        exact_position_replacement_accuracy BETWEEN 0 AND 1
    ),
    coach_preference_sample_size smallint NOT NULL CHECK (
        coach_preference_sample_size >= 0
    ),
    prediction_confidence text NOT NULL CHECK (prediction_confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    calculated_at timestamptz NOT NULL
);

CREATE TABLE football.product_context_snapshots (
    context_snapshot_id uuid PRIMARY KEY,
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures (fixture_id),
    football_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    context_snapshot jsonb NOT NULL CHECK (jsonb_typeof(context_snapshot) = 'object'),
    context_snapshot_sha256 football.sha256_hex NOT NULL,
    source_information_ids jsonb NOT NULL CHECK (jsonb_typeof(source_information_ids) = 'array'),
    created_at timestamptz NOT NULL,
    UNIQUE (fixture_id, context_snapshot_sha256)
);

ALTER TABLE football.product_forecasts
    ADD COLUMN forecast_horizon text CHECK (forecast_horizon IN (
        'EARLY_GT_7D', '7D', '3D', '24H', '6H', '1H', '15M', 'CONFIRMED_LINEUP'
    )),
    ADD COLUMN supersedes_forecast_id uuid REFERENCES football.product_forecasts (forecast_id),
    ADD COLUMN predictive_input_snapshot_sha256 football.sha256_hex,
    ADD COLUMN context_snapshot_sha256 football.sha256_hex,
    ADD COLUMN revision_reason_codes jsonb CHECK (
        revision_reason_codes IS NULL OR jsonb_typeof(revision_reason_codes) = 'array'
    ),
    ADD COLUMN new_information_ids jsonb CHECK (
        new_information_ids IS NULL OR jsonb_typeof(new_information_ids) = 'array'
    );

-- Existing forecasts predate revision metadata. Backfill only the new columns while
-- the row-immutability trigger is suspended inside this transactional migration.
ALTER TABLE football.product_forecasts
    DISABLE TRIGGER product_forecasts_immutable;

UPDATE football.product_forecasts
SET predictive_input_snapshot_sha256 = semantic_sha256,
    context_snapshot_sha256 = '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
    forecast_horizon = 'EARLY_GT_7D',
    revision_reason_codes = '["INITIAL_FORECAST"]'::jsonb,
    new_information_ids = '[]'::jsonb
WHERE predictive_input_snapshot_sha256 IS NULL;

ALTER TABLE football.product_forecasts
    ENABLE TRIGGER product_forecasts_immutable;

ALTER TABLE football.product_forecasts
    ALTER COLUMN forecast_horizon SET NOT NULL,
    ALTER COLUMN predictive_input_snapshot_sha256 SET NOT NULL,
    ALTER COLUMN context_snapshot_sha256 SET NOT NULL,
    ALTER COLUMN revision_reason_codes SET NOT NULL,
    ALTER COLUMN new_information_ids SET NOT NULL;

CREATE UNIQUE INDEX product_forecasts_predictive_revision_idx
    ON football.product_forecasts (
        fixture_id, model_algorithm_version, model_artifact_sha256,
        predictive_input_snapshot_sha256
    );

-- +goose StatementBegin
CREATE FUNCTION football.guard_live_context_immutable() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'live context observations and snapshots are immutable';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER product_availability_observations_immutable
BEFORE UPDATE OR DELETE ON football.product_availability_observations
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();
CREATE TRIGGER product_coach_observations_immutable
BEFORE UPDATE OR DELETE ON football.product_coach_observations
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();
CREATE TRIGGER product_lineup_observations_immutable
BEFORE UPDATE OR DELETE ON football.product_lineup_observations
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();
CREATE TRIGGER product_lineup_players_immutable
BEFORE UPDATE OR DELETE ON football.product_lineup_players
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();
CREATE TRIGGER product_lineup_accuracy_immutable
BEFORE UPDATE OR DELETE ON football.product_lineup_accuracy
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();
CREATE TRIGGER product_context_snapshots_immutable
BEFORE UPDATE OR DELETE ON football.product_context_snapshots
FOR EACH ROW EXECUTE FUNCTION football.guard_live_context_immutable();

-- +goose Down

DROP TRIGGER product_context_snapshots_immutable ON football.product_context_snapshots;
DROP TRIGGER product_lineup_accuracy_immutable ON football.product_lineup_accuracy;
DROP TRIGGER product_lineup_players_immutable ON football.product_lineup_players;
DROP TRIGGER product_lineup_observations_immutable ON football.product_lineup_observations;
DROP TRIGGER product_coach_observations_immutable ON football.product_coach_observations;
DROP TRIGGER product_availability_observations_immutable ON football.product_availability_observations;
DROP FUNCTION football.guard_live_context_immutable();
DROP INDEX football.product_forecasts_predictive_revision_idx;
ALTER TABLE football.product_forecasts
    DROP COLUMN new_information_ids,
    DROP COLUMN revision_reason_codes,
    DROP COLUMN context_snapshot_sha256,
    DROP COLUMN predictive_input_snapshot_sha256,
    DROP COLUMN supersedes_forecast_id,
    DROP COLUMN forecast_horizon;
DROP TABLE football.product_context_snapshots;
DROP TABLE football.product_lineup_accuracy;
DROP TABLE football.product_lineup_players;
DROP TABLE football.product_lineup_observations;
DROP TABLE football.product_coach_observations;
DROP TABLE football.product_availability_observations;
DROP TABLE football.product_context_capabilities;
