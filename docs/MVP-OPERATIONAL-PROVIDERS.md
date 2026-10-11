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
```

The same operations are available on `/admin/data-sync`. Set `MATCHFORGE_OPERATIONAL_SYNC_INTERVAL` to a Go duration of at least `1m` to alternate enabled provider jobs. The existing single-active-run database constraint coordinates manual and scheduled work.

Raw responses are checksum-addressed under `FOOTBALL_DATA_ROOT/operational`. Normalized fixture observations are append-only. Canonical fixtures update only through verified provider mappings; unmatched observations remain visible in sync counts and are not converted into new fixtures through name similarity.

Detailed match resources are stored with `development_only=true`. `point_in_time_eligibility=UNKNOWN` is the default because acquisition time does not prove historical publication time. These rows are not read by production forecasts or protected evaluation datasets.

External predictions settle only from a final score explicitly identified as the regulation-time result. Extra-time, penalty-shootout, and unknown-basis totals remain pending so knockout scores cannot be graded as 90-minute markets.
