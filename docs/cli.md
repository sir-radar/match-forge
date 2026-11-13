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
run. Use `football resolve corners --dataset-version <uuid> --source-snapshot <uuid>`
for another published StatsBomb dataset with complete lifecycle evidence for that
exact pair. See [corner outcome labels](backtesting.md#corner-outcome-labels).

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
set -a
. ./.env
set +a
export FOOTBALL_DATA_ROOT='.local/football-data'
export FOOTBALL_STATSBOMB_GIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_QUALITY_POLICY='schemas/quality/statsbomb-quality-policy-v1.json'
export FOOTBALL_SPRINT2_REPORT_ROOT='.local/reports/sprint2'
export FOOTBALL_CODE_COMMIT_SHA='<40-character-lowercase-git-sha>'
export FOOTBALL_DEPENDENCY_LOCK_SHA256='<64-character-lowercase-sha256>'
```

`FOOTBALL_STATSBOMB_GIT_SHA` is required only for ingestion. The code and dependency checksums are
required when an eligible evaluation reaches execution; the Make target derives them from `HEAD`
and `uv.lock`. `DATABASE_URL` or `FOOTBALL_DATABASE_URL` must be set in `.env`; no database
credentials are embedded in application code. Other defaults target `.local/football-data`,
`.local/reports/sprint2`, and checked-in quality policy. Equivalent global
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

## Operational history replay

The product CLI (`python -m football.product.cli backfill-history`) maintains
separate provider, native competition, and native season scopes. `--refresh`
requeues only due scopes; it preserves attempts, retry deadlines, and active
worker claims. Native labels such as `2024/2025 - Apertura` and
`2024/2025 - Clausura` remain separate, including in retained response lookup.
An absent fixture list or an empty advertised season cannot complete a scope.

Forecast refresh claims competition rows before fixture rows and skips busy rows.
Deferred work remains pending for a later worker. Identity admission and fixture
reconciliation acquire the identity admission advisory lock before the fixture
crosswalk advisory lock. Maintenance can run alongside operational polling.

Use `make openfootball-sync` and `make football-data-uk-sync` for bulk results.
The former reads a pinned Git mirror and the latter preserves official CSV and
ZIP downloads. Changed resources append immutable snapshots; exact replays
reuse them. Provider conflicts stay separate from the stored canonical result.
`make history-backfill` or `backfill-history --provider-only <provider>` can
select FotMob, PitchAPI, OpenFootball or Football-Data.co.uk. API-Football and
football-data.org use the shared history queue. Its fallback order is eligible
local history, requested-season API-Football within its cap, explicit
football-data.org requested/previous-season coverage, then the capped
API-Football season. The cap applies only to API-Football.

For FotMob/PitchAPI, use the per-provider history actions in Admin Data Sync or
`backfill-history --provider-only` with optional `--competition`, `--season`,
`--provider-discovery-budget` and `--provider-scope-budget`. Closed seasons
replay verified retained bytes by default. Advertised scopes without qualified
identity or regulation scores cannot complete. Review per-provider unmatched
and history-depth diagnostics with `history-coverage`. Repair existing
provisional geography from retained bytes with
`refresh-competition-geography --provider fotmob` or `--provider pitchapi`.
These repairs do not fetch sources or refresh forecasts.

### Operational sync

`make fotmob-sync` and `make pitchapi-sync` accept `FROM_DATE` and `DATE`.
Enable each provider in the local environment before use. Live scheduling
is opt-in via `MATCHFORGE_OPERATIONAL_SYNC_INTERVAL` (minimum 30 seconds).
Scheduled history is separately opt-in via `MATCHFORGE_HISTORY_SYNC_ENABLED`
and uses `MATCHFORGE_HISTORY_SYNC_INTERVAL` (minimum one hour). History
defers to live work and respects per-provider quotas and scope budgets.
The Make targets require current migrations. Admin Data Sync can stop or
retry a run; retry preserves the original selectors. Failed providers and
unqualified history remain explicit in each run summary.

Use `provider-mapping-review --provider fotmob` (or `pitchapi`) to inspect
unresolved mappings. Supply `--provider-match-id` and `--fixture-id` only for
an independently verified relationship. Use `development-provider-preview
--provider fotmob --fixture-id UUID --knowledge-cutoff ISO_TIMESTAMP` for a
read-only pre-kickoff diagnostic. The target fixture is excluded, provider xG
definitions stay separate and this path does not publish forecasts.

### Reviewed team identity corrections

Run the read-only preview with separately reviewed IDs:

```bash
uv run python -m football.product.identity_correction \
  --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" \
  --source-mapping-id "$SOURCE_MAPPING_ID" --target-mapping-id "$TARGET_MAPPING_ID" \
  --original-decision-id "$ORIGINAL_DECISION_ID" \
  --fixture-registration-id "$FIXTURE_REGISTRATION_ID" --orientation HOME
```

The operation verifies the exact original contradiction, fixture evidence,
retained bytes and target admission under `ProductTeamIdentityCorrectionV1`.
It appends a prospective correction for one team. Before an owner-approved
live `--apply`, verify current migrations and a recoverable backup, then run
`uv run python -m football.product.maintenance --output .local/r3-quiescence.json`.
Any other writer blocks the operation. Compare protected registrations and
publication hashes after applying. Rollback uses a prospective revocation
through the existing correction owner. See [identity rules](architecture.md#identity).

## External prediction bindings

`make external-predictions DATE=YYYY-MM-DD` runs enabled sources independently.
Use `SOURCE=<source>` to select one. The optional
`MVP_EXTERNAL_PREDICTIONS_IMPORT_FILE` uses the append-only manual import path.
A requested date outside the published window can produce `NO_DATE_PAGE`.
The repository timer specifies 06:00 Africa/Lagos. Verify installation and
alert delivery on the operating host separately.

For a capture without a native fixture ID, an operator can review an existing
verified native mapping against retained evidence:

```bash
uv run python -m football.product.cli --database-url "$DATABASE_URL" \
  external-binding-review --prediction-id "$PREDICTION_ID" \
  --mapping-id "$MAPPING_ID" --reason '<retained evidence and review rationale>'
```

The binding records the source revision, snapshot, mapping and reason. A retry
reuses the binding. Mapping revocation queues recovery and retains the original
capture. See [comparison and settlement rules](architecture.md#external-prediction-comparison).
