# Football forecasting platform

Current phase: Sprint 1 production implementation, Phase 5 event catalogue ingestion.

Gate A passed. Phase 1 established the pinned toolchain and language boundaries. Phase 2 added canonical temporal storage. Phase 3 added commit-pinned immutable StatsBomb source acquisition. Phases 4 and 5 re-verify and register source manifests and resources in PostgreSQL, then atomically ingest canonical competitions, seasons, teams, players, matches, lineups, and the lightweight event catalogue with provider mappings and point-in-time observation history. The platform does not yet publish Parquet, generate quality reports, expose the ingestion CLI, or implement forecasting.

```bash
make bootstrap
make doctor
make migrate
make check
make integration
```

The Go scaffold exposes `GET /healthz`, `GET /readyz`, and `GET /version`. Run it after `make up` with:

```bash
. ./scripts/toolchain.sh
cd go/api
go run ./cmd/api
```

The disposable Gate A prototype remains reproducible:

```bash
make prototype-gate-a
```

Runtime data is written beneath `.local/prototype/sprint1-roundtrip/` and is excluded from Git.
