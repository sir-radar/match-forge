-- +goose Up

ALTER TABLE football.external_prediction_sources
    DROP CONSTRAINT external_prediction_sources_automated_access_status_check;

ALTER TABLE football.external_prediction_sources
    ADD CONSTRAINT external_prediction_sources_automated_access_status_check
    CHECK (automated_access_status IN (
        'ALLOWED', 'TECHNICALLY_AVAILABLE', 'TECHNICALLY_UNAVAILABLE',
        'AUTH_REQUIRED', 'PAID_ONLY', 'PARSER_BROKEN',
        'UNSUPPORTED_TERMS', 'UNSUPPORTED_ROBOTS', 'UNSUPPORTED_ANTI_BOT',
        'REVIEW_REQUIRED'
    ));

UPDATE football.external_prediction_sources
SET prediction_date_available = true,
    automated_access_status = 'TECHNICALLY_AVAILABLE',
    adapter_status = 'ENABLED',
    known_issues = 'TERMS_NOTE: NO_EXPLICIT_AUTOMATION_PERMISSION_FOUND; public free predictions retrieved normally.',
    checked_at = '2026-09-30T12:00:00Z'
WHERE source_code = 'r2bet';

UPDATE football.external_prediction_sources
SET automated_access_status = 'TECHNICALLY_AVAILABLE',
    adapter_status = 'ENABLED',
    known_issues = 'TERMS_NOTE: restrictive reuse terms recorded; private local structured-fact collection only.',
    checked_at = '2026-09-30T12:00:00Z'
WHERE source_code = 'tips1960';

UPDATE football.external_prediction_sources
SET prediction_date_available = true,
    automated_access_status = 'TECHNICALLY_AVAILABLE',
    adapter_status = 'ENABLED',
    known_issues = 'TERMS_NOTE: NO_EXPLICIT_AUTOMATION_PERMISSION_FOUND; public free predictions retrieved normally.',
    checked_at = '2026-09-30T12:00:00Z'
WHERE source_code = 'slybet';

UPDATE football.external_prediction_sources
SET automated_access_status = 'TECHNICALLY_AVAILABLE',
    adapter_status = 'ENABLED',
    known_issues = 'TERMS_NOTE: restrictive reuse terms recorded; private local structured-fact collection only; no redistribution.',
    checked_at = '2026-09-30T12:00:00Z'
WHERE source_code = 'matchoutlook';

UPDATE football.external_prediction_sources
SET automated_access_status = 'TECHNICALLY_UNAVAILABLE',
    adapter_status = 'DISABLED',
    known_issues = 'Managed anti-bot challenge returned HTTP 403 to an ordinary request; no circumvention attempted.',
    checked_at = '2026-09-30T12:00:00Z'
WHERE source_code = 'forebet';

-- +goose Down

UPDATE football.external_prediction_sources
SET prediction_date_available = false,
    automated_access_status = 'REVIEW_REQUIRED',
    adapter_status = 'DISABLED',
    known_issues = 'No clear collection/reuse permission found.',
    checked_at = '2026-09-29T00:00:00Z'
WHERE source_code = 'r2bet';

UPDATE football.external_prediction_sources
SET automated_access_status = 'UNSUPPORTED_TERMS',
    adapter_status = 'DISABLED',
    known_issues = 'April 2026 terms prohibit redistribution or republication without written permission.',
    checked_at = '2026-09-30T00:00:00Z'
WHERE source_code = 'tips1960';

UPDATE football.external_prediction_sources
SET prediction_date_available = false,
    automated_access_status = 'REVIEW_REQUIRED',
    adapter_status = 'DISABLED',
    known_issues = 'Robots allows crawling; collection/reuse terms remain unverified.',
    checked_at = '2026-09-29T00:00:00Z'
WHERE source_code = 'slybet';

UPDATE football.external_prediction_sources
SET automated_access_status = 'UNSUPPORTED_TERMS',
    adapter_status = 'DISABLED',
    known_issues = 'Terms prohibit reproduction or lifting predictions.',
    checked_at = '2026-09-29T00:00:00Z'
WHERE source_code = 'matchoutlook';

UPDATE football.external_prediction_sources
SET automated_access_status = 'UNSUPPORTED_ANTI_BOT',
    adapter_status = 'DISABLED',
    known_issues = 'Managed anti-bot challenge; circumvention is prohibited.',
    checked_at = '2026-09-29T00:00:00Z'
WHERE source_code = 'forebet';

ALTER TABLE football.external_prediction_sources
    DROP CONSTRAINT external_prediction_sources_automated_access_status_check;

ALTER TABLE football.external_prediction_sources
    ADD CONSTRAINT external_prediction_sources_automated_access_status_check
    CHECK (automated_access_status IN (
        'ALLOWED', 'UNSUPPORTED_TERMS', 'UNSUPPORTED_ROBOTS',
        'UNSUPPORTED_ANTI_BOT', 'REVIEW_REQUIRED'
    ));
