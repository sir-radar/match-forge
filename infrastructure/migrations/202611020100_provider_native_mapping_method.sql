-- +goose Up

-- A provider-native link to a database-generated surrogate is not a
-- reproducible provider-origin UUID. Existing rows and decisions stay intact.
ALTER TABLE football.competition_provider_mappings
    DROP CONSTRAINT competition_provider_mappings_mapping_method_check,
    ADD CONSTRAINT competition_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

ALTER TABLE football.season_provider_mappings
    DROP CONSTRAINT season_provider_mappings_mapping_method_check,
    ADD CONSTRAINT season_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

ALTER TABLE football.team_provider_mappings
    DROP CONSTRAINT team_provider_mappings_mapping_method_check,
    ADD CONSTRAINT team_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

ALTER TABLE football.player_provider_mappings
    DROP CONSTRAINT player_provider_mappings_mapping_method_check,
    ADD CONSTRAINT player_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

ALTER TABLE football.match_provider_mappings
    DROP CONSTRAINT match_provider_mappings_mapping_method_check,
    ADD CONSTRAINT match_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

ALTER TABLE football.provider_mapping_history
    DROP CONSTRAINT provider_mapping_history_mapping_method_check,
    ADD CONSTRAINT provider_mapping_history_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual', 'provider_native'));

-- +goose Down

-- Refuse downgrade while native mappings exist; never relabel historical rows.
ALTER TABLE football.provider_mapping_history
    DROP CONSTRAINT provider_mapping_history_mapping_method_check,
    ADD CONSTRAINT provider_mapping_history_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));

ALTER TABLE football.match_provider_mappings
    DROP CONSTRAINT match_provider_mappings_mapping_method_check,
    ADD CONSTRAINT match_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));

ALTER TABLE football.player_provider_mappings
    DROP CONSTRAINT player_provider_mappings_mapping_method_check,
    ADD CONSTRAINT player_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));

ALTER TABLE football.team_provider_mappings
    DROP CONSTRAINT team_provider_mappings_mapping_method_check,
    ADD CONSTRAINT team_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));

ALTER TABLE football.season_provider_mappings
    DROP CONSTRAINT season_provider_mappings_mapping_method_check,
    ADD CONSTRAINT season_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));

ALTER TABLE football.competition_provider_mappings
    DROP CONSTRAINT competition_provider_mappings_mapping_method_check,
    ADD CONSTRAINT competition_provider_mappings_mapping_method_check CHECK (mapping_method IN (
        'explicit_crosswalk', 'deterministic', 'probabilistic', 'manual'));
