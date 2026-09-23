# Football forecasting platform

## Project use

MatchForge is a private, non-commercial research project. It is not intended
for distribution or external publication.

Source selection does not require commercial-use or redistribution rights.
Private research use must still comply with provider access and usage terms,
attribution requirements, retention limits, rate limits, and restrictions on
automated or bulk acquisition. Third-party source data must not be published
unless its terms permit publication.

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
