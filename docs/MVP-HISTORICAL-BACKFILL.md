# MVP historical backfill

## Scope

MatchForge imports completed historical results from OpenFootball and Football-Data.co.uk. These providers extend the canonical product history; they do not replace API-Football or football-data.org and do not change `MVP_FORECAST` mathematics.

## Flow

```text
provider catalog
→ immutable local resource cache
→ source snapshot and resource registration
→ provider parser
→ competition and team resolution
→ canonical match reconciliation
→ football.product_team_match_history
→ missing-forecast refresh
```

OpenFootball is acquired as a Git mirror beneath `.local/providers/openfootball`. The exact commit SHA is stored as the source revision. Season directories and competition JSON files are discovered from the mirror; downloaded data is not committed.

Football-Data.co.uk is acquired from its published download indexes. Discovery follows official index links and retains complete CSV or ZIP resources beneath `.local/football-data/football_data_uk`. CSV parsing reads football result columns only. Betting columns remain intact in the cached source artifact and never enter `MVP_FORECAST`.

## Incremental behavior

Every resource is keyed by provider path and SHA-256. A parsed resource with the same identity and hash returns `SKIP_ALREADY_IMPORTED` behavior through the `resources_cached` summary count. A changed current-season file creates a new immutable source snapshot and only newly completed canonical matches are inserted.

OpenFootball revisions and Football-Data.co.uk resource hashes remain visible through `football.source_snapshots` and `football.source_resources`.

## Canonical resolution

Competition resolution uses, in order:

1. an existing provider mapping;
2. a verified provider-code crosswalk to an existing API-Football mapping;
3. a new provider-specific canonical competition when no crosswalk exists.

Team resolution uses, in order:

1. an approved provider-ID crosswalk;
2. an existing provider mapping or product alias;
3. a new traceable provider-specific team.

Cross-provider merging requires an explicit provider-ID crosswalk. Names never
establish canonical identity. Migration `202610040100` repairs previously split
product fixtures and history without changing match results or forecast rules.

Matches reconcile on canonical competition, home team, away team, and kickoff. Exact timestamps allow a three-hour provider tolerance. Date-only sources use the calendar date and preserve `source_kickoff_precision = DATE_ONLY`. Forecast history admits a date-only result only when its calendar date is before the target date, preventing ambiguous same-day ordering.

If a matched source score disagrees with the stored canonical result, MatchForge records `football.product_source_result_conflicts`. The existing result is not overwritten.

## Commands

```bash
uv run python -m football.product.cli backfill-openfootball
uv run python -m football.product.cli backfill-football-data-uk
uv run python -m football.product.cli backfill-history
uv run python -m football.product.cli refresh-forecasts
uv run python -m football.product.cli sync-all
```

Backfill commands accept optional `--season`, `--competition`, and `--country` selectors. With no selector, all discovered usable data is processed. `--refresh` runs missing-forecast generation after a provider backfill.

Equivalent Make targets are:

```bash
make openfootball-sync
make football-data-uk-sync
make history-backfill
make forecast-refresh
make all-data-sync
```

MVP and full sync queue every eligible competition-season in
`football.product_history_sync_queue`. `MVP_HISTORY_SYNC_CONCURRENCY` controls
the bounded worker pool and defaults to `3`; it does not cap queue size.
Workers process existing due jobs first, then candidates with no prior attempt,
then least-recently attempted candidates. Each job commits independently.
Transient failures return to `PENDING` with a capped retry delay, and expired
worker leases are recovered by a later sync. Each invocation attempts a queued
job at most once. The command exits when no job is currently runnable, leaving
future retries for a later invocation. The candidate set includes
stored future fixtures, not only fixtures in the current two-day provider window.
`API_FOOTBALL_MAX_HISTORY_SEASON` is an API-Football-only entitlement cap. It
does not limit other providers or canonical MatchForge history. For each
scheduled competition-season, history resolution now uses this order:

1. sufficient eligible local history, including a team's mapped history from a
   previous competition;
2. requested-season API-Football history when that season is within its cap;
3. requested and previous-season football-data.org history for explicitly
   mapped qualified competitions;
4. the capped API-Football season only after newer alternate-provider data is
   exhausted.

Compatible result observations contribute to the same canonical history and
canonical fixture identity deduplicates overlap. Provider match mappings,
source snapshots, original seasons, kickoff timestamps, and result-conflict
records preserve provenance. Sync attempts record the ordered fallback path and
providers used. Provider-specific metrics such as xG are never copied between
series; no alternate MVP provider currently supplies qualified compatible xG.
If real history remains below the ten-match requirement, MatchForge leaves the
fixture unavailable instead of manufacturing history or relabelling a season.

Full sync order is MVP provider sync, OpenFootball, Football-Data.co.uk, canonical reconciliation during import, forecast refresh, then external-prediction collection.

## Independent team identity corrections

`football.product.identity_correction` verifies retained Football-Data.org and
API-Football team IDs against an approved explicit crosswalk and retained
FotMob fixture evidence. It accepts a Football-Data.org match-provider
registration and verified raw bytes; no operational observation is fabricated.
API-Football team/league/season evidence is required, but an exact shared future
fixture is not invented. Names alone never establish equivalence.

Each request contains `source_mapping_id`, `target_mapping_id`,
`original_decision_id`, `fixture_registration_id` and `orientation` (`HOME` or
`AWAY`). `qualify_team_correction` is read-only. `correct_team_identity` inserts
one linked CROSSWALK admission in an atomic transaction/savepoint and returns
its actual decision ID/time. The caller owns the outer commit. Confidence must
already be 1 and the shared R2 trust predicate must pass. Qualification fails
closed on wrong IDs/UUIDs, reversed orientation, missing/tampered bytes,
revoked target identity, incompatible context or an additional contradiction.

The evidence contract is `ProductTeamIdentityCorrectionV1`. It records the
unchanged original decision, source/target registrations and hashes,
competition/season/kickoff/orientation and the correction reason
`INCORRECT_PRIOR_MAPPING`. Correcting one team never approves the other or
merges the provider-scoped fixtures. The whole-fixture
`OperationalProviderSync.apply_reviewed_mapping` path is not used.

Run read-only qualification with separately reviewed IDs:

```bash
python -m football.product.identity_correction \
  --database-url "$DATABASE_URL" --data-root .local/football-data \
  --source-mapping-id "$SOURCE_MAPPING_ID" --target-mapping-id "$TARGET_MAPPING_ID" \
  --original-decision-id "$ORIGINAL_DECISION_ID" \
  --fixture-registration-id "$FIXTURE_REGISTRATION_ID" --orientation HOME
```

Only append `--apply` after the specific database mutation is authorised and
migration `202610140100_team_identity_corrections.sql` is deployed. Deploy all
required preceding migrations before code that reads the new effective views.
The migration is forward-only, preserves existing decisions and performs no
automatic corrections/admissions. Snapshot and verify the database and retained
files before deployment; compare original decisions, registrations, observations,
published payload hashes and artifact hashes afterwards. Do not downgrade or
delete committed correction events to roll back an admission.

`revoke_team_correction(connection, decision_id, reason)` appends a prospective
REVOKED event. Earlier cutoffs retain the admitted interval. Changes to source
validation, source/target mapping metadata, target admission or a new retained
contradiction revoke affected corrections prospectively. Revalidation checks
retained bytes; tampering cannot trigger automatic re-admission. Identical retries
return the existing decision, including its revoked state. The existing R2
advisory lock and a correction-only unique index serialize competing requests;
unlinked continuations and conflicting corrections are rejected. Standard
PostgreSQL serialization failures still require retrying the whole transaction.

Current reads use `product_effective_team_mappings`,
`product_effective_team_aliases` and `product_effective_fixtures`. Physical rows
remain evidence. Historical callers use `product_team_identity_at` or
`product_fixture_team_at` with their explicit knowledge cutoff. Eligibility and
history snapshots share this resolution; current operational IDs must never
replace a historical cutoff. Database triggers verify registrations and links;
only the Python operation verifies retained file bytes and approved crosswalks.

## Admin operations

`/admin/data-sync` exposes only fixed synchronization types. Go persists a `football.product_sync_runs` record, enforces one queued/running operation, and starts a controlled Python argument array from `MATCHFORGE_REPO_ROOT`. Browser input cannot select an executable or arbitrary arguments.

The POST returns `202 Accepted`. The page polls the individual run, disables all start buttons while a run is active, then shows the command's structured JSON summary. Run logs remain local under `.local/sync-runs`.

Research remains `MODEL_RESEARCH_PAUSED_FOR_MVP`. Existing published forecasts remain immutable; refresh creates only missing future forecasts.

## Verified full backfill

The 30 September 2026 full run used OpenFootball revision `e6744429ee395bc86f247348c6184bb08d4eb361`. It mapped all 90,036 parsed completed matches from 291 resources, 21 season labels, 47 competitions, and 20 countries. The stored range is 12 July 2010 through 20 September 2026.

Football-Data.co.uk discovered 37 resources containing 713 CSV files and 34 ZIP archives. It mapped all 241,379 parsed completed matches from 34 season labels, 22 competitions, and 11 countries. The stored range is 23 July 1993 through 28 September 2026.

The sources share 5,487 canonical matches. Scores agree for 5,481; six disagreements are preserved as source-result conflicts. Both providers completed with zero mapping failures.

A repeat Football-Data.co.uk run reused all 37 resources, parsed zero CSV files, and inserted zero rows. Closed seasons are skipped before remote artifact download. Current or unknown seasons remain eligible for hash comparison and refresh.

## Download and ZIP bounds

Authenticated legacy API downloads and public pages reuse the existing transport
utilities with bounded body reads and existing 30s/60s socket timeouts. Redirect
bodies are closed without reading, standard redirect validation/loop limits remain,
and credentials are removed across origins. Error bodies are closed. Body elapsed
checks run between chunks; a pending read retains its socket timeout, so the body
limit may include one final socket-wait interval. Original acquisition timestamps
are preserved; new registrations timestamp completed acquisition.

All 38 retained supported ZIP samples were content-hash and CRC verified before
choosing limits. Maxima were 1,111,382 compressed bytes, 3,957,667 extracted bytes,
22 entries, 294,390 bytes per file and 10.43x individual expansion. Configurable
ceilings are `MATCHFORGE_ARCHIVE_COMPRESSED_BYTES=2097152`,
`MATCHFORGE_ARCHIVE_EXTRACTED_BYTES=16777216`, `MATCHFORGE_ARCHIVE_ENTRIES=128`,
`MATCHFORGE_ARCHIVE_FILE_BYTES=1048576`, `MATCHFORGE_ARCHIVE_RATIO=32` and
`MATCHFORGE_ARCHIVE_EXTRACTION_SECONDS=5`. All retained samples remain compatible.

Validate names, duplicate paths, links/types, encryption, compression and declared
sizes before decoding. Only stored/deflated ZIP members are supported. CSV members
are decoded into bounded in-memory buffers before ingestion; no archive pathname
is extracted to disk, and ingestion/database time is not charged as extraction
work. Memory is bounded by compressed bytes, metadata and at most 16MiB of decoded
buffers, rather than a claimed process-wide RSS cap. Invalid or excessive archives
fail explicitly. New unusually large supported resources require measurement and
review before increasing limits; limits never increase automatically.

## Controlled R3 refill and qualification

FotMob discovers `allAvailableSeasons` separately for each configured competition.
Season aliases are normalized and deduplicated; multi-year qualification periods
remain valid. The requested competition and selected season must match retained
response metadata. There is no global FotMob start year. Fixture/result depth does
not establish xG, lineup, event, shot-map or other advanced-feature depth.

Empty advertised seasons report `ADVERTISED_BUT_UNUSABLE`. Stored results without
qualified identities or regulation-score evidence remain blocked; they cannot
mark a history scope complete. Closed retained responses preserve their original
acquisition times. New observations and admissions use actual execution times.
Football-Data.co.uk discovery fails explicitly when its page budget leaves
unvisited catalogue pages. Fixture reconciliation first selects nearby history
IDs, then reads their latest dated eligibility decisions; historical registration
indexes also cover closed mappings.

R3 origin-method repair closes an old mapping revision and appends a new revision
only when full-confidence, verified retained IDs reproduce the same provider-origin
UUID. Canonical IDs stay unchanged. Correct provider origins remain deterministic
when crosswalk review runs; a shared identity does not turn its originating mapping
into a foreign crosswalk. Existing rejection and revocation decisions require
separate review. Historical eligibility decisions remain append-only.

Forecast diagnostics distinguish raw H2Hs, qualified H2Hs and each team's general
history. They use cutoff-qualified history and effective corrected team identities.
Provider-derived forecast targets must also have qualified provider competition
and team mappings. The champion's ten-match requirement and artifact remain fixed.

Before live corrections, run the maintenance preflight:

```sh
uv run python -m football.product.maintenance --output .local/r3-quiescence.json
```

It checks socket ownership, repository processes, database clients and durable jobs.
Verified local `pg_isready` probes and PostgreSQL autovacuum are recorded separately.
Other writers block correction work. The refill is a one-time controlled operation;
automatic historical acquisition retains its approved disabled default.
