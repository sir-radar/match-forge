-- +goose Up

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SCHEMA IF NOT EXISTS football;

CREATE DOMAIN football.sha256_hex AS text
    CHECK (VALUE ~ '^[0-9a-f]{64}$');

-- +goose StatementBegin
CREATE FUNCTION football.known_at(
    known_from timestamptz,
    known_to timestamptz,
    knowledge_cutoff timestamptz
) RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT known_from <= knowledge_cutoff
       AND (known_to IS NULL OR known_to > knowledge_cutoff)
$$;
-- +goose StatementEnd

CREATE TABLE football.providers (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    code text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name text NOT NULL CHECK (name <> ''),
    source_type text NOT NULL CHECK (source_type IN (
        'git_repository', 'http_api', 'file_download', 'manual'
    )),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE football.source_snapshots (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    source_identity text NOT NULL CHECK (source_identity <> ''),
    source_revision text NOT NULL CHECK (source_revision <> ''),
    repository text,
    git_sha text CHECK (
        git_sha IS NULL OR git_sha ~ '^([0-9a-f]{40}|[0-9a-f]{64})$'
    ),
    source_commit_at timestamptz,
    acquired_at timestamptz NOT NULL,
    manifest_path text NOT NULL CHECK (
        manifest_path <> ''
        AND manifest_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    manifest_sha256 football.sha256_hex NOT NULL,
    status text NOT NULL CHECK (status IN (
        'discovered', 'acquiring', 'acquired', 'validated', 'quarantined', 'superseded'
    )),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (provider_id, source_identity, source_revision),
    UNIQUE (id, provider_id)
);

CREATE INDEX source_snapshots_provider_acquired_idx
    ON football.source_snapshots (provider_id, acquired_at DESC);

CREATE TABLE football.source_resources (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    source_snapshot_id uuid NOT NULL REFERENCES football.source_snapshots (id),
    provider_path text NOT NULL CHECK (
        provider_path <> ''
        AND provider_path !~ '(^/|(^|/)\.\.(/|$))'
    ),
    sha256 football.sha256_hex NOT NULL,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL CHECK (media_type <> ''),
    parse_status text NOT NULL CHECK (parse_status IN (
        'pending', 'parsed', 'failed', 'not_applicable'
    )),
    validation_status text NOT NULL CHECK (validation_status IN (
        'pending', 'valid', 'warnings', 'quarantined', 'failed'
    )),
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (source_snapshot_id, provider_path),
    UNIQUE (id, source_snapshot_id)
);

CREATE TABLE football.competitions (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE football.seasons (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    competition_id uuid NOT NULL REFERENCES football.competitions (id),
    start_date date,
    end_date date,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date),
    UNIQUE (id, competition_id)
);

CREATE TABLE football.teams (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    entity_kind text NOT NULL DEFAULT 'unknown' CHECK (entity_kind IN (
        'club', 'national_team', 'representative_team', 'unknown'
    )),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE football.players (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    date_of_birth date,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE football.matches (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    competition_id uuid NOT NULL REFERENCES football.competitions (id),
    season_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (season_id, competition_id)
        REFERENCES football.seasons (id, competition_id),
    UNIQUE (id, competition_id, season_id)
);

CREATE TABLE football.competition_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    competition_id uuid NOT NULL REFERENCES football.competitions (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'
    )),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1
    ),
    source_snapshot_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    EXCLUDE USING gist (
        provider_id WITH =,
        provider_competition_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    )
);

CREATE TABLE football.season_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    season_id uuid NOT NULL REFERENCES football.seasons (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    provider_season_id text NOT NULL CHECK (provider_season_id <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'
    )),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1
    ),
    source_snapshot_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    EXCLUDE USING gist (
        provider_id WITH =,
        provider_competition_id WITH =,
        provider_season_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    )
);

CREATE TABLE football.team_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    team_id uuid NOT NULL REFERENCES football.teams (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_team_id text NOT NULL CHECK (provider_team_id <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'
    )),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1
    ),
    source_snapshot_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    EXCLUDE USING gist (
        provider_id WITH =,
        provider_team_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    )
);

CREATE TABLE football.player_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    player_id uuid NOT NULL REFERENCES football.players (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_player_id text NOT NULL CHECK (provider_player_id <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'
    )),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1
    ),
    source_snapshot_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    EXCLUDE USING gist (
        provider_id WITH =,
        provider_player_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    )
);

CREATE TABLE football.match_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_id uuid NOT NULL REFERENCES football.matches (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    mapping_method text NOT NULL CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'
    )),
    mapping_confidence double precision NOT NULL CHECK (
        mapping_confidence >= 0 AND mapping_confidence <= 1
    ),
    source_snapshot_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    EXCLUDE USING gist (
        provider_id WITH =,
        provider_match_id WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    )
);

CREATE TABLE football.competition_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    competition_id uuid NOT NULL REFERENCES football.competitions (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    name text NOT NULL CHECK (name <> ''),
    country_name text,
    gender text,
    is_youth boolean,
    is_international boolean,
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    provider_available_at timestamptz,
    provider_updated_at timestamptz,
    provider_available_at_raw text,
    provider_updated_at_raw text,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_competition_id),
    EXCLUDE USING gist (
        competition_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX competition_observations_as_of_idx
    ON football.competition_observations (competition_id, known_from DESC);

CREATE TABLE football.season_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    season_id uuid NOT NULL REFERENCES football.seasons (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_competition_id text NOT NULL CHECK (provider_competition_id <> ''),
    provider_season_id text NOT NULL CHECK (provider_season_id <> ''),
    name text NOT NULL CHECK (name <> ''),
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    provider_available_at timestamptz,
    provider_updated_at timestamptz,
    provider_available_at_raw text,
    provider_updated_at_raw text,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_competition_id, provider_season_id),
    EXCLUDE USING gist (
        season_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX season_observations_as_of_idx
    ON football.season_observations (season_id, known_from DESC);

CREATE TABLE football.team_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    team_id uuid NOT NULL REFERENCES football.teams (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_team_id text NOT NULL CHECK (provider_team_id <> ''),
    name text NOT NULL CHECK (name <> ''),
    gender text,
    country_provider_id text,
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    provider_available_at timestamptz,
    provider_updated_at timestamptz,
    provider_available_at_raw text,
    provider_updated_at_raw text,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_team_id),
    EXCLUDE USING gist (
        team_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX team_observations_as_of_idx
    ON football.team_observations (team_id, known_from DESC);

CREATE TABLE football.player_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    player_id uuid NOT NULL REFERENCES football.players (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_player_id text NOT NULL CHECK (provider_player_id <> ''),
    full_name text NOT NULL CHECK (full_name <> ''),
    nickname text,
    country_provider_id text,
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    provider_available_at timestamptz,
    provider_updated_at timestamptz,
    provider_available_at_raw text,
    provider_updated_at_raw text,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_player_id),
    EXCLUDE USING gist (
        player_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX player_observations_as_of_idx
    ON football.player_observations (player_id, known_from DESC);

CREATE TABLE football.match_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_id uuid NOT NULL REFERENCES football.matches (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    match_date date,
    kick_off_local time,
    kickoff_timezone text,
    kickoff_at timestamptz,
    home_team_id uuid REFERENCES football.teams (id),
    away_team_id uuid REFERENCES football.teams (id),
    home_score smallint CHECK (home_score >= 0),
    away_score smallint CHECK (away_score >= 0),
    lifecycle text NOT NULL DEFAULT 'unknown' CHECK (lifecycle IN (
        'scheduled', 'in_progress', 'completed', 'abandoned', 'postponed', 'cancelled', 'unknown'
    )),
    stage text,
    match_week integer CHECK (match_week > 0),
    provider_status text,
    provider_360_status text,
    data_version text,
    shot_fidelity_version text,
    xy_fidelity_version text,
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    provider_available_at timestamptz,
    provider_updated_at timestamptz,
    provider_available_at_raw text,
    provider_updated_at_raw text,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (home_team_id IS NULL OR away_team_id IS NULL OR home_team_id <> away_team_id),
    CHECK ((home_score IS NULL) = (away_score IS NULL)),
    CHECK (kickoff_at IS NULL OR kickoff_timezone IS NOT NULL),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_match_id),
    EXCLUDE USING gist (
        match_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX match_observations_as_of_idx
    ON football.match_observations (match_id, known_from DESC);

CREATE TABLE football.match_team_participations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_id uuid NOT NULL REFERENCES football.matches (id),
    team_id uuid NOT NULL REFERENCES football.teams (id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (match_id, team_id),
    UNIQUE (id, match_id)
);

CREATE TABLE football.match_team_participation_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_team_participation_id uuid NOT NULL,
    match_id uuid NOT NULL,
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    side text NOT NULL CHECK (side IN ('home', 'away')),
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (match_team_participation_id, match_id)
        REFERENCES football.match_team_participations (id, match_id),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, match_team_participation_id),
    EXCLUDE USING gist (
        match_team_participation_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    ),
    EXCLUDE USING gist (
        match_id WITH =,
        provider_id WITH =,
        side WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE TABLE football.match_player_participations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_team_participation_id uuid NOT NULL
        REFERENCES football.match_team_participations (id),
    player_id uuid NOT NULL REFERENCES football.players (id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (match_team_participation_id, player_id)
);

CREATE TABLE football.match_player_participation_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_player_participation_id uuid NOT NULL
        REFERENCES football.match_player_participations (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    jersey_number smallint CHECK (jersey_number > 0),
    was_in_lineup boolean NOT NULL,
    was_starter boolean NOT NULL,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (NOT was_starter OR was_in_lineup),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, match_player_participation_id),
    EXCLUDE USING gist (
        match_player_participation_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE TABLE football.player_position_stints (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_player_observation_id uuid NOT NULL
        REFERENCES football.match_player_participation_observations (id) ON DELETE RESTRICT,
    provider_position_id text,
    position_name text NOT NULL CHECK (position_name <> ''),
    period_from smallint NOT NULL CHECK (period_from > 0),
    clock_from interval NOT NULL CHECK (clock_from >= interval '0 seconds'),
    period_to smallint CHECK (period_to > 0),
    clock_to interval CHECK (clock_to >= interval '0 seconds'),
    start_reason text,
    end_reason text,
    sequence integer NOT NULL CHECK (sequence > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((period_to IS NULL) = (clock_to IS NULL)),
    CHECK (
        period_to IS NULL
        OR period_to > period_from
        OR (period_to = period_from AND clock_to > clock_from)
    ),
    UNIQUE (match_player_observation_id, sequence)
);

CREATE TABLE football.player_cards (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_player_observation_id uuid NOT NULL
        REFERENCES football.match_player_participation_observations (id) ON DELETE RESTRICT,
    provider_card_id text,
    card_type text NOT NULL CHECK (card_type <> ''),
    period smallint CHECK (period > 0),
    event_clock interval CHECK (event_clock >= interval '0 seconds'),
    reason text,
    sequence integer NOT NULL CHECK (sequence > 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (match_player_observation_id, sequence)
);

CREATE TABLE football.event_catalog (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    match_id uuid NOT NULL REFERENCES football.matches (id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (id, match_id)
);

CREATE TABLE football.event_provider_mappings (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_id uuid NOT NULL REFERENCES football.event_catalog (id),
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    provider_event_id text NOT NULL CHECK (provider_event_id <> ''),
    source_snapshot_id uuid NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (last_seen_at >= first_seen_at),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    UNIQUE (provider_id, provider_event_id)
);

CREATE TABLE football.event_observations (
    id uuid PRIMARY KEY DEFAULT uuidv7(),
    event_id uuid NOT NULL,
    match_id uuid NOT NULL,
    provider_id uuid NOT NULL REFERENCES football.providers (id),
    provider_match_id text NOT NULL CHECK (provider_match_id <> ''),
    provider_event_id text NOT NULL CHECK (provider_event_id <> ''),
    event_index integer NOT NULL CHECK (event_index > 0),
    provider_event_type text NOT NULL CHECK (provider_event_type <> ''),
    period smallint NOT NULL CHECK (period > 0),
    event_clock interval NOT NULL CHECK (event_clock >= interval '0 seconds'),
    team_id uuid REFERENCES football.teams (id),
    player_id uuid REFERENCES football.players (id),
    possession_team_id uuid REFERENCES football.teams (id),
    valid_from timestamptz,
    valid_to timestamptz,
    known_from timestamptz NOT NULL,
    known_to timestamptz,
    source_snapshot_id uuid NOT NULL,
    source_resource_id uuid NOT NULL,
    acquired_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from),
    CHECK (known_to IS NULL OR known_to > known_from),
    CHECK (known_from >= acquired_at),
    FOREIGN KEY (event_id, match_id)
        REFERENCES football.event_catalog (id, match_id),
    FOREIGN KEY (source_snapshot_id, provider_id)
        REFERENCES football.source_snapshots (id, provider_id),
    FOREIGN KEY (source_resource_id, source_snapshot_id)
        REFERENCES football.source_resources (id, source_snapshot_id),
    UNIQUE (source_snapshot_id, provider_event_id),
    UNIQUE (source_snapshot_id, provider_match_id, event_index),
    EXCLUDE USING gist (
        event_id WITH =,
        provider_id WITH =,
        tstzrange(known_from, known_to, '[)') WITH &&
    )
);

CREATE INDEX event_observations_match_order_idx
    ON football.event_observations (match_id, event_index);

CREATE VIEW football.current_competition_observations AS
SELECT * FROM football.competition_observations WHERE known_to IS NULL;

CREATE VIEW football.current_season_observations AS
SELECT * FROM football.season_observations WHERE known_to IS NULL;

CREATE VIEW football.current_team_observations AS
SELECT * FROM football.team_observations WHERE known_to IS NULL;

CREATE VIEW football.current_player_observations AS
SELECT * FROM football.player_observations WHERE known_to IS NULL;

CREATE VIEW football.current_match_observations AS
SELECT * FROM football.match_observations WHERE known_to IS NULL;
