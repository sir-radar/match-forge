-- +goose Up

ALTER TABLE football.forecast_artifacts
    DROP CONSTRAINT forecast_artifacts_forecast_id_artifact_role_key;

CREATE UNIQUE INDEX forecast_artifacts_one_calibrator_idx
    ON football.forecast_artifacts (forecast_id)
    WHERE artifact_role = 'CALIBRATOR';
