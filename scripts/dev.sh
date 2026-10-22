#!/bin/sh
set -eu

. ./scripts/toolchain.sh

if [ -f .env ]; then
	set -a
	. ./.env
	set +a
fi

(uv run --locked python scripts/dev_watch.py \
	--watch go/api --suffix .go --suffix go.mod --suffix go.sum \
	--cwd go/api -- go run ./cmd/api) &
MATCHFORGE_API_PID=$!
(cd web && pnpm dev) &
MATCHFORGE_WEB_PID=$!

MATCHFORGE_DEV_PIDS="$MATCHFORGE_API_PID $MATCHFORGE_WEB_PID"
if [ -n "${MATCHFORGE_PYTHON_COMMAND:-}" ]; then
	uv run --locked python scripts/dev_watch.py \
		--watch python/football/src --watch scripts \
		--suffix .py --suffix pyproject.toml --suffix uv.lock \
		--command-env MATCHFORGE_PYTHON_COMMAND &
	MATCHFORGE_DEV_PIDS="$MATCHFORGE_DEV_PIDS $!"
fi
if [ -n "${MATCHFORGE_RUST_COMMAND:-}" ]; then
	uv run --locked python scripts/dev_watch.py \
		--watch rust --watch Cargo.toml --watch Cargo.lock \
		--suffix .rs --suffix Cargo.toml --suffix Cargo.lock \
		--command-env MATCHFORGE_RUST_COMMAND &
	MATCHFORGE_DEV_PIDS="$MATCHFORGE_DEV_PIDS $!"
fi

cleanup() {
	trap - EXIT INT TERM
	for pid in $MATCHFORGE_DEV_PIDS; do
		kill -TERM "$pid" 2>/dev/null || true
	done
	for pid in $MATCHFORGE_DEV_PIDS; do
		wait "$pid" 2>/dev/null || true
	done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "MatchForge API: http://127.0.0.1:8080"
echo "MatchForge web: http://127.0.0.1:3000"
wait
