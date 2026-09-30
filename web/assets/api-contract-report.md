# API contract report

- Contract source: `docs/api/openapi.yaml` plus Go response types in `go/api/internal/app/product.go`.
- Frontend boundary: `web/lib/contracts.ts` validates objects, arrays, finite numbers, probabilities, enums used by controls, nullable values and source maps before rendering.
- Filters: continent, country, competition, division/forecast availability, date, source, market and agreement are passed explicitly.
- Request safety: `useResource` aborts superseded requests, ignores stale completions, preserves previous data while refreshing and exposes retry.
- Partial failure: fixture, forecast, context and external-selection resources render independently. Missing context cannot hide a fixture or overwrite a forecast.
- Mutation/optimistic state: none. The MVP API is read-only.
- Contract tests: invalid probability rejection; fixture list loading/expansion; unavailable-forecast visibility; Go query/rating/agreement tests.
