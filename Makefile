SHELL := /bin/sh

UV := .tools/bin/uv
PROTOTYPE_DIR := experiments/sprint1_roundtrip
PROTOTYPE_COMPOSE := $(PROTOTYPE_DIR)/compose.yaml
export UV_CACHE_DIR := $(CURDIR)/.local/uv-cache

.PHONY: prototype-bootstrap prototype-up prototype-down prototype-test prototype-run prototype-gate-a prototype-clean

prototype-bootstrap:
	@test -x $(UV) || { echo "missing $(UV); install uv 0.12.1" >&2; exit 3; }
	$(UV) python install 3.13.14
	$(UV) sync --locked

prototype-up:
	docker compose -f $(PROTOTYPE_COMPOSE) up -d --wait

prototype-down:
	docker compose -f $(PROTOTYPE_COMPOSE) down

prototype-test:
	$(UV) run pytest

prototype-run:
	$(UV) run python -m experiments.sprint1_roundtrip.cli run

prototype-gate-a: prototype-up prototype-test prototype-run

prototype-clean:
	$(UV) run python -m experiments.sprint1_roundtrip.cli clean
