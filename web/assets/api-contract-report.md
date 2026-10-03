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
