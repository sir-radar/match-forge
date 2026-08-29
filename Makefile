SHELL := /bin/sh

UV := .tools/bin/uv
TOOL_ENV := . ./scripts/toolchain.sh
PROTOTYPE_DIR := experiments/sprint1_roundtrip
PROTOTYPE_COMPOSE := $(PROTOTYPE_DIR)/compose.yaml
export UV_CACHE_DIR := $(CURDIR)/.local/uv-cache

.PHONY: bootstrap doctor up down clean format format-check lint test build integration check \
	prototype-bootstrap prototype-up prototype-down prototype-test prototype-run \
	prototype-gate-a prototype-clean

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
	@sh -n scripts/bootstrap.sh scripts/doctor.sh scripts/integration.sh scripts/toolchain.sh

test:
	@$(TOOL_ENV); uv run pytest
	@$(TOOL_ENV); cargo test --workspace --all-targets --all-features
	@$(TOOL_ENV); cd go/api && go test ./...

build:
	@mkdir -p .local/dist .local/bin
	@$(TOOL_ENV); UV_CACHE_DIR="$${TMPDIR:-/tmp}/football-forecasting-uv-build-cache" uv build --no-build-isolation --out-dir .local/dist
	@$(TOOL_ENV); cargo build --workspace --all-targets --all-features
	@$(TOOL_ENV); cd go/api && go build -o $(CURDIR)/.local/bin/football-api ./cmd/api

integration: build
	docker compose up -d --wait
	./scripts/integration.sh

check: format-check lint test build

prototype-bootstrap:
	@test -x $(UV) || { echo "missing $(UV); run make bootstrap" >&2; exit 3; }
	$(UV) python install 3.13.14
	$(UV) sync --locked

prototype-up:
	docker compose -f $(PROTOTYPE_COMPOSE) up -d --wait

prototype-down:
	docker compose -f $(PROTOTYPE_COMPOSE) down

prototype-test:
	$(UV) run pytest tests/test_gate_a_contracts.py tests/test_gate_a_core.py

prototype-run:
	$(UV) run python -m experiments.sprint1_roundtrip.cli run

prototype-gate-a: prototype-up prototype-test prototype-run

prototype-clean:
	$(UV) run python -m experiments.sprint1_roundtrip.cli clean
