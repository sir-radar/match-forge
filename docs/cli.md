# Data pipeline CLI

## Commands

The `football` console script exposes the Sprint 1 production services:

```bash
football ingest competitions
football ingest season <id>
football validate season <id>
```

Competition ingestion acquires the commit-pinned StatsBomb catalog and publishes canonical competitions and seasons. Season ingestion refreshes that catalog, resolves exactly one competition, acquires and ingests the season match list, acquires every match lineup and event resource, then publishes one normalized event dataset. An empty season succeeds without publishing a dataset.

Season validation resolves exactly one canonical StatsBomb season and validates its latest published normalized event dataset. `passed` and `warnings` return success. `quarantined` and `failed` remain registered results but return nonzero exit codes.

## Configuration

Use environment variables for routine execution:

```bash
export FOOTBALL_DATABASE_URL='postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable'
export FOOTBALL_DATA_ROOT='.local/football-data'
export FOOTBALL_STATSBOMB_GIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_QUALITY_POLICY='schemas/quality/statsbomb-quality-policy-v1.json'
```

`FOOTBALL_STATSBOMB_GIT_SHA` is required only for ingestion. The other defaults target the repository's local Compose database, `.local/football-data`, and checked-in quality policy. Equivalent global options are `--database-url`, `--data-root`, `--source-git-sha`, and `--quality-policy`; place them before `ingest` or `validate`.

The CLI assumes production migrations are current. It never migrates PostgreSQL automatically.

## Exit codes

```text
0  ingestion completed, or validation passed/has warnings
2  invalid configuration, unknown/ambiguous season, or missing dataset
3  provider fetch or immutable source-integrity failure
4  database, canonical ingestion, publication, or validation execution failure
5  validation completed with quarantined status
6  validation completed with failed status
```

Task 14 will replace the basic one-line summaries with durable JSON and human-readable ingestion reports.
