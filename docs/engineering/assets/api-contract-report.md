# Admin data-sync API contract report

Canonical evidence is the Go handlers and tests, followed by `docs/api/openapi.yaml` and frontend boundary parsers.

- Starts: fixed `POST /v1/admin/sync/*` actions, optional JSON selectors, `202`, `409`, `500/503`.
- Reads: `GET /v1/admin/sync-runs` and `GET /v1/admin/sync-runs/{run_id}`.
- Persistence states: `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`.
- Concurrency: a partial unique index permits one queued/running job.
- Cancellation: browser reads accept `AbortSignal`; background subprocess lifetime is owned by the Go process, not the POST request.
- Drift gate: TypeScript parses every required field and enum; Go route tests and OpenAPI change with the same patch.
- Fixtures: component and Playwright tests use frozen timestamps, IDs, summaries, coverage, failures, and active states.
