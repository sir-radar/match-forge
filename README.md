# Football forecasting platform

Current phase: Sprint 1 production implementation, Phase 10 ingestion reports.

Gate A passed. Phase 1 established the pinned toolchain and language boundaries. Phase 2 added canonical temporal storage. Phase 3 added commit-pinned immutable StatsBomb source acquisition. Phases 4 and 5 added canonical PostgreSQL ingestion. Phase 6 publishes schema-bound normalized event Parquet, immutable dataset manifests, and PostgreSQL dataset lineage. Phase 7 adds policy-driven dataset validation with immutable PostgreSQL runs and findings. Phase 8 adds checksum-pinned synthetic fixtures. Phase 9 exposes the production data pipeline through the `football` CLI. Phase 10 publishes deterministic JSON and Markdown ingestion reports with source, canonical, dataset, and quality evidence. The platform does not yet normalize 360 data or implement forecasting.

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
