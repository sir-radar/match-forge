#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export FOOTBALL_PROJECT_ROOT
. "$FOOTBALL_PROJECT_ROOT/scripts/toolchain.sh"
cd "$FOOTBALL_PROJECT_ROOT"

TEST_DATABASE="football_storage_test_$$"
DATABASE_CREATED=0

test_database_suffix=${TEST_DATABASE#football_storage_test_}
case "$test_database_suffix" in
	''|*[!0-9]*) printf 'Unsafe storage test database name: %s\n' "$TEST_DATABASE" >&2; exit 8 ;;
esac

cleanup() {
	if [ "$DATABASE_CREATED" -eq 1 ]; then
		docker compose exec -T postgres dropdb --if-exists --force -U "${POSTGRES_USER:-football}" "$TEST_DATABASE" >/dev/null
	fi
}

trap cleanup EXIT HUP INT TERM

docker compose exec -T postgres createdb -U "${POSTGRES_USER:-football}" "$TEST_DATABASE"
DATABASE_CREATED=1

TEST_DATABASE_URL="postgresql://${POSTGRES_USER:-football}:${POSTGRES_PASSWORD:-football-local-only}@127.0.0.1:${POSTGRES_PORT:-55433}/$TEST_DATABASE?sslmode=disable"
export TEST_DATABASE_URL

goose -dir infrastructure/migrations postgres "$TEST_DATABASE_URL" up
goose -dir infrastructure/migrations postgres "$TEST_DATABASE_URL" up
uv run pytest -q tests/integration/test_canonical_storage.py \
	tests/integration/test_canonical_ingestion.py \
	tests/integration/test_dependency_storage.py \
	tests/integration/test_f3_fixture_persistence.py \
	tests/integration/test_sprint1_fixtures.py \
	tests/integration/test_cli.py \
	tests/integration/test_postgres_recovery.py \
	tests/integration/test_team_elo.py

printf 'Fresh-database migration and canonical storage invariants passed\n'
