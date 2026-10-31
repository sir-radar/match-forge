# Football forecasting platform

## Project use

MatchForge is a private, non-commercial research project. It is not intended
for distribution or external publication.

Source selection does not require commercial-use or redistribution rights.
Private research use must still comply with provider access and usage terms,
attribution requirements, retention limits, rate limits, and restrictions on
automated or bulk acquisition. Third-party source data must not be published
unless its terms permit publication.

Current status: MVP implementation complete; live settlement evidence pending. Model research remains paused; prior gate and research results remain unchanged.

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

## MVP product

Copy `.env.example` to `.env`, set the required PostgreSQL, Redis, and `DATABASE_URL`
values and the credentials for the providers you enable. Bootstrap tools, apply
the serving schema, then start the Go API and Next.js frontend:

```bash
make bootstrap
make migrate
make dev
```

The web app is served at `http://127.0.0.1:3000` and the API at `http://127.0.0.1:8080`.

`make dev` restarts the Go API when Go sources or module files change; Next.js
provides React Fast Refresh. Python and Rust are batch/library code in this
repository, so they do not start a background server by default. To restart a
long-running local Python or Rust development command on source changes, pass it
to `make dev`:

```bash
make dev PYTHON_COMMAND='uv run python -m your_long_running_module' \
  RUST_COMMAND='cargo run -p simulation-core --bin your_dev_binary'
```

The Python and Rust commands are optional and are restarted as separate
processes. `make dev-python` and `make dev-rust` run those watchers on their own;
set the corresponding `MATCHFORGE_PYTHON_COMMAND` or
`MATCHFORGE_RUST_COMMAND` environment variable. These commands should run a local
development process; one-shot data sync and mutation commands are not suitable
for automatic restarts. The watcher uses Python's standard library and adds no
runtime dependency.

Populate a requested fixture date with:

```bash
make mvp-sync DATE=YYYY-MM-DD
make mvp-sync FROM_DATE=YYYY-MM-DD DATE=YYYY-MM-DD
make external-predictions DATE=YYYY-MM-DD
```

The second command collects public predictions from the four enabled sources when
`EXTERNAL_PREDICTION_USAGE_MODE=PRIVATE_LOCAL`. Use `SOURCE=<source>` to run one source.
Forebet remains disabled because an ordinary request receives a managed anti-bot response.
`infrastructure/systemd/matchforge-mvp-refresh.timer` provides the 06:00 `Africa/Lagos`
deployment schedule and invokes `scripts/mvp-refresh.sh`. Each fixture sync refreshes the
requested date and previous date so completed scores settle on the next scheduled run. Set
`FROM_DATE` for an inclusive fixture and score backfill through `DATE`; adjust the timer's `/opt/matchforge`
user/path settings during installation. No unnecessary realtime scheduler is bundled.

The Go service also exposes `GET /healthz`, `GET /readyz`, and `GET /version`. Readiness checks the serving PostgreSQL pool, schema through migration
`202610130600`, and Redis PING; liveness remains independent. Run it separately
after `make migrate`:

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
