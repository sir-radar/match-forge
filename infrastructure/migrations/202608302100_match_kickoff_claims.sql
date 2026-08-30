-- +goose Up

ALTER TABLE football.competition_observations
    ADD CONSTRAINT competition_observations_id_competition_unique
    UNIQUE (id, competition_id);

ALTER TABLE football.match_lifecycle_claims
    ADD CONSTRAINT match_lifecycle_claims_exact_observation_unique
    UNIQUE (id, match_id, match_observation_id);

CREATE TABLE football.match_kickoff_claims (
    id uuid PRIMARY KEY,
    match_id uuid NOT NULL,
    competition_id uuid NOT NULL,
    season_id uuid NOT NULL,
    claim_version text NOT NULL CHECK (claim_version <> ''),
    claim_sha256 football.sha256_hex NOT NULL UNIQUE,
    lifecycle_claim_id uuid NOT NULL,
    match_observation_id uuid NOT NULL,
    competition_observation_id uuid NOT NULL,
    local_match_date date NOT NULL,
    local_kickoff_time time NOT NULL,
    timezone_name text NOT NULL CHECK (timezone_name <> ''),
    tzdata_version text NOT NULL CHECK (tzdata_version <> ''),
    tzif_sha256 football.sha256_hex NOT NULL,
    kickoff_at timestamptz NOT NULL,
    known_from timestamptz NOT NULL,
    evidence jsonb NOT NULL CHECK (jsonb_typeof(evidence) = 'object'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (match_id, competition_id, season_id)
        REFERENCES football.matches (id, competition_id, season_id),
    FOREIGN KEY (lifecycle_claim_id, match_id, match_observation_id)
        REFERENCES football.match_lifecycle_claims (id, match_id, match_observation_id),
    FOREIGN KEY (competition_observation_id, competition_id)
        REFERENCES football.competition_observations (id, competition_id),
    UNIQUE (
        match_id, lifecycle_claim_id, claim_version, timezone_name, tzdata_version
    )
);

CREATE INDEX match_kickoff_claims_match_version_idx
    ON football.match_kickoff_claims (
        match_id, claim_version, timezone_name, tzdata_version, known_from DESC
    );
