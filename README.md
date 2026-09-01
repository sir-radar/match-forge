# Football forecasting platform

Current phase: Sprint 2 forecasting baselines.

Gate A and Sprint 1 are complete. Sprint 2 implementation now includes versioned team Elo, Dixon–Coles goal products, Poisson/NB2 corner baselines, retained point-in-time walk-forward execution, paired bootstrap uncertainty, chronological calibration analysis, and immutable model governance. Sprint 2's phase gate intentionally remains `FAIL` pending review of the retained baseline evidence. See the [architecture](docs/architecture.md), [backtesting contract](docs/backtesting.md), [model governance](docs/model-governance.md), and [Sprint 2 phase gate](docs/sprint2-phase-gate.md). Simulation and 360 normalization remain deferred.

```bash
make bootstrap
make doctor
make migrate
make check
make integration
make sprint2-evaluate
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
