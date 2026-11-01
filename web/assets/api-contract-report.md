# API contract report

- Contract source: `docs/api/openapi.yaml` plus Go response types in `go/api/internal/app/product.go`.
- Frontend boundary: `web/lib/contracts.ts` validates objects, arrays, finite numbers, probabilities, enums used by controls, nullable values and source maps before rendering.
- Filters: continent, country, competition, division/forecast availability, date, source, market and agreement are passed explicitly.
- Daily predictions: `/predictions` sends one exact `date`; source metrics use
  the equivalent closed `date_from`/`date_to` range. Previous and next controls
  advance by one UTC day, and the renderer rejects off-day rows.
- Request safety: `useResource` aborts superseded requests, ignores stale completions, preserves previous data while refreshing and exposes retry.
- Partial failure: fixture, forecast, context and external-selection resources render independently. Missing context cannot hide a fixture or overwrite a forecast.
- Mutation/optimistic state: product endpoints are read-only. Admin submits durable jobs and reconciles server responses; metrics are never changed optimistically.
- Contract tests: invalid probability and agreement rejection; exact-day request
  keys and day navigation; fixture list loading/expansion; unavailable-forecast
  visibility; Go query/rating/agreement tests.

## Score bucket serialization

New forecast responses declare `compact-buckets-v2` and include labels and
`EXACT`/`AT_LEAST` kinds on both score axes. The numeric goal fields remain
bucket minima for compatibility. Historical responses declare
`legacy-compact-index-v1`; the frontend recognizes the approved Poisson model
versions and interprets index 5 as `5+`. Missing version metadata is accepted
only for those known historical algorithms. Unknown versions, inconsistent
labels, and non-integer minima fail at the transport boundary.

Exact-score grids use only `EXACT` cells. Category rankings and modals display
`5+` explicitly. Existing request cancellation, retry, and independent resource
states remain unchanged. Drift checks cover the JSON serialization schema,
OpenAPI fields, Go response metadata, and deterministic legacy/new/malformed
component fixtures in `fixture-explorer.test.tsx`.

## Provider history admin contract

Authority: Go `HistoricalCoverage` and `syncCoverageSQL` in `go/api/internal/app/admin_sync.go`.

The response adds required numeric `eligible_history`, `excluded_history`, `provisional_fixtures`, `verified_provider_matches`, and `identity_conflicts`. TypeScript validates all five at the existing transport boundary. Counts are not inferred from linked observations. Component and Playwright fixtures use the same fields; malformed metric coverage rejects null values rather than rendering zero.

No new frontend requests, optimistic mutations, loading policy, or cancellation behavior were introduced. Existing status polling, errors, retry, stop, and duplicate-submit protection remain in place. State coverage is recorded in `api-state-matrix.md`. Contract drift is checked by boundary tests, deterministic admin browser fixtures, Go tests, and the repository's normal type/build checks.

## Performance selection

Responses declare `pre-match-revisions-v2` and a fixed analytics horizon. The
transport rejects unknown policies and horizons. Each verified regulation-time
fixture contributes its latest eligible immutable pre-kickoff revision once.
Fixed horizons select by availability at the cutoff, independent of a revision's
stored horizon label. Query keys include the horizon. Score rankings describe
categories; aggregate buckets cannot count as exact scores.

## Remediation frontend states

Forecast history consumes the existing revision endpoint. The boundary validates
issue/cutoff timestamps, SHA-256 lineage, revision reasons and original probability
payloads through the shared bucket parser; it rejects a fixture mismatch. Current
and selected revision labels remain distinct, and selection changes only local
presentation. History has independent loading, empty, error and retry states.

Resources retain data only for the same request key. A changed date or filter
hides old results synchronously; cancellation and generation checks also reject
late completions. Date-bearing pages receive their initial configured civil day
from the server, and fixture day labels use explicit calendar names/punctuation.
Invalid or cleared selections preserve the last valid fixture request.

Admin controls mirror the existing bulk, FotMob and PitchAPI lanes. Requests
within one lane cannot overlap mutations; other lanes retain their controls.
Polling waits for completion before scheduling the next request, aborts superseded
reads, preserves terminal run states and retrieves active runs omitted from the
recent-list page. Cancellation/retry and errors remain lane-specific.

## Architecture V2 frontend cleanup

Normal components consume the existing MatchForge DTOs. Provider IDs, status
labels and original statistic names remain explicit provenance fields, rather
than provider-native objects or behavioral identity keys. Fixture groups reject
repeated canonical IDs across the entire response; separate canonical matches
with identical teams and kickoff remain separate. Both public fixture status
enums now match the existing SQL constraint, with a drift regression.

Single-resource requests bind decoded fixture, forecast and competition IDs to
their requested IDs. Required fixture, context, forecast and live-source clocks
use the existing timezone-aware timestamp validator. Form venues are validated
before becoming domain values. Untrusted HTTP error envelopes are checked as
unknown values and retain a status-based fallback.

Forecast requests depend on the immutable forecast ID and fixture ID, not the
summary object's reference. Polling can update a fixture without reloading the
same forecast. New revisions cancel old requests, and stale completions cannot
replace current data. Failed fixture refreshes display retained same-key rows
with an alert and retry; changed request keys still hide old rows immediately.
Context, live and forecast failures remain independent. Simulation evidence
stays explicitly unavailable because no approved linked artifact is exposed.

## Resolution Center, 31 October 2026

The new OpenAPI read route delegates to Python through the existing Go runner.
Admin page sizes remain 20, 50 and 100. Runtime checks reject inconsistent counts,
invalid groups, missing case keys, mismatched detail IDs and invalid evidence
hashes. A drift assertion binds client view names to OpenAPI. Transport disables
caching and forwards cancellation. No optimistic mutation or credential storage
is present in this phase.

Phase 4 adds bounded batch-preview/batch-apply routes (20 cases). Runtime guards bind every preview/event to its requested case and approved inputs, reject duplicate/missing result identities and verify per-case status totals. Owner credentials remain headers only.

Phase 5 case detail adds immutable recovery page receipts and current downstream queue counts for the latest recovery request. Shared generations may include later work; an empty queue is not an identity/parity PASS. The existing read route remains no-store and read-only.

## Live ordering metadata and score disagreements — V4 Phase 16

GET `/v1/fixtures/{id}/live` preserves the canonical score and independent incident
and statistics resources. `score_conflict` marks unresolved retained score claims;
the existing Live Match panel explains the warning and partial coverage. Source
provenance separates fetch freshness, original observation and optional provider
update time. `ordering_basis` is UNKNOWN, MATCH_CLOCK or PROVIDER_TIMESTAMP.
Missing legacy metadata becomes UNKNOWN; invalid enums, timestamps and booleans
fail the existing resource parser and local error/retry path. Existing fetch
cancellation and request keys are unchanged; no mutations or optimistic updates.
Deterministic contract/component tests exercise these states. The drift assertion
binds the new response fields and enum to OpenAPI and Go. Backend disposable tests
verify cached lower clocks, current/unknown-clock conflicts and canonical progress.

## V4 Phase 22 — market readiness

The Python read-only report now has a compact operator summary; full CLI output is unchanged unless --summary is requested. Go validates canonical scope, cutoff, non-authoritative/read-only envelope and bounds output to 2 MiB using the existing shared command buffer. The frontend checks every rendered field, model metadata completeness, semantic version, digests, status enums and exact scope/cutoff. OpenAPI/Go/Python and deterministic fixtures are verified; status drift ties the Python enum to the web and documented schema. The actual operating summary has 67 families, 53 DATA_COLLECTION_REQUIRED and 14 INSUFFICIENT_PLAYER_DATA, with no publication grant.
