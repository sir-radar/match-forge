#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$FOOTBALL_PROJECT_ROOT"

[ -f .env ] || { printf 'Missing .env\n' >&2; exit 8; }
set -a
. ./.env
set +a
: "${POSTGRES_USER:?Set POSTGRES_USER in .env}"
: "${POSTGRES_DB:?Set POSTGRES_DB in .env}"
: "${DATABASE_URL:?Set DATABASE_URL in .env}"

API_LOG=$(mktemp "$FOOTBALL_PROJECT_ROOT/.local/integration-api.XXXXXX")
API_PID=
API_TEST_DATABASE="football_api_test_$$"
API_DATABASE_CREATED=0

cleanup() {
	if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
		kill -TERM "$API_PID" 2>/dev/null || true
		wait "$API_PID" 2>/dev/null || true
	fi
	if [ "$API_DATABASE_CREATED" -eq 1 ]; then
		docker compose exec -T postgres dropdb --if-exists --force -U "$POSTGRES_USER" "$API_TEST_DATABASE" >/dev/null
	fi
	rm -f "$API_LOG"
}

trap cleanup EXIT HUP INT TERM

postgres_result=$(docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc 'SELECT 1')
[ "$postgres_result" = 1 ] || { printf 'PostgreSQL integration check failed\n' >&2; exit 8; }

redis_result=$(docker compose exec -T redis redis-cli ping)
[ "$redis_result" = PONG ] || { printf 'Redis integration check failed\n' >&2; exit 8; }

docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$API_TEST_DATABASE"
API_DATABASE_CREATED=1
export API_TEST_DATABASE
. "$FOOTBALL_PROJECT_ROOT/scripts/toolchain.sh"
API_TEST_DATABASE_URL=$(uv run python -c 'import os; from psycopg.conninfo import make_conninfo; print(make_conninfo(os.environ["DATABASE_URL"], dbname=os.environ["API_TEST_DATABASE"]))' )
isolation_exports=$(MATCHFORGE_TEST_OWNER_PID=$$ uv run python -m tests.integration.database_isolation prepare "$API_TEST_DATABASE_URL" "$DATABASE_URL")
set -a
eval "$isolation_exports"
set +a
goose -dir infrastructure/migrations postgres "$API_TEST_DATABASE_URL" up
TEST_DATABASE_URL="$API_TEST_DATABASE_URL" DATABASE_URL="$API_TEST_DATABASE_URL" \
	uv run python -m tests.integration.database_isolation verify

(
	cd "$FOOTBALL_PROJECT_ROOT/go/api"
	TEST_DATABASE_URL="$API_TEST_DATABASE_URL" go test ./internal/app -run '^(TestServingDatabaseFixtureHTTPFiltersUnknownSeasons|TestServingDatabaseFixtureScoreBasis|TestUnknownSeasonFixtureRepairRequiresUniqueExactProviderIdentity)$'
)

MATCHFORGE_OPERATIONAL_SYNC_INTERVAL=0 MATCHFORGE_HISTORY_SYNC_ENABLED=false \
    MATCHFORGE_STORAGE_POLICY= DATABASE_URL="$API_TEST_DATABASE_URL" API_ADDR=127.0.0.1:0 \
    "$FOOTBALL_PROJECT_ROOT/.local/bin/football-api" >"$API_LOG" 2>&1 &
API_PID=$!

attempt=0
while :; do
	API_ADDRESS=$(sed -n 's/.*"msg":"api listening","address":"\(127\.0\.0\.1:[0-9][0-9]*\)".*/\1/p' "$API_LOG")
	if [ -n "$API_ADDRESS" ] && curl --fail --silent "http://$API_ADDRESS/healthz" >/dev/null 2>&1; then
		break
	fi
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
export version_result
uv run python -c 'import json,os,re; v=json.loads(os.environ["version_result"]); assert v["version"]=="dev"; assert re.fullmatch("[0-9a-f]{40}",v["code_commit_sha"]); assert re.fullmatch("[0-9a-f]{64}",v["dependency_lock_sha256"]); assert v["worktree_state"] in ("clean","dirty")'

kill -TERM "$API_PID"
wait "$API_PID"
API_PID=

printf 'PostgreSQL 18.6, Redis 8.10, and Go operational API integration checks passed\n'
