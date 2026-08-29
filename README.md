# Football forecasting platform

Current phase: Sprint 1 complete and validated.

Gate A passed. Sprint 1 now provides pinned toolchains, canonical temporal storage, commit-pinned immutable StatsBomb acquisition, canonical PostgreSQL ingestion, normalized event Parquet, dataset lineage, policy-driven validation, deterministic fixtures, production CLI commands, and immutable JSON/Markdown ingestion reports. See the [Sprint 1 architecture](docs/architecture.md). Forecasting, simulation, and 360 normalization remain deferred.

```bash
make bootstrap
make doctor
make migrate
make check
make integration
```

See [CLI usage](docs/cli.md) for data-pipeline commands and configuration.

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
