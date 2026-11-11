set default_transaction_read_only = on;
\echo == total
select count(*), pg_size_pretty(sum(pg_database_size(datname))), sum(pg_database_size(datname)) from pg_database;
\echo == db created (PG_VERSION mtime) | size | conns
select d.oid, d.datname, (pg_stat_file(format('base/%s/PG_VERSION', d.oid))).modification::timestamp(0), pg_database_size(d.datname),
  (select count(*) from pg_stat_activity a where a.datid=d.oid)
from pg_database d order by 3;
\echo == stats
select datname, xact_commit, tup_inserted, tup_updated, tup_deleted, stats_reset::timestamp(0), temp_files, pg_size_pretty(temp_bytes)
from pg_stat_database where datname is not null order by tup_inserted desc limit 20;
\echo == settings
select name, setting, unit from pg_settings where name in ('max_wal_size','min_wal_size','wal_level','archive_mode','autovacuum','wal_keep_size','shared_buffers','data_checksums','default_toast_compression','wal_compression','log_destination','logging_collector','temp_file_limit');
\echo == slots / prepared
select count(*) from pg_replication_slots;
select count(*) from pg_prepared_xacts;
\echo == activity
select datname, usename, application_name, state, backend_start::timestamp(0), left(query,70) from pg_stat_activity where datname is not null order by backend_start;
\echo == wal
select count(*), pg_size_pretty(sum(size)) from pg_ls_waldir();
