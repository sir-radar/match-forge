SHELL := /bin/sh

UV := .tools/bin/uv
TOOL_ENV := . ./scripts/toolchain.sh
PROTOTYPE_DIR := experiments/sprint1_roundtrip
PROTOTYPE_COMPOSE := $(PROTOTYPE_DIR)/compose.yaml
MIGRATIONS_DIR := infrastructure/migrations
SPRINT2_REPORT_ROOT ?= $(CURDIR)/.local/reports/sprint2
CODE_COMMIT_SHA ?= $(shell git rev-parse HEAD)
DEPENDENCY_LOCK_SHA256 ?= $(shell shasum -a 256 uv.lock | cut -d ' ' -f 1)
export UV_CACHE_DIR := $(CURDIR)/.local/uv-cache

.PHONY: bootstrap doctor up down clean migrate migration-status format format-check lint test test-coverage build integration check project-status-check identity-check entity-crosswalk-review entity-crosswalk-apply pretraining-snapshot-check pretraining-check postgres-restore-test sprint2-evaluate h2h-context-evaluate model-fit model-forecast model-evaluate probability-benchmark dev mvp-sync openfootball-sync football-data-uk-sync history-backfill forecast-refresh all-data-sync external-predictions web-install web-lint web-test web-build web-e2e \
	prototype-bootstrap prototype-up prototype-down prototype-test prototype-run \
	prototype-gate-a prototype-clean codex-luna codex-terra codex-sol

bootstrap:
	./scripts/bootstrap.sh

doctor:
	./scripts/doctor.sh

up:
	docker compose up -d --wait

down:
	docker compose down

clean:
	docker compose down --volumes

migrate: up
	@set -a; . ./.env; set +a; $(TOOL_ENV); : "$${DATABASE_URL:?Set DATABASE_URL in .env}"; goose -dir $(MIGRATIONS_DIR) postgres "$$DATABASE_URL" up

migration-status: up
	@set -a; . ./.env; set +a; $(TOOL_ENV); : "$${DATABASE_URL:?Set DATABASE_URL in .env}"; goose -dir $(MIGRATIONS_DIR) postgres "$$DATABASE_URL" status

format:
	@$(TOOL_ENV); uv run ruff check --fix python tests experiments
	@$(TOOL_ENV); uv run ruff format python tests experiments
	@$(TOOL_ENV); cargo fmt --all
	@$(TOOL_ENV); find go -type f -name '*.go' -exec gofmt -w {} +

format-check:
	@$(TOOL_ENV); uv run ruff format --check python tests experiments
	@$(TOOL_ENV); cargo fmt --all --check
	@$(TOOL_ENV); test -z "$$(find go -type f -name '*.go' -exec gofmt -l {} +)"

lint:
	@$(TOOL_ENV); uv run ruff check python tests experiments
	@$(TOOL_ENV); uv run mypy
	@$(TOOL_ENV); cargo clippy --workspace --all-targets --all-features -- -D warnings
	@$(TOOL_ENV); cd go/api && go vet ./...
	@$(TOOL_ENV); cd go/api && golangci-lint run ./...
	@$(TOOL_ENV); goose -dir $(MIGRATIONS_DIR) validate
	@sh -n scripts/bootstrap.sh scripts/doctor.sh scripts/integration.sh scripts/storage-integration.sh scripts/toolchain.sh

test:
	@$(TOOL_ENV); uv run pytest --ignore=tests/integration
	@$(TOOL_ENV); cargo test --workspace --all-targets --all-features
	@$(TOOL_ENV); cd go/api && go test ./...

test-coverage:
	@$(TOOL_ENV); uv run coverage run --branch -m pytest --ignore=tests/integration
	@$(TOOL_ENV); uv run coverage report

build:
	@mkdir -p .local/dist .local/bin
	@$(TOOL_ENV); UV_CACHE_DIR="$${TMPDIR:-/tmp}/football-forecasting-uv-build-cache" uv build --no-build-isolation --out-dir .local/dist
	@$(TOOL_ENV); cargo build --workspace --all-targets --all-features
	@$(TOOL_ENV); cd go/api && go build -o $(CURDIR)/.local/bin/football-api ./cmd/api

integration: build
	docker compose up -d --wait
	./scripts/storage-integration.sh
	./scripts/integration.sh

postgres-restore-test: up
	./scripts/storage-integration.sh

check: format-check lint test build project-status-check web-lint web-test web-build

project-status-check:
	@$(TOOL_ENV); uv run python -m football.project_status docs/project-status.json

identity-check: migrate
	@set -a; . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.identity_audit --database-url "$$DATABASE_URL"

entity-crosswalk-review: migrate
	@set -a; . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.crosswalk_resolution --database-url "$$DATABASE_URL"

entity-crosswalk-apply: migrate
	@set -a; . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.crosswalk_resolution --database-url "$$DATABASE_URL" --apply

pretraining-snapshot-check:
	@$(TOOL_ENV); uv run python scripts/verify_pretraining_snapshot.py $(if $(SNAPSHOT_ROOT),--root "$(SNAPSHOT_ROOT)",) $(if $(RESTORE_TO),--restore-to "$(RESTORE_TO)",)

pretraining-check: project-status-check identity-check pretraining-snapshot-check test-coverage

sprint2-evaluate: up
	@test -z "$$(git status --porcelain)" || { echo "Sprint 2 evaluation requires a clean worktree" >&2; exit 2; }
	@set -a; . ./.env; set +a; $(TOOL_ENV); : "$${DATABASE_URL:?Set DATABASE_URL in .env}"; uv run football --database-url "$$DATABASE_URL" --data-root "$(CURDIR)/.local/football-data" --report-root "$(SPRINT2_REPORT_ROOT)" --code-commit-sha "$(CODE_COMMIT_SHA)" --dependency-lock-sha256 "$(DEPENDENCY_LOCK_SHA256)" --authoritative-worktree-clean evaluate sprint2

h2h-context-evaluate:
	@$(TOOL_ENV); uv run python -m scripts.run_h2h_incremental_signal_research

model-fit:
	@$(TOOL_ENV); uv run football models fit --model-id "$(MODEL_ID)" --training-data "$(TRAINING_DATA)" --config "$(MODEL_CONFIG)" --artifact-root "$(ARTIFACT_ROOT)"

model-forecast:
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run football models forecast --manifest "$(MODEL_MANIFEST)" --snapshot "$(FORECAST_SNAPSHOT)" $(if $(PERSIST),--persist,)

model-evaluate:
	@$(TOOL_ENV); uv run football models evaluate --observations "$(MODEL_OBSERVATIONS)"

probability-benchmark:
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run football benchmarks collect --provider "$(BENCHMARK_PROVIDER)" --provider-fixture-id "$(PROVIDER_FIXTURE_ID)"

prototype-bootstrap:
	@test -x $(UV) || { echo "missing $(UV); run make bootstrap" >&2; exit 3; }
	$(UV) python install 3.13.14
	$(UV) sync --locked

prototype-up:
	docker compose --env-file .env -f $(PROTOTYPE_COMPOSE) up -d --wait

prototype-down:
	docker compose --env-file .env -f $(PROTOTYPE_COMPOSE) down

prototype-test:
	$(UV) run pytest tests/test_gate_a_contracts.py tests/test_gate_a_core.py

prototype-run:
	$(UV) run python -m experiments.sprint1_roundtrip.cli run

prototype-gate-a: prototype-up prototype-test prototype-run

prototype-clean:
	$(UV) run python -m experiments.sprint1_roundtrip.cli clean

codex-luna:
	codex -m gpt-5.6-luna

codex-terra:
	codex -m gpt-5.6-terra

codex-sol:
	codex -m gpt-5.6-sol

web-install:
	cd web && pnpm install --frozen-lockfile

web-lint:
	cd web && pnpm lint && pnpm typecheck

web-test:
	cd web && pnpm test

web-build:
	cd web && pnpm build

web-e2e: web-build
	cd web && pnpm test:e2e

mvp-sync: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli sync $(if $(DATE),--date $(DATE),) $(if $(FROM_DATE),--from-date $(FROM_DATE),) $(if $(HISTORY_CONCURRENCY),--history-concurrency $(HISTORY_CONCURRENCY),)

openfootball-sync: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli backfill-openfootball $(if $(SEASON),--season $(SEASON),) $(if $(COMPETITION),--competition "$(COMPETITION)",) $(if $(COUNTRY),--country "$(COUNTRY)",) $(if $(REFRESH),--refresh,)

football-data-uk-sync: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli backfill-football-data-uk $(if $(SEASON),--season $(SEASON),) $(if $(COMPETITION),--competition "$(COMPETITION)",) $(if $(COUNTRY),--country "$(COUNTRY)",) $(if $(REFRESH),--refresh,)

history-backfill: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli backfill-history $(if $(SEASON),--season $(SEASON),) $(if $(COMPETITION),--competition "$(COMPETITION)",) $(if $(COUNTRY),--country "$(COUNTRY)",) $(if $(REFRESH),--refresh,)

forecast-refresh: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli refresh-forecasts

all-data-sync: migrate
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli sync-all $(if $(DATE),--date $(DATE),) $(if $(FROM_DATE),--from-date $(FROM_DATE),) $(if $(HISTORY_CONCURRENCY),--history-concurrency $(HISTORY_CONCURRENCY),)

external-predictions:
	@set -a; test ! -f .env || . ./.env; set +a; $(TOOL_ENV); uv run python -m football.product.cli external-predictions $(if $(DATE),--date $(DATE),) $(if $(SOURCE),--source $(SOURCE),)

dev: migrate
	./scripts/dev.sh
