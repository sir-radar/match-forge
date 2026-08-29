# Football forecasting platform

Current phase: Sprint 1 production implementation, Phase 2 canonical storage.

Gate A passed. Phase 1 established the pinned toolchain and language boundaries. Phase 2 adds forward-only Goose migrations for source lineage, canonical identity, provider mappings, bitemporal observations, lineups, and the lightweight event catalogue. It does not implement source acquisition, full ingestion orchestration, Parquet publication, or forecasting.

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
