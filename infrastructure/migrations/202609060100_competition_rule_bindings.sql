-- +goose Up

ALTER TABLE football.baseline_forecasts
    ADD COLUMN competition_rules_id text,
    ADD COLUMN competition_rules_sha256 football.sha256_hex,
    ADD COLUMN outcome_scope text;

ALTER TABLE football.baseline_forecasts
    ADD CONSTRAINT baseline_forecasts_competition_rules_required CHECK (
        competition_rules_id IS NOT NULL
        AND competition_rules_id <> ''
        AND competition_rules_sha256 IS NOT NULL
        AND outcome_scope IN ('REGULATION_TIME', 'INCLUDING_EXTRA_TIME', 'INCLUDING_SHOOTOUT')
    ) NOT VALID;

ALTER TABLE football.sprint2_evaluation_runs
    ADD COLUMN competition_rules_id text,
    ADD COLUMN competition_rules_sha256 football.sha256_hex,
    ADD COLUMN outcome_scope text;

ALTER TABLE football.sprint2_evaluation_runs
    ADD CONSTRAINT sprint2_evaluation_runs_competition_rules_required CHECK (
        competition_rules_id IS NOT NULL
        AND competition_rules_id <> ''
        AND competition_rules_sha256 IS NOT NULL
        AND outcome_scope IN ('REGULATION_TIME', 'INCLUDING_EXTRA_TIME', 'INCLUDING_SHOOTOUT')
    ) NOT VALID;
