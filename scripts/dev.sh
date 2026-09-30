#!/bin/sh
set -eu

. ./scripts/toolchain.sh

if [ -f .env ]; then
	set -a
	. ./.env
	set +a
fi

cleanup() {
	kill "${MATCHFORGE_API_PID:-}" "${MATCHFORGE_WEB_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(cd go/api && go run ./cmd/api) &
MATCHFORGE_API_PID=$!
(cd web && pnpm dev) &
MATCHFORGE_WEB_PID=$!

echo "MatchForge API: http://127.0.0.1:8080"
echo "MatchForge web: http://127.0.0.1:3000"
wait
