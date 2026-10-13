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

The same operations are available on `/admin/data-sync`. Scheduling is opt-in: an omitted or zero `MATCHFORGE_OPERATIONAL_SYNC_INTERVAL` disables it; an enabled interval must be at least `30s`. Provider enablement is also required. FotMob live, PitchAPI live, and bulk work have independent database lanes; browser polling is not required. Worker heartbeats recover abandoned leases. API-Football quota exhaustion stops that provider's requests until the UTC reset without blocking the other providers.

Administrative mutations require a loopback API listener, loopback client, approved loopback Host with the configured API port, and `application/json`. Browser requests must carry the exact configured `WEB_ORIGIN`; this Origin and JSON boundary prevents cross-origin browser mutations. Origin-less CLI and Codex requests additionally require `Authorization: Bearer <MATCHFORGE_ADMIN_CLI_TOKEN>`. An absent token denies origin-less access. Keep this secret in ignored `.env`, never in frontend environment variables or logs. Non-loopback administrative exposure remains disabled.

Before upgrading worker fencing, stop existing synchronization processes and deploy the updated API and Python workers together. New workers carry database ownership credentials; publication transactions lock and check their active run lease and historical claim. Ownership loss terminates the process group, rejects subsequent writes, and cannot revive terminal run state. Old binaries do not carry these credentials and must not remain running during this upgrade. Direct operator CLI execution retains its existing behavior; history scope execution always uses claim tokens.

Active runs can be stopped with `POST /v1/admin/sync-runs/{run_id}/stop`. Stopping terminates the owned sync process group and records terminal `CANCELLED` status. Failed or cancelled runs can be retried with `POST /v1/admin/sync-runs/{run_id}/retry`; the new run preserves the original date and selector parameters and records `retry_of_run_id` in its parameters.

History synchronization calculates standings from stored match history when the provider standings request is unavailable. A standings transport failure or plan restriction therefore cannot keep an otherwise usable history job pending.

Raw responses are checksum-addressed under `FOOTBALL_DATA_ROOT/operational`. Normalized fixture observations retain their original mapping; a reviewed correction appends a mapped observation. Verified provider IDs and explicit crosswalks permit automatic reconciliation within the configured kickoff tolerance. Name/kickoff similarity produces review candidates only. Date-only history requires verified competition/team IDs, matching UTC date and scores. Conflicts remain in `product_provider_mapping_decisions` for operator review. Complete provider identities without verified crosswalks may create `PROVISIONAL` fixtures, never forecast-eligible identities. Unknown competition metadata stays `Unknown`/`UNKNOWN`; seasons come from the source scope, not the kickoff year. Manual acceptance records `MANUAL_ACCEPTED` evidence and a prospective identity admission.

New OpenFootball and Football-Data.co.uk imports write immutable `HistoricalSourceManifestV1` files. Registrations hash the manifest bytes and verify every referenced resource's size and SHA-256. Replay preserves the original acquisition time. New snapshot revisions use `manifest-v1:`. Legacy registrations remain unchanged and are explicitly `LEGACY_MANIFEST_UNVERIFIED`, including the 48 measured pathname-hashed registrations. Independently verified raw-resource bytes can support prospective identity admission; that verification does not prove the legacy manifest or cross-provider equivalence. Missing or tampered resources remain unverified. Optional append-only repair requires new owner authorization and evidence linked to the original registration.

`ProductIdentityTrustV1` requires retained provider/identifier evidence and the exact approved UUID algorithm for an origin anchor. An origin anchor proves identity within its provider. Cross-provider equivalence requires a versioned explicit crosswalk with compatible context, or an operator review linked to retained observations. Confidence 1 alone is insufficient. Name/kickoff candidates remain `REVIEW_REQUIRED`; manual review validates retained provider IDs, kickoff and conflicting finished results before applying a mapping. Corrections close the earlier mapping interval and create a successor; original observations and source evidence remain retained.

Raw `product_team_match_history` evidence is retained. Identity admissions and history eligibility/fact changes are append-only decisions with separate source and decision timestamps. Forecast reconstruction calls `product_eligible_history_at(knowledge_cutoff)`; the current `product_eligible_match_history` view serves prospective context. Later promotion, revocation, quarantine or correction cannot change earlier cutoffs. Migration `202610121100` withholds history lacking verified admission evidence. After migration, seed only verified retained mappings prospectively with `python -m football.product.identity_audit --database-url "$DATABASE_URL" --data-root "$FOOTBALL_DATA_ROOT" --admit-verified`. Without `--admit-verified`, the command is read-only. It reports verified origin/crosswalk, unresolved and contradictory classifications; unresolved cases require review. No admission time is inferred or backdated. Import counts differ from eligible counts; the ten-match requirement is unchanged. `history-coverage` reports each upcoming fixture's reason and every unmatched PitchAPI observation with its snapshot and latest review reason.

Historical acquisition uses persistent provider/competition/season checkpoints, cached checksum-verified snapshots, stale-claim recovery, failure cooldowns, and fair attempt ordering. PitchAPI discovers the supported league catalogue; FotMob discovers seasons for configured competition mappings. Per-run budgets bound acquisition without limiting eventual scope coverage:

```bash
uv run python -m football.product.cli backfill-history --provider-only fotmob --competition 47 --provider-discovery-budget 1 --provider-scope-budget 2
uv run python -m football.product.cli backfill-history --provider-only pitchapi --provider-scope-budget 8
uv run python -m football.product.cli history-coverage
```

Use `--season YYYY/YYYY` to select a season and `--refresh` to reacquire selected scopes. After reconciliation, run the canonical-history audit and the existing forecast refresh. Failed scopes preserve raw evidence and explicit reasons; they are not reported as successful imports.

Detailed match resources are stored with `development_only=true`. Their conservative `known_at` is the actual acquisition time, so they are eligible only for later prospective development cutoffs. Production forecasts and protected evaluation datasets never read them. A non-persisting preview is available with `development-provider-preview --provider fotmob --fixture-id UUID --knowledge-cutoff ISO_TIMESTAMP` (also supports PitchAPI); it rejects cutoffs at or after kickoff and structurally excludes the target fixture. It uses verified history and mappings known by the cutoff, keeps each provider's shot/xG definitions separate, and feeds qualified xG through the existing model interface without blending other providers' xG. Lineup, rating, and H2H resources are diagnostic context, not new model weights. The frozen champion has `beta_xg_for=0`; `model.uses_provider_xg` makes that limitation explicit. Published forecasts and champion parameters remain unchanged.

External predictions settle only from a final score explicitly identified as the regulation-time result. Extra-time, penalty-shootout, and unknown-basis totals remain pending so knockout scores cannot be graded as 90-minute markets.
