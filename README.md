# Football forecasting platform

Current phase: Sprint 2 forecasting baselines.

Gate A and Sprint 1 are complete. Sprint 2 now includes versioned team Elo and a time-weighted Dixon–Coles goal model with score matrices and market probabilities. See the [Sprint 1 architecture](docs/architecture.md), [team Elo baseline](docs/team-elo.md), and [Dixon–Coles goal baseline](docs/dixon-coles.md). Corner models, walk-forward evaluation, calibration, simulation, and 360 normalization remain deferred.

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
