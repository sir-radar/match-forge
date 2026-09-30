-- +goose Up

INSERT INTO football.external_prediction_sources (
    source_code, name, base_url, public_predictions, prediction_date_available,
    login_required, paid_content, automated_access_status, adapter_status,
    known_issues, checked_at
) VALUES (
    'manual_import', 'Owner-approved import', 'urn:matchforge:manual-import',
    false, true, false, false, 'ALLOWED', 'ENABLED',
    'Accepts only owner-supplied JSON records from sources the owner may lawfully use.',
    '2026-09-30T00:00:00Z'
) ON CONFLICT (source_code) DO NOTHING;

-- +goose Down

DELETE FROM football.external_prediction_sources WHERE source_code = 'manual_import';
