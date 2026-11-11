set default_transaction_read_only = on;
set statement_timeout = '180s';
\echo == product_competitions value sizes
select pg_size_pretty(sum(pg_column_size(source_roles))::bigint), max(pg_column_size(source_roles)), max(octet_length(source_roles::text)) from football.product_competitions;
\echo == toast chunks actually visible
select count(*), count(distinct chunk_id), pg_size_pretty(sum(octet_length(chunk_data))::bigint) from pg_toast.pg_toast_866743;
\echo == same table in today's restored rehearsal copy is measured separately
\echo == growth: rows per day
select 'source_snapshots', date_trunc('week', created_at)::date, count(*) from football.source_snapshots group by 2 order by 2;
select 'resource_observations', date_trunc('week', created_at)::date, count(*) from football.product_provider_resource_observations group by 2 order by 2;
select 'read_reports', date_trunc('week', created_at)::date, count(*) from football.product_read_reports group by 2 order by 2;
select 'mapping_decisions', min(created_at)::date, max(created_at)::date, count(*) from football.product_provider_mapping_decisions;
\echo == source registry dedupe
select count(*), count(distinct content_sha256), pg_size_pretty(sum(byte_size)::bigint) from football.source_resources;
