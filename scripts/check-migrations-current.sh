#!/bin/sh
# Refuse to continue when DATABASE_URL has pending Goose migrations.
#
# Dev and sync targets call this instead of applying migrations. Applying
# migrations to the operating database is a deliberate step: run
# `make migrate` only when the current owner decision authorizes it.
set -eu

migrations_dir=${1:?usage: check-migrations-current.sh MIGRATIONS_DIR}
: "${DATABASE_URL:?Set DATABASE_URL in .env}"

# Goose prints the status table on stderr.
if ! status=$(goose -dir "$migrations_dir" postgres "$DATABASE_URL" status 2>&1); then
	printf '%s\n' "$status" >&2
	echo "error: could not read migration status for DATABASE_URL." >&2
	exit 1
fi

pending=$(printf '%s\n' "$status" | grep -E 'Pending[[:space:]]+--' || true)
if [ -n "$pending" ]; then
	{
		echo "error: DATABASE_URL has pending migrations; refusing to start."
		printf '%s\n' "$pending"
		echo
		echo "This target no longer applies migrations. Applying them to the operating"
		echo "database needs an owner decision. When it is authorized, run:"
		echo
		echo "    make migrate"
		echo
		echo "Inspect the state with: make migration-status"
	} >&2
	exit 1
fi
