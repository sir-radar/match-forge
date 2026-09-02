# Data pipeline CLI

## Commands

The `football` console script exposes the data pipeline and Sprint 2 gate:

```bash
football ingest competitions
football ingest season <id>
football ingest season <id> --competition-id <id>
football validate season <id>
football validate season <id> --competition-id <id>
football resolve sprint2-lifecycle
football resolve sprint2-kickoffs
football resolve sprint2-corners
football evaluate sprint2
football provider status
football provider status --provider-id <id>
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

`football resolve sprint2-lifecycle` publishes immutable `completed` claims only when every match
in the approved corpus has exact score-reconciled validator v3 lineage and terminal event evidence.
It does not alter provider match observations or treat `match_status=available` as football
completion. See [Match lifecycle claims](lifecycle-claims.md).

`football resolve sprint2-kickoffs` preserves timezone-naive provider date/time and publishes
separate UTC claims using exact lifecycle and competition facts, `Europe/London`, and pinned
`tzdata 2026.3`. See [Match kickoff claims](kickoff-claims.md).

`football resolve sprint2-corners` publishes immutable home/away corner labels from exact
StatsBomb `Pass` / pass-type `Corner` ID-and-name semantics. Each label binds the completed
lifecycle claim, canonical teams, validated event file and checksums, source lineage, and validator
run. It does not add outcomes to pre-match forecast contexts. See [Match corner labels](corner-labels.md).

`football evaluate sprint2` runs the pinned Sprint 2 workflow until the first blocking stage. It
starts with the approved StatsBomb EPL 2015/16 corpus (`competition_id=2`, `season_id=27`). A
complete execution retains an immutable report plus JSON, Parquet, bootstrap, calibration, and SVG
evidence, then returns exit code `7` at `baseline-policy-review`. Missing corpus data produces
`null` scope and metric fields; the command never substitutes synthetic matches or zero-valued
metrics. `make sprint2-evaluate` supplies repository provenance and propagates FAIL as a failed Make
target. Later modelling phases remain blocked.

The Make target refuses a dirty worktree so the recorded commit identifies the executed code.

## Configuration

Use environment variables for routine execution:

```bash
export FOOTBALL_DATABASE_URL='postgresql://football:football-local-only@127.0.0.1:55433/football?sslmode=disable'
export FOOTBALL_DATA_ROOT='.local/football-data'
export FOOTBALL_STATSBOMB_GIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_QUALITY_POLICY='schemas/quality/statsbomb-quality-policy-v1.json'
export FOOTBALL_SPRINT2_REPORT_ROOT='.local/reports/sprint2'
export FOOTBALL_CODE_COMMIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_DEPENDENCY_LOCK_SHA256='<64-character-lowercase-sha256>'
```

`FOOTBALL_STATSBOMB_GIT_SHA` is required only for ingestion. The code and dependency checksums are
required when an eligible evaluation reaches execution; the Make target derives them from `HEAD`
and `uv.lock`. Other defaults target the repository's local Compose database,
`.local/football-data`, `.local/reports/sprint2`, and checked-in quality policy. Equivalent global
options include `--code-commit-sha` and `--dependency-lock-sha256`; place global options before the
command.

The CLI assumes production migrations are current. It never migrates PostgreSQL automatically.

`football provider status` is read-only and reports registered capability
declarations without connecting to PostgreSQL or a provider. Sync, backfill,
and cursor mutation commands remain gated on the durable worker contracts.

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
