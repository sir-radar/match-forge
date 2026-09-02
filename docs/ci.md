# Continuous integration

`.github/workflows/ci.yml` is the required pull-request check. It runs the repository's
deterministic checks and the Docker-backed integration suite on `ubuntu-24.04`.

The workflow installs the versions owned by the repository toolchain contract:

```text
uv 0.12.1
Python 3.13.14
Go 1.27.0
Rust 1.97.1
goose 3.27.1
golangci-lint 2.11.4
```

`make check` covers formatting, Ruff, strict MyPy, Rust checks, Go vet/lint, migration validation,
unit tests, and builds. `make integration` covers PostgreSQL/Redis, migrations, canonical storage,
ingestion, CLI, and Go API integration tests. `git diff --check` is run separately.

The authoritative `make sprint2-evaluate` run remains separate from every pull-request check.
This CI gate does not change the retained Sprint 2 `FAIL` or authorize Phase 3.
