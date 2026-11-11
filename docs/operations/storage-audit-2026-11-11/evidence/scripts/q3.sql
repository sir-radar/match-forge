set default_transaction_read_only = on;
set statement_timeout = '120s';
\echo == product_competitions columns
select attname, format_type(atttypid, atttypmod), attstorage from pg_attribute where attrelid='football.product_competitions'::regclass and attnum>0 and not attisdropped;
\echo == product_competitions live bytes (sum pg_column_size of row) vs relation
select count(*), pg_size_pretty(sum(pg_column_size(t.*))::bigint) live_row_bytes, pg_size_pretty(pg_total_relation_size('football.product_competitions')) total from football.product_competitions t;
\echo == product_competitions toast stats
select s.relname, s.n_live_tup, s.n_dead_tup, s.n_tup_ins, s.n_tup_upd, s.n_tup_del, s.last_autovacuum::timestamp(0), s.autovacuum_count, pg_size_pretty(pg_relation_size(s.relid))
from pg_stat_all_tables s where s.relid = (select reltoastrelid from pg_class where oid='football.product_competitions'::regclass) or s.relid='football.product_competitions'::regclass;
\echo == tables with JSON/bytea heavy toast: live toast estimate vs physical for top toast tables
select c.relname, pg_size_pretty(pg_total_relation_size(c.reltoastrelid)) toast_physical,
  ts.n_live_tup toast_live_chunks, ts.n_dead_tup toast_dead_chunks, ts.n_tup_ins, ts.n_tup_del, ts.last_autovacuum::timestamp(0)
from pg_class c join pg_stat_all_tables ts on ts.relid=c.reltoastrelid
where c.relnamespace='football'::regnamespace and c.reltoastrelid<>0 order by pg_total_relation_size(c.reltoastrelid) desc limit 8;
\echo == per-table insert/update/delete churn top
select relname, n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd, n_live_tup, autovacuum_count from pg_stat_user_tables order by n_tup_upd+n_tup_del desc limit 15;
\echo == stats_reset / oldest xact
select stats_reset from pg_stat_database where datname='football';
select max(age(backend_xmin)) from pg_stat_activity;
\echo == row counts by created day for growth tables (source_snapshots)
select column_name from information_schema.columns where table_schema='football' and table_name in ('source_snapshots','source_resources','product_read_reports','product_provider_resource_observations','product_provider_mapping_decisions','fixture_identity_resolutions') and data_type like 'timestamp%' order by table_name, ordinal_position;
