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

The live provider history budget is bounded by `MVP_MAX_HISTORY_LEAGUES` per
sync. MatchForge selects leagues with no prior attempt first, then the
least-recently attempted leagues. Repeated syncs therefore cover every observed
competition with scheduled fixtures instead of repeatedly spending the budget
on the same leagues. The candidate set includes stored future fixtures, not only
fixtures in the current two-day provider window.
When a provider plan limits recent historical seasons,
`MVP_MAX_HISTORY_SEASON` selects the newest accessible season. This affects
history acquisition only; target fixtures and point-in-time filtering remain
unchanged.

Full sync order is MVP provider sync, OpenFootball, Football-Data.co.uk, canonical reconciliation during import, forecast refresh, then external-prediction collection.

## Admin operations

`/admin/data-sync` exposes only fixed synchronization types. Go persists a `football.product_sync_runs` record, enforces one queued/running operation, and starts a controlled Python argument array from `MATCHFORGE_REPO_ROOT`. Browser input cannot select an executable or arbitrary arguments.

The POST returns `202 Accepted`. The page polls the individual run, disables all start buttons while a run is active, then shows the command's structured JSON summary. Run logs remain local under `.local/sync-runs`.

Research remains `MODEL_RESEARCH_PAUSED_FOR_MVP`. Existing published forecasts remain immutable; refresh creates only missing future forecasts.

## Verified full backfill

The 30 September 2026 full run used OpenFootball revision `e6744429ee395bc86f247348c6184bb08d4eb361`. It mapped all 90,036 parsed completed matches from 291 resources, 21 season labels, 47 competitions, and 20 countries. The stored range is 12 July 2010 through 20 September 2026.

Football-Data.co.uk discovered 37 resources containing 713 CSV files and 34 ZIP archives. It mapped all 241,379 parsed completed matches from 34 season labels, 22 competitions, and 11 countries. The stored range is 23 July 1993 through 28 September 2026.

The sources share 5,487 canonical matches. Scores agree for 5,481; six disagreements are preserved as source-result conflicts. Both providers completed with zero mapping failures.

A repeat Football-Data.co.uk run reused all 37 resources, parsed zero CSV files, and inserted zero rows. Closed seasons are skipped before remote artifact download. Current or unknown seasons remain eligible for hash comparison and refresh.
