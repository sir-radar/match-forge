-- +goose Up

CREATE TABLE football.product_competitions (
    competition_id uuid PRIMARY KEY REFERENCES football.competitions (id),
    name text NOT NULL CHECK (name <> ''),
    country text NOT NULL CHECK (country <> ''),
    continent text NOT NULL CHECK (continent <> ''),
    division smallint CHECK (division > 0),
    competition_type text NOT NULL CHECK (competition_type IN ('LEAGUE', 'CUP')),
    season_label text NOT NULL CHECK (season_label <> ''),
    fixtures_available boolean NOT NULL DEFAULT false,
    results_available boolean NOT NULL DEFAULT false,
    standings_available boolean NOT NULL DEFAULT false,
    h2h_available boolean NOT NULL DEFAULT false,
    forecast_available boolean NOT NULL DEFAULT false,
    xg_available boolean NOT NULL DEFAULT false,
    team_stats_available boolean NOT NULL DEFAULT false,
    availability_status text NOT NULL CHECK (availability_status IN (
        'FORECAST_AVAILABLE', 'NO_FIXTURES', 'NO_RESULTS', 'NOT_ENOUGH_HISTORY',
        'NO_STANDINGS', 'NO_H2H', 'TEAM_MAPPING_MISSING', 'PROVIDER_LIMIT',
        'RATE_LIMIT', 'USAGE_RESTRICTION', 'SEASON_UNAVAILABLE',
        'SOURCE_DATA_INCOMPLETE', 'TEMPORARILY_UNAVAILABLE'
    )),
    source_roles jsonb NOT NULL CHECK (jsonb_typeof(source_roles) = 'object'),
    updated_at timestamptz NOT NULL,
    CHECK (forecast_available = (availability_status = 'FORECAST_AVAILABLE'))
);

CREATE INDEX product_competitions_filters_idx
    ON football.product_competitions (continent, country, division, name);

CREATE TABLE football.product_teams (
    team_id uuid PRIMARY KEY REFERENCES football.teams (id),
    name text NOT NULL CHECK (name <> ''),
    country text,
    crest_url text,
    updated_at timestamptz NOT NULL
);

CREATE TABLE football.product_team_aliases (
    provider_code text NOT NULL CHECK (provider_code <> ''),
    provider_team_id text NOT NULL CHECK (provider_team_id <> ''),
    normalized_name text NOT NULL CHECK (normalized_name <> ''),
    country text,
    team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    PRIMARY KEY (provider_code, provider_team_id)
);

CREATE INDEX product_team_alias_name_idx
    ON football.product_team_aliases (normalized_name, country);

CREATE TABLE football.product_fixtures (
    fixture_id uuid PRIMARY KEY REFERENCES football.matches (id),
    competition_id uuid NOT NULL REFERENCES football.product_competitions (competition_id),
    home_team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    away_team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    kickoff_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN (
        'SCHEDULED', 'LIVE', 'FINISHED', 'POSTPONED', 'CANCELLED', 'ABANDONED'
    )),
    home_score smallint CHECK (home_score >= 0),
    away_score smallint CHECK (away_score >= 0),
    venue text,
    round_name text,
    forecast_availability text NOT NULL CHECK (forecast_availability IN (
        'FORECAST_AVAILABLE', 'NOT_ENOUGH_HISTORY', 'SOURCE_DATA_INCOMPLETE',
        'TEMPORARILY_UNAVAILABLE'
    )),
    updated_at timestamptz NOT NULL,
    CHECK (home_team_id <> away_team_id),
    CHECK ((status = 'FINISHED') = (home_score IS NOT NULL AND away_score IS NOT NULL))
);

CREATE INDEX product_fixtures_date_idx
    ON football.product_fixtures (kickoff_at, competition_id);

CREATE TABLE football.product_team_match_history (
    fixture_id uuid PRIMARY KEY REFERENCES football.matches (id),
    competition_id uuid NOT NULL REFERENCES football.product_competitions (competition_id),
    home_team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    away_team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    kickoff_at timestamptz NOT NULL,
    home_goals smallint NOT NULL CHECK (home_goals >= 0),
    away_goals smallint NOT NULL CHECK (away_goals >= 0),
    home_xg double precision CHECK (
        home_xg >= 0 AND home_xg < 'Infinity'::double precision
    ),
    away_xg double precision CHECK (
        away_xg >= 0 AND away_xg < 'Infinity'::double precision
    ),
    source_provider_code text NOT NULL CHECK (source_provider_code <> ''),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    CHECK (home_team_id <> away_team_id)
);

CREATE INDEX product_team_history_lookup_idx
    ON football.product_team_match_history (competition_id, kickoff_at DESC);
CREATE INDEX product_team_history_home_idx
    ON football.product_team_match_history (home_team_id, kickoff_at DESC);
CREATE INDEX product_team_history_away_idx
    ON football.product_team_match_history (away_team_id, kickoff_at DESC);

CREATE TABLE football.product_standings (
    competition_id uuid NOT NULL REFERENCES football.product_competitions (competition_id),
    team_id uuid NOT NULL REFERENCES football.product_teams (team_id),
    position smallint NOT NULL CHECK (position > 0),
    played smallint NOT NULL CHECK (played >= 0),
    won smallint NOT NULL CHECK (won >= 0),
    drawn smallint NOT NULL CHECK (drawn >= 0),
    lost smallint NOT NULL CHECK (lost >= 0),
    goals_for smallint NOT NULL CHECK (goals_for >= 0),
    goals_against smallint NOT NULL CHECK (goals_against >= 0),
    goal_difference smallint NOT NULL,
    points smallint NOT NULL CHECK (points >= 0),
    source_provider_code text NOT NULL CHECK (source_provider_code <> ''),
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (competition_id, team_id),
    UNIQUE (competition_id, position)
);

CREATE TABLE football.product_forecasts (
    forecast_id uuid PRIMARY KEY,
    semantic_sha256 football.sha256_hex NOT NULL UNIQUE,
    fixture_id uuid NOT NULL REFERENCES football.product_fixtures (fixture_id),
    model_label text NOT NULL CHECK (model_label = 'MVP_FORECAST'),
    model_algorithm_version text NOT NULL,
    model_artifact_sha256 football.sha256_hex NOT NULL,
    created_at timestamptz NOT NULL,
    football_cutoff timestamptz NOT NULL,
    knowledge_cutoff timestamptz NOT NULL,
    knowledge_mode text NOT NULL CHECK (knowledge_mode = 'bitemporal'),
    expected_home_goals double precision NOT NULL CHECK (
        expected_home_goals > 0 AND expected_home_goals < 'Infinity'::double precision
    ),
    expected_away_goals double precision NOT NULL CHECK (
        expected_away_goals > 0 AND expected_away_goals < 'Infinity'::double precision
    ),
    probabilities jsonb NOT NULL CHECK (jsonb_typeof(probabilities) = 'object'),
    score_matrix jsonb NOT NULL CHECK (jsonb_typeof(score_matrix) = 'array'),
    payload_sha256 football.sha256_hex NOT NULL,
    publication_mode text NOT NULL CHECK (publication_mode = 'MVP_OWNER_AUTHORIZED'),
    UNIQUE (fixture_id, model_artifact_sha256, knowledge_cutoff)
);

CREATE INDEX product_forecasts_fixture_idx
    ON football.product_forecasts (fixture_id, created_at DESC);

-- +goose StatementBegin
CREATE FUNCTION football.guard_product_forecast() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.created_at >= (
        SELECT kickoff_at FROM football.product_fixtures WHERE fixture_id = NEW.fixture_id
    ) THEN
        RAISE EXCEPTION 'MVP forecast must be stored before kickoff';
    END IF;
    IF TG_OP = 'INSERT' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'published MVP forecasts are immutable';
END;
$$;
-- +goose StatementEnd

CREATE TRIGGER product_forecasts_pre_kickoff
BEFORE INSERT ON football.product_forecasts
FOR EACH ROW EXECUTE FUNCTION football.guard_product_forecast();

CREATE TRIGGER product_forecasts_immutable
BEFORE UPDATE OR DELETE ON football.product_forecasts
FOR EACH ROW EXECUTE FUNCTION football.guard_product_forecast();

CREATE TABLE football.external_prediction_sources (
    source_code text PRIMARY KEY CHECK (source_code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL,
    base_url text NOT NULL,
    public_predictions boolean NOT NULL,
    prediction_date_available boolean NOT NULL,
    login_required boolean NOT NULL,
    paid_content boolean NOT NULL,
    automated_access_status text NOT NULL CHECK (automated_access_status IN (
        'ALLOWED', 'UNSUPPORTED_TERMS', 'UNSUPPORTED_ROBOTS',
        'UNSUPPORTED_ANTI_BOT', 'REVIEW_REQUIRED'
    )),
    adapter_status text NOT NULL CHECK (adapter_status IN ('ENABLED', 'DISABLED', 'NOT_IMPLEMENTED')),
    known_issues text NOT NULL DEFAULT '',
    checked_at timestamptz NOT NULL
);

CREATE TABLE football.external_predictions (
    prediction_id uuid PRIMARY KEY,
    revision_sha256 football.sha256_hex NOT NULL UNIQUE,
    source_code text NOT NULL REFERENCES football.external_prediction_sources (source_code),
    source_page text NOT NULL,
    prediction_date date NOT NULL,
    original_date_text text NOT NULL CHECK (original_date_text <> ''),
    collected_at timestamptz NOT NULL,
    fixture_id uuid REFERENCES football.product_fixtures (fixture_id),
    competition_text text NOT NULL,
    home_team_text text NOT NULL,
    away_team_text text NOT NULL,
    market text NOT NULL,
    selection text NOT NULL,
    match_status text NOT NULL CHECK (match_status IN ('MATCHED', 'UNMATCHED', 'AMBIGUOUS')),
    UNIQUE (source_code, source_page, collected_at, home_team_text, away_team_text, market)
);

CREATE INDEX external_predictions_date_idx
    ON football.external_predictions (prediction_date, source_code);

CREATE TABLE football.external_prediction_results (
    prediction_id uuid PRIMARY KEY REFERENCES football.external_predictions (prediction_id),
    correct boolean NOT NULL,
    settled_at timestamptz NOT NULL
);

INSERT INTO football.external_prediction_sources (
    source_code, name, base_url, public_predictions, prediction_date_available,
    login_required, paid_content, automated_access_status, adapter_status,
    known_issues, checked_at
) VALUES
    ('r2bet', 'R2Bet', 'https://r2bet.com', true, false, false, true,
        'REVIEW_REQUIRED', 'DISABLED', 'No clear collection/reuse permission found.',
        '2026-09-29T00:00:00Z'),
    ('tips1960', '1960Tips', 'https://www.1960tips.com', true, true, false, true,
        'REVIEW_REQUIRED', 'DISABLED', 'Public free tips exist; automated reuse permission is not explicit.',
        '2026-09-29T00:00:00Z'),
    ('slybet', 'SlyBet', 'https://slybet.net', true, false, false, false,
        'REVIEW_REQUIRED', 'DISABLED', 'Robots allows crawling; collection/reuse terms remain unverified.',
        '2026-09-29T00:00:00Z'),
    ('matchoutlook', 'MatchOutlook', 'https://www.matchoutlook.com', true, true, false, true,
        'UNSUPPORTED_TERMS', 'DISABLED', 'Terms prohibit reproduction or lifting predictions.',
        '2026-09-29T00:00:00Z'),
    ('forebet', 'Forebet', 'https://www.forebet.com', true, true, false, true,
        'UNSUPPORTED_ANTI_BOT', 'DISABLED', 'Managed anti-bot challenge; circumvention is prohibited.',
        '2026-09-29T00:00:00Z');
