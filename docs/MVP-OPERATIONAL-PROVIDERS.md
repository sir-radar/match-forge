# Operational provider sync

FotMob and PitchAPI operational ingestion is separate from protected research snapshots and frozen evaluations.

Enable providers only in local development:

```text
MATCHFORGE_FOTMOB_ENABLED=true
MATCHFORGE_PITCHAPI_ENABLED=true
```

FotMob uses ordinary `https://www.fotmob.com/api/data/` JSON endpoints. It does not use signed hosts, browser impersonation, CAPTCHA handling, or access-control workarounds. Disable it when ordinary access is unavailable. PitchAPI uses `PITCH_API_TOKEN` server-side and always requests `status=all` for fixture listings.

Endpoint mapping and cache behavior were cross-checked against the MIT-licensed `writeshh/FotMob-API` reference. MatchForge keeps its own Python adapter and does not add a Node.js service.

Manual commands:

```bash
uv run python -m football.product.cli fotmob-sync --from-date 2026-10-08 --date 2026-10-09
uv run python -m football.product.cli pitchapi-sync --from-date 2026-10-08 --date 2026-10-09
uv run python -m football.product.cli provider-mapping-review --provider fotmob
uv run python -m football.product.cli provider-mapping-review --provider fotmob --provider-match-id PROVIDER_ID --fixture-id MATCHFORGE_UUID
```

The same operations are available on `/admin/data-sync`. Set `MATCHFORGE_OPERATIONAL_SYNC_INTERVAL` to a Go duration of at least `15s` (default `30s`). FotMob live, PitchAPI live, and bulk work have independent database lanes; browser polling is not required. Worker heartbeats recover abandoned leases. API-Football quota exhaustion stops that provider's requests until the UTC reset without blocking the other providers.

Active runs can be stopped with `POST /v1/admin/sync-runs/{run_id}/stop`. Stopping terminates the owned sync process group and records terminal `CANCELLED` status. Failed or cancelled runs can be retried with `POST /v1/admin/sync-runs/{run_id}/retry`; the new run preserves the original date and selector parameters and records `retry_of_run_id` in its parameters.

History synchronization calculates standings from stored match history when the provider standings request is unavailable. A standings transport failure or plan restriction therefore cannot keep an otherwise usable history job pending.

Raw responses are checksum-addressed under `FOOTBALL_DATA_ROOT/operational`. Normalized fixture observations are append-only. Existing verified provider IDs win. Otherwise, automatic reconciliation requires one unique canonical fixture with exact normalized competition, home team, away team, and UTC kickoff within ten minutes. Explicit competition/team crosswalks also permit matching date-only history when the UTC date and both scores agree. Conflicts remain in `product_provider_mapping_decisions` for operator review. Complete provider identities without verified crosswalks may create `PROVISIONAL` fixtures, never forecast-eligible identities. Unknown competition metadata stays `Unknown`/`UNKNOWN`; seasons come from the source scope, not the kickoff year. Manual acceptance records `MANUAL_ACCEPTED` evidence.

Raw `product_team_match_history` evidence is retained. Forecasts, standings, and qualified context read `product_eligible_match_history`, excluding provisional identities, quarantine, and secondary duplicates, with an explicit acquisition-time cutoff. Import counts therefore differ from eligible counts; the ten-match requirement is unchanged. `history-coverage` reports each upcoming fixture's reason and every unmatched PitchAPI observation with its snapshot and latest review reason.

Historical acquisition uses persistent provider/competition/season checkpoints, cached checksum-verified snapshots, stale-claim recovery, failure cooldowns, and fair attempt ordering. PitchAPI discovers the supported league catalogue; FotMob discovers seasons for configured competition mappings. Per-run budgets bound acquisition without limiting eventual scope coverage:

```bash
uv run python -m football.product.cli backfill-history --provider-only fotmob --competition 47 --provider-discovery-budget 1 --provider-scope-budget 2
uv run python -m football.product.cli backfill-history --provider-only pitchapi --provider-scope-budget 8
uv run python -m football.product.cli history-coverage
```

Use `--season YYYY/YYYY` to select a season and `--refresh` to reacquire selected scopes. After reconciliation, run the canonical-history audit and the existing forecast refresh. Failed scopes preserve raw evidence and explicit reasons; they are not reported as successful imports.

Detailed match resources are stored with `development_only=true`. Their conservative `known_at` is the actual acquisition time, so they are eligible only for later prospective development cutoffs. Production forecasts and protected evaluation datasets never read them. A non-persisting preview is available with `development-provider-preview --provider fotmob --fixture-id UUID --knowledge-cutoff ISO_TIMESTAMP` (also supports PitchAPI); it rejects cutoffs at or after kickoff and structurally excludes the target fixture. It uses verified history and mappings known by the cutoff, keeps each provider's shot/xG definitions separate, and feeds qualified xG through the existing model interface without blending other providers' xG. Lineup, rating, and H2H resources are diagnostic context, not new model weights. The frozen champion has `beta_xg_for=0`; `model.uses_provider_xg` makes that limitation explicit. Published forecasts and champion parameters remain unchanged.

External predictions settle only from a final score explicitly identified as the regulation-time result. Extra-time, penalty-shootout, and unknown-basis totals remain pending so knockout scores cannot be graded as 90-minute markets.
