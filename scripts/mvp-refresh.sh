#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
if [ -f .env ]; then
	set -a
	. ./.env
	set +a
fi

sync_status=0
collection_status=0
make mvp-sync || sync_status=$?
make external-predictions || collection_status=$?
printf 'MVP refresh: sync_exit=%s collection_exit=%s\n' "$sync_status" "$collection_status"
[ "$sync_status" -eq 0 ] && [ "$collection_status" -eq 0 ]
