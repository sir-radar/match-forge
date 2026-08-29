#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export FOOTBALL_PROJECT_ROOT
. "$FOOTBALL_PROJECT_ROOT/scripts/toolchain.sh"
cd "$FOOTBALL_PROJECT_ROOT"

pass() {
	printf '[doctor] PASS %-18s %s\n' "$1" "$2"
}

fail() {
	printf '[doctor] FAIL %-18s %s\n' "$1" "$2" >&2
	exit 3
}

expect_contains() {
	name=$1
	expected=$2
	shift 2
	actual=$("$@" 2>&1) || fail "$name" "$actual"
	case "$actual" in
		*"$expected"*) pass "$name" "$actual" ;;
		*) fail "$name" "expected '$expected', got '$actual'" ;;
	esac
}

[ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ] || fail host "expected Darwin arm64"
pass host "Darwin arm64"
expect_contains make "GNU Make" make --version
expect_contains uv "uv 0.12.1 " uv --version
expect_contains python "Python 3.13.14" uv run python --version
expect_contains rustc "rustc 1.97.1 " rustc --version
expect_contains cargo "cargo 1.97.1 " cargo --version
expect_contains rustfmt "rustfmt 1.9.0" rustfmt --version
expect_contains clippy "clippy 0.1.97" cargo clippy --version
expect_contains go "go version go1.27.0 darwin/arm64" go version
expect_contains goose "v3.27.1" goose --version
expect_contains golangci-lint "2.11.4" golangci-lint --version
expect_contains docker "Docker version" docker --version
expect_contains compose "Docker Compose version" docker compose version
docker info >/dev/null 2>&1 || fail engine "Docker engine unavailable"
pass engine "Docker engine reachable"
docker image inspect "postgres:18.6-bookworm@sha256:1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af" >/dev/null 2>&1 || fail postgres-image "pinned image missing"
pass postgres-image "18.6 pinned digest present"
docker image inspect "redis:8.10.0-alpine3.23@sha256:978f0e01593e65eed801f2402944efcd936d43b5027e4908a7897baf88ed6241" >/dev/null 2>&1 || fail redis-image "pinned image missing"
pass redis-image "8.10.0 pinned digest present"
running_services=$(docker compose ps --status running --services)
printf '%s\n' "$running_services" | grep -qx postgres || fail postgres-service "container is not running"
pass postgres-service "container running"
printf '%s\n' "$running_services" | grep -qx redis || fail redis-service "container is not running"
pass redis-service "container running"
postgres_probe=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-football}" -d "${POSTGRES_DB:-football}" -tAc 'SELECT 1') || fail postgres-probe "query failed"
[ "$postgres_probe" = 1 ] || fail postgres-probe "expected SELECT 1 result"
pass postgres-probe "SQL query succeeded"
redis_probe=$(docker compose exec -T redis redis-cli ping) || fail redis-probe "PING failed"
[ "$redis_probe" = PONG ] || fail redis-probe "expected PONG"
pass redis-probe "PING returned PONG"
uv lock --check >/dev/null 2>&1 || fail uv-lock "uv.lock is stale"
pass uv-lock "locked dependency graph current"
