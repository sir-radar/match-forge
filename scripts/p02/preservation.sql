-- P02 rollout preservation hashes. Read-only.
-- Usage: psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -v run_start="'<ISO timestamp>'" -f scripts/p02/preservation.sql
-- Capture before step 2 and again after every later step; each row must be unchanged.
-- Rows registered at or after run_start are new append-only records and are excluded.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT 'forecasts' AS name, count(*) AS rows,
       md5(string_agg(forecast_id::text || payload_sha256, ',' ORDER BY forecast_id)) AS md5
FROM football.product_forecasts WHERE created_at < :run_start::timestamptz
UNION ALL
SELECT 'model_forecasts', count(*), md5(string_agg(t::text, ',' ORDER BY t::text))
FROM football.product_model_forecasts t
UNION ALL
SELECT 'forecast_artifacts', count(*), md5(string_agg(t::text, ',' ORDER BY t::text))
FROM football.forecast_artifacts t WHERE created_at < :run_start::timestamptz
UNION ALL
SELECT 'read_reports', count(*), md5(string_agg(input_sha256 || record_sha256, ',' ORDER BY input_sha256))
FROM football.product_read_reports WHERE registered_at < :run_start::timestamptz
UNION ALL
SELECT 'history_decisions', count(*), md5(string_agg(t::text, ',' ORDER BY decision_id))
FROM football.product_match_history_decisions t WHERE decided_at < :run_start::timestamptz
UNION ALL
SELECT 'source_snapshots', count(*),
       md5(string_agg(id::text || manifest_sha256 || status, ',' ORDER BY id))
FROM football.source_snapshots WHERE created_at < :run_start::timestamptz
UNION ALL
-- History-qualification collisions are stamped with their source time, so the
-- replay adds rows dated before run_start. Inserts use ON CONFLICT DO NOTHING
-- and never touch existing rows; compare the other stages only.
SELECT 'identity_conflicts_other_stages', count(*),
       md5(string_agg(conflict_sha256, ',' ORDER BY conflict_sha256))
FROM football.fixture_identity_ingestion_conflicts
WHERE created_at < :run_start::timestamptz
  AND incoming_facts->>'stage' IS DISTINCT FROM 'HISTORY_QUALIFICATION'
ORDER BY 1;
COMMIT;
