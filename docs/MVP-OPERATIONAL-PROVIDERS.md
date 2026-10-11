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

The same operations are available on `/admin/data-sync`. Set `MATCHFORGE_OPERATIONAL_SYNC_INTERVAL` to a Go duration of at least `1m` to alternate enabled provider jobs. The existing single-active-run database constraint coordinates manual and scheduled work.

Active runs can be stopped with `POST /v1/admin/sync-runs/{run_id}/stop`. Stopping terminates the owned sync process group and records terminal `CANCELLED` status. Failed or cancelled runs can be retried with `POST /v1/admin/sync-runs/{run_id}/retry`; the new run preserves the original date and selector parameters and records `retry_of_run_id` in its parameters.

History synchronization calculates standings from stored match history when the provider standings request is unavailable. A standings transport failure or plan restriction therefore cannot keep an otherwise usable history job pending.

Raw responses are checksum-addressed under `FOOTBALL_DATA_ROOT/operational`. Normalized fixture observations are append-only. Existing verified provider IDs win. Otherwise, automatic reconciliation requires one unique canonical fixture with exact normalized competition, home team, away team, and UTC kickoff within ten minutes. Conflicting scores, zero candidates, and multiple candidates are retained in `product_provider_mapping_decisions` for the review command; they never create canonical entities. The second review command is the explicit operator acceptance path and records `MANUAL_ACCEPTED` evidence.

Detailed match resources are stored with `development_only=true`. Their conservative `known_at` is the actual acquisition time, so they are eligible only for later prospective development cutoffs. Production forecasts and protected evaluation datasets never read them. A non-persisting preview is available with `development-provider-preview --fixture-id UUID --knowledge-cutoff ISO_TIMESTAMP`; it rejects cutoffs at or after kickoff and structurally excludes the target fixture.

External predictions settle only from a final score explicitly identified as the regulation-time result. Extra-time, penalty-shootout, and unknown-basis totals remain pending so knockout scores cannot be graded as 90-minute markets.
