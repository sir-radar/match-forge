-- +goose Up

ALTER TABLE football.model_artifact_inputs
    ADD COLUMN knowledge_mode text NOT NULL DEFAULT 'bitemporal'
        CHECK (knowledge_mode ~ '^[a-z0-9][a-z0-9._-]*$');

ALTER TABLE football.model_artifact_inputs
    ALTER COLUMN knowledge_mode DROP DEFAULT;

ALTER TABLE football.baseline_forecasts
    ADD COLUMN knowledge_cutoff timestamptz,
    ADD COLUMN knowledge_mode text NOT NULL DEFAULT 'legacy-unspecified'
        CHECK (knowledge_mode ~ '^[a-z0-9][a-z0-9._-]*$'),
    ADD COLUMN quality_policy_sha256 football.sha256_hex NOT NULL
        DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
    ADD COLUMN forecast_context_sha256 football.sha256_hex NOT NULL
        DEFAULT '0000000000000000000000000000000000000000000000000000000000000000',
    ADD COLUMN probability_contract_version text NOT NULL DEFAULT 'legacy-unspecified'
        CHECK (probability_contract_version ~ '^[a-z0-9][a-z0-9._-]*$'),
    ADD COLUMN output_version text NOT NULL DEFAULT 'legacy-unspecified'
        CHECK (output_version ~ '^[a-z0-9][a-z0-9._-]*$');

UPDATE football.baseline_forecasts
SET knowledge_cutoff = prediction_cutoff
WHERE knowledge_cutoff IS NULL;

ALTER TABLE football.baseline_forecasts
    ALTER COLUMN knowledge_cutoff SET NOT NULL,
    ALTER COLUMN knowledge_mode DROP DEFAULT,
    ALTER COLUMN quality_policy_sha256 DROP DEFAULT,
    ALTER COLUMN forecast_context_sha256 DROP DEFAULT,
    ALTER COLUMN probability_contract_version DROP DEFAULT,
    ALTER COLUMN output_version DROP DEFAULT;
