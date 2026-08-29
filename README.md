# Football forecasting platform

Current phase: Sprint 1 production implementation, Phase 1 foundation.

Gate A passed. Phase 1 establishes the pinned macOS arm64 toolchain, local PostgreSQL and Redis services, production Python package boundary, Rust simulation-core boundary, and Go operational API scaffold. It does not implement production ingestion or forecasting.

```bash
make bootstrap
make doctor
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
