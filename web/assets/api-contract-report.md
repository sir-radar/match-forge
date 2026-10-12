# API contract report

- Contract source: `docs/api/openapi.yaml` plus Go response types in `go/api/internal/app/product.go`.
- Frontend boundary: `web/lib/contracts.ts` validates objects, arrays, finite numbers, probabilities, enums used by controls, nullable values and source maps before rendering.
- Filters: continent, country, competition, division/forecast availability, date, source, market and agreement are passed explicitly.
- Daily predictions: `/predictions` sends one exact `date`; source metrics use
  the equivalent closed `date_from`/`date_to` range. Previous and next controls
  advance by one UTC day, and the renderer rejects off-day rows.
- Request safety: `useResource` aborts superseded requests, ignores stale completions, preserves previous data while refreshing and exposes retry.
- Partial failure: fixture, forecast, context and external-selection resources render independently. Missing context cannot hide a fixture or overwrite a forecast.
- Mutation/optimistic state: none. The MVP API is read-only.
- Contract tests: invalid probability and agreement rejection; exact-day request
  keys and day navigation; fixture list loading/expansion; unavailable-forecast
  visibility; Go query/rating/agreement tests.

## Provider history admin contract

Authority: Go `HistoricalCoverage` and `syncCoverageSQL` in `go/api/internal/app/admin_sync.go`.

The response adds required numeric `eligible_history`, `excluded_history`, `provisional_fixtures`, `verified_provider_matches`, and `identity_conflicts`. TypeScript validates all five at the existing transport boundary. Counts are not inferred from linked observations. Component and Playwright fixtures use the same fields; malformed metric coverage rejects null values rather than rendering zero.

No new frontend requests, optimistic mutations, loading policy, or cancellation behavior were introduced. Existing status polling, errors, retry, stop, and duplicate-submit protection remain in place. State coverage is recorded in `api-state-matrix.md`. Contract drift is checked by boundary tests, deterministic admin browser fixtures, Go tests, and the repository's normal type/build checks.
