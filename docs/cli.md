# Data pipeline CLI

## Commands

The `football` console script exposes the data pipeline and Sprint 2 gate:

```bash
football ingest competitions
football ingest season <id>
football ingest season <id> --competition-id <id>
football validate season <id>
football validate season <id> --competition-id <id>
football evaluate sprint2
```

Competition ingestion acquires the commit-pinned StatsBomb catalog and publishes canonical competitions and seasons. Season ingestion refreshes that catalog, resolves exactly one competition, acquires and ingests the season match list, acquires every match lineup and event resource, publishes one normalized event dataset, and validates it. An empty season succeeds without publishing or validating a dataset.

Use `--competition-id` when a provider season ID is ambiguous or when the pinned
`competitions.json` omits the requested competition-season pair even though its match list exists.
For example, the approved Sprint 2 corpus is:

```bash
football ingest season 27 --competition-id 2
```

The explicit pair selects `data/matches/2/27.json`. When that pair is absent from the catalog,
canonical ingestion derives the missing competition-season observation only from consistent
metadata in that preserved match-list resource and records the resource as lineage. It does not
modify provider bytes or infer a pair from the non-unique season ID alone.

Season validation resolves exactly one canonical StatsBomb competition-season pair and validates
its latest published normalized event dataset. Use `--competition-id` when the provider season ID
is ambiguous. `passed` and `warnings` return success. `quarantined` and `failed` remain registered
results but return nonzero exit codes.

Both ingestion commands publish immutable JSON and Markdown reports and print their paths. See [Ingestion reports](ingestion-reports.md).

`football evaluate sprint2` runs the pinned `Sprint2BaselineGatePolicyV1` workflow until the first
blocking stage. It starts with the approved StatsBomb EPL 2015/16 corpus
(`competition_id=2`, `season_id=27`), retains an immutable JSON and Markdown report, and returns
exit code `7` for `FAIL`. Missing corpus data produces `null` scope and metric fields; the command
never substitutes synthetic matches or zero-valued metrics. `make sprint2-evaluate` propagates this
as a failed Make target. Later modelling phases remain blocked.

## Configuration

Use environment variables for routine execution:

```bash
export FOOTBALL_DATABASE_URL='postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable'
export FOOTBALL_DATA_ROOT='.local/football-data'
export FOOTBALL_STATSBOMB_GIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_QUALITY_POLICY='schemas/quality/statsbomb-quality-policy-v1.json'
export FOOTBALL_SPRINT2_REPORT_ROOT='.local/reports/sprint2'
```

`FOOTBALL_STATSBOMB_GIT_SHA` is required only for ingestion. Other defaults target the repository's local Compose database, `.local/football-data`, `.local/reports/sprint2`, and checked-in quality policy. Equivalent global options are `--database-url`, `--data-root`, `--report-root`, `--source-git-sha`, and `--quality-policy`; place them before the command.

The CLI assumes production migrations are current. It never migrates PostgreSQL automatically.

## Exit codes

```text
0  ingestion completed with no quarantine/failure, or validation passed/has warnings
2  invalid configuration, unknown/ambiguous season, or missing dataset
3  provider fetch or immutable source-integrity failure
4  database, canonical ingestion, publication, or validation execution failure
5  ingestion or validation completed with quarantined status
6  ingestion or validation completed with failed status
7  Sprint 2 evaluation completed with FAIL status; retained reports contain blockers
```
