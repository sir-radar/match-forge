#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export FOOTBALL_PROJECT_ROOT
. "$FOOTBALL_PROJECT_ROOT/scripts/toolchain.sh"
cd "$FOOTBALL_PROJECT_ROOT"

shard=${INTEGRATION_SHARD:-all}
case "$shard" in
	all|storage|browser) ;;
	*) printf 'Unknown integration shard: %s\n' "$shard" >&2; exit 8 ;;
esac

set --
while read -r group test_file; do
	case "$group" in
		storage|browser) ;;
		*) printf 'Unknown integration test group: %s\n' "$group" >&2; exit 8 ;;
	esac
	if [ "$shard" = all ] || [ "$shard" = "$group" ]; then
		set -- "$@" "$test_file"
	fi
done < scripts/storage-integration-tests.txt
[ "$#" -gt 0 ] || { printf 'Integration shard is empty: %s\n' "$shard" >&2; exit 8; }

[ -f .env ] || { printf 'Missing .env\n' >&2; exit 8; }
set -a
. ./.env
set +a
: "${POSTGRES_USER:?Set POSTGRES_USER in .env}"
: "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
: "${POSTGRES_PORT:?Set POSTGRES_PORT in .env}"

TEST_DATABASE="football_storage_test_$$"
DATABASE_CREATED=0
TEST_DATA_ROOT=

test_database_suffix=${TEST_DATABASE#football_storage_test_}
case "$test_database_suffix" in
	''|*[!0-9]*) printf 'Unsafe storage test database name: %s\n' "$TEST_DATABASE" >&2; exit 8 ;;
esac

cleanup() {
	# Drop databases tests created but an interrupted run never dropped, then the run's own.
	if [ -n "${MATCHFORGE_DISPOSABLE_DATABASE_TOKEN:-}" ]; then
		uv run python -m tests.integration.database_isolation sweep "$TEST_DATABASE_URL" || true
	fi
	if [ "$DATABASE_CREATED" -eq 1 ]; then
		docker compose exec -T postgres dropdb --if-exists --force -U "$POSTGRES_USER" "$TEST_DATABASE" >/dev/null 2>&1
	fi
	if [ -n "$TEST_DATA_ROOT" ]; then
		rm -rf "$TEST_DATA_ROOT"
	fi
}

trap cleanup EXIT HUP INT TERM

docker compose exec -T postgres createdb -U "$POSTGRES_USER" "$TEST_DATABASE"
DATABASE_CREATED=1
TEST_DATA_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/matchforge-storage-test.XXXXXX")

TEST_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/$TEST_DATABASE?sslmode=disable"
export TEST_DATABASE_URL

# Mark the new database disposable for this run and record the cluster's protected
# identities. Every test connection is then checked by stable identity, not by name.
isolation_exports=$(uv run python -m tests.integration.database_isolation prepare "$TEST_DATABASE_URL" "${DATABASE_URL:-}")
set -a
eval "$isolation_exports"
set +a
DATABASE_URL="$TEST_DATABASE_URL"
export DATABASE_URL

goose -dir infrastructure/migrations postgres "$TEST_DATABASE_URL" up
goose -dir infrastructure/migrations postgres "$TEST_DATABASE_URL" up
DATABASE_URL="$TEST_DATABASE_URL" FOOTBALL_DATA_ROOT="$TEST_DATA_ROOT" \
uv run pytest -q "$@"

uv run python -m tests.integration.database_isolation verify
if [ "$shard" != browser ]; then
	(cd go/api && go test ./internal/storage ./internal/app -run "TestDatabase|TestStorageDatabase|TestStorageAdmin")
fi

printf 'Fresh-database migration and canonical storage invariants passed\n'
