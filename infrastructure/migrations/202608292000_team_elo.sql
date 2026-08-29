-- +goose Up

CREATE TABLE football.elo_model_versions (
    model_version text PRIMARY KEY CHECK (model_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    config_sha256 football.sha256_hex NOT NULL,
    config jsonb NOT NULL CHECK (jsonb_typeof(config) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE football.matches
    ADD CONSTRAINT matches_id_competition_unique UNIQUE (id, competition_id);

CREATE TABLE football.team_elo_history (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    model_version text NOT NULL REFERENCES football.elo_model_versions (model_version),
    team_id uuid NOT NULL REFERENCES football.teams (id),
    opponent_team_id uuid NOT NULL REFERENCES football.teams (id),
    match_id uuid NOT NULL REFERENCES football.matches (id),
    competition_id uuid NOT NULL REFERENCES football.competitions (id),
    rating_timestamp timestamptz NOT NULL,
    is_home boolean NOT NULL,
    pre_match_rating double precision NOT NULL CHECK (
        pre_match_rating > '-Infinity'::double precision
        AND pre_match_rating < 'Infinity'::double precision
    ),
    rating double precision NOT NULL CHECK (
        rating > '-Infinity'::double precision
        AND rating < 'Infinity'::double precision
    ),
    expected_score double precision NOT NULL CHECK (
        expected_score >= 0 AND expected_score <= 1
    ),
    actual_score double precision NOT NULL CHECK (actual_score IN (0, 0.5, 1)),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (team_id <> opponent_team_id),
    FOREIGN KEY (match_id, competition_id)
        REFERENCES football.matches (id, competition_id),
    FOREIGN KEY (match_id, team_id)
        REFERENCES football.match_team_participations (match_id, team_id),
    FOREIGN KEY (match_id, opponent_team_id)
        REFERENCES football.match_team_participations (match_id, team_id),
    UNIQUE (model_version, team_id, rating_timestamp),
    UNIQUE (model_version, team_id, match_id)
);

CREATE INDEX team_elo_history_as_of_idx
    ON football.team_elo_history (model_version, team_id, rating_timestamp DESC);
