-- +goose Up

ALTER TABLE football.product_fixtures
    ADD COLUMN result_score_basis text NOT NULL DEFAULT 'UNKNOWN' CHECK (
        result_score_basis IN (
            'REGULATION_90', 'EXTRA_TIME', 'PENALTY_SHOOTOUT', 'UNKNOWN'
        )
    );

ALTER TABLE football.external_prediction_result_revisions
    DROP CONSTRAINT external_prediction_result_revisions_score_basis_check;

ALTER TABLE football.external_prediction_result_revisions
    ADD CONSTRAINT external_prediction_result_revisions_score_basis_check CHECK (
        score_basis IN (
            'REGULATION_90', 'EXTRA_TIME', 'PENALTY_SHOOTOUT', 'UNKNOWN', 'NOT_SETTLED'
        )
    );

-- +goose Down

ALTER TABLE football.external_prediction_result_revisions
    DROP CONSTRAINT external_prediction_result_revisions_score_basis_check;

ALTER TABLE football.external_prediction_result_revisions
    ADD CONSTRAINT external_prediction_result_revisions_score_basis_check CHECK (
        score_basis IN ('REGULATION_90', 'NOT_SETTLED')
    );

ALTER TABLE football.product_fixtures DROP COLUMN result_score_basis;
