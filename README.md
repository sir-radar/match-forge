# Football forecasting platform

Current phase: Sprint 1 production implementation, Phase 3 source acquisition.

Gate A passed. Phase 1 established the pinned toolchain and language boundaries. Phase 2 added canonical temporal storage. Phase 3 adds the provider protocol, a commit-pinned StatsBomb Open Data adapter, exact-byte raw preservation, deterministic source manifests, offline idempotency, and interrupted-run recovery. It does not yet parse or normalize provider data, register acquired resources in PostgreSQL, publish Parquet, generate quality reports, or implement forecasting.

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
