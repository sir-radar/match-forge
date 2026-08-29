#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$FOOTBALL_PROJECT_ROOT"

API_ADDRESS=127.0.0.1:58080
API_LOG="$FOOTBALL_PROJECT_ROOT/.local/integration-api.log"
API_PID=

cleanup() {
	if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
		kill -TERM "$API_PID" 2>/dev/null || true
		wait "$API_PID" 2>/dev/null || true
	fi
}

trap cleanup EXIT HUP INT TERM

postgres_result=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-football}" -d "${POSTGRES_DB:-football}" -tAc 'SELECT 1')
[ "$postgres_result" = 1 ] || { printf 'PostgreSQL integration check failed\n' >&2; exit 8; }

redis_result=$(docker compose exec -T redis redis-cli ping)
[ "$redis_result" = PONG ] || { printf 'Redis integration check failed\n' >&2; exit 8; }

API_ADDR="$API_ADDRESS" "$FOOTBALL_PROJECT_ROOT/.local/bin/football-api" >"$API_LOG" 2>&1 &
API_PID=$!

attempt=0
while ! curl --fail --silent "http://$API_ADDRESS/healthz" >/dev/null 2>&1; do
	attempt=$((attempt + 1))
	if [ "$attempt" -ge 30 ] || ! kill -0 "$API_PID" 2>/dev/null; then
		printf 'Go API failed to start:\n' >&2
		sed -n '1,120p' "$API_LOG" >&2
		exit 8
	fi
	sleep 0.2
done

health_result=$(curl --fail --silent "http://$API_ADDRESS/healthz")
ready_result=$(curl --fail --silent "http://$API_ADDRESS/readyz")
version_result=$(curl --fail --silent "http://$API_ADDRESS/version")
[ "$health_result" = '{"status":"ok"}' ] || { printf 'Go API health contract failed\n' >&2; exit 8; }
[ "$ready_result" = '{"status":"ready"}' ] || { printf 'Go API readiness contract failed\n' >&2; exit 8; }
[ "$version_result" = '{"version":"dev"}' ] || { printf 'Go API version contract failed\n' >&2; exit 8; }

kill -TERM "$API_PID"
wait "$API_PID"
API_PID=

printf 'PostgreSQL 18.6, Redis 8.10, and Go operational API integration checks passed\n'
