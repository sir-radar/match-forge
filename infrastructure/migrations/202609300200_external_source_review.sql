-- +goose Up

UPDATE football.external_prediction_sources
SET automated_access_status = 'UNSUPPORTED_TERMS',
    known_issues = 'April 2026 terms prohibit redistribution or republication without written permission.',
    checked_at = '2026-09-30T00:00:00Z'
WHERE source_code = 'tips1960';

-- +goose Down

UPDATE football.external_prediction_sources
SET automated_access_status = 'REVIEW_REQUIRED',
    known_issues = 'Public free tips exist; automated reuse permission is not explicit.',
    checked_at = '2026-09-29T00:00:00Z'
WHERE source_code = 'tips1960';
