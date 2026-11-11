set default_transaction_read_only = on;
\echo == schemas
select n.nspname, count(*), pg_size_pretty(sum(pg_total_relation_size(c.oid))) from pg_class c join pg_namespace n on n.oid=c.relnamespace
where c.relkind in ('r','m','p') group by 1 order by sum(pg_total_relation_size(c.oid)) desc limit 15;
\echo == top relations: schema.table | total | heap | toast | indexes | est rows | dead | last_autovacuum
select n.nspname||'.'||c.relname, pg_total_relation_size(c.oid) tot,
  pg_relation_size(c.oid) heap,
  coalesce(pg_total_relation_size(nullif(c.reltoastrelid,0)),0) toast,
  pg_indexes_size(c.oid) idx,
  c.reltuples::bigint, s.n_dead_tup, s.n_live_tup, s.last_autovacuum::timestamp(0)
from pg_class c join pg_namespace n on n.oid=c.relnamespace
left join pg_stat_all_tables s on s.relid=c.oid
where c.relkind in ('r','m') and n.nspname not in ('pg_catalog','information_schema')
order by tot desc limit 40;
\echo == totals heap/toast/index
select pg_size_pretty(sum(pg_relation_size(c.oid))) heap,
  pg_size_pretty(sum(coalesce(pg_total_relation_size(nullif(c.reltoastrelid,0)),0))) toast,
  pg_size_pretty(sum(pg_indexes_size(c.oid))) idx, count(*)
from pg_class c join pg_namespace n on n.oid=c.relnamespace
where c.relkind in ('r','m') and n.nspname not in ('pg_catalog','information_schema');
\echo == unused indexes (idx_scan=0) top
select schemaname||'.'||indexrelname, pg_relation_size(indexrelid), idx_scan from pg_stat_user_indexes where idx_scan=0 order by 2 desc limit 15;
\echo == dead tuple ratio top
select schemaname||'.'||relname, n_live_tup, n_dead_tup, pg_total_relation_size(relid) from pg_stat_user_tables where n_dead_tup > 10000 order by n_dead_tup desc limit 15;
