#!/bin/sh

set -eu

FOOTBALL_PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export FOOTBALL_PROJECT_ROOT
. "$FOOTBALL_PROJECT_ROOT/scripts/toolchain.sh"
cd "$FOOTBALL_PROJECT_ROOT"

UV_VERSION=0.12.1
PYTHON_VERSION=3.13.14
RUST_TOOLCHAIN=1.97.1-aarch64-apple-darwin
GO_VERSION=1.27.0
GO_ARCHIVE_SHA256=90493b3bbd5e10f91d12153198bf1994fd756399b4fec93b49b0c6e2acdeeb3e
GOOSE_VERSION=3.27.1
GOLANGCI_LINT_VERSION=2.11.4

log() {
	printf '[bootstrap] %s\n' "$*"
}

fail() {
	printf '[bootstrap] ERROR: %s\n' "$*" >&2
	exit 3
}

require_supported_host() {
	[ "$(uname -s)" = Darwin ] || fail "Sprint 1 supports macOS only"
	[ "$(uname -m)" = arm64 ] || fail "Sprint 1 requires Apple Silicon arm64"
}

ensure_git_repository() {
	command -v git >/dev/null 2>&1 || fail "git is missing"
	if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
		log "initializing Git repository"
		git init || fail "git init failed"
	else
		log "Git repository already initialized"
	fi
}

make_temp_dir() {
	BOOTSTRAP_TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/football-bootstrap.XXXXXX")
	export BOOTSTRAP_TEMP_DIR
	trap 'rm -rf "$BOOTSTRAP_TEMP_DIR"' EXIT HUP INT TERM
}

install_uv() {
	if [ -x "$FOOTBALL_TOOLS_BIN/uv" ] && "$FOOTBALL_TOOLS_BIN/uv" --version | grep -q "uv $UV_VERSION "; then
		log "uv $UV_VERSION already installed"
		return
	fi
	log "installing uv $UV_VERSION into $FOOTBALL_TOOLS_BIN"
	curl --fail --location --retry 3 "https://astral.sh/uv/$UV_VERSION/install.sh" -o "$BOOTSTRAP_TEMP_DIR/uv-install.sh" || fail "uv installer download failed"
	UV_INSTALL_DIR="$FOOTBALL_TOOLS_BIN" sh "$BOOTSTRAP_TEMP_DIR/uv-install.sh" || fail "uv installer failed"
}

install_python() {
	log "installing uv-managed CPython $PYTHON_VERSION and locked dependencies"
	uv python install "$PYTHON_VERSION" || fail "uv python install $PYTHON_VERSION failed"
	uv sync --locked || fail "uv sync --locked failed"
}

install_rust() {
	if [ ! -x "$FOOTBALL_RUST_BIN/rustc" ] || [ ! -x "$FOOTBALL_RUST_BIN/rustfmt" ] || [ ! -x "$FOOTBALL_RUST_BIN/cargo-clippy" ]; then
		if ! command -v rustup >/dev/null 2>&1; then
			log "installing rustup in user space without modifying shell startup files"
			curl --fail --location --retry 3 https://sh.rustup.rs -o "$BOOTSTRAP_TEMP_DIR/rustup-init.sh" || fail "rustup installer download failed"
			sh "$BOOTSTRAP_TEMP_DIR/rustup-init.sh" -y --no-modify-path --default-toolchain none || fail "rustup installer failed"
			PATH="$HOME/.cargo/bin:$PATH"
			export PATH
		fi
		log "installing Rust $RUST_TOOLCHAIN with rustfmt and Clippy"
		rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal --component rustfmt --component clippy || fail "rustup toolchain install $RUST_TOOLCHAIN failed"
	else
		log "Rust $RUST_TOOLCHAIN already installed"
	fi
}

install_go() {
	if [ -x "$FOOTBALL_GO_ROOT/bin/go" ] && [ "$("$FOOTBALL_GO_ROOT/bin/go" version)" = "go version go$GO_VERSION darwin/arm64" ]; then
		log "Go $GO_VERSION already installed"
		return
	fi
	archive="$BOOTSTRAP_TEMP_DIR/go$GO_VERSION.darwin-arm64.tar.gz"
	log "installing Go $GO_VERSION arm64 into $FOOTBALL_GO_ROOT"
	curl --fail --location --retry 3 "https://go.dev/dl/go$GO_VERSION.darwin-arm64.tar.gz" -o "$archive" || fail "Go archive download failed"
	actual_sha=$(shasum -a 256 "$archive" | awk '{print $1}')
	[ "$actual_sha" = "$GO_ARCHIVE_SHA256" ] || fail "Go archive checksum mismatch: expected $GO_ARCHIVE_SHA256, got $actual_sha"
	mkdir -p "$FOOTBALL_TOOLS_DIR/go"
	tar -xzf "$archive" -C "$BOOTSTRAP_TEMP_DIR" || fail "Go archive extraction failed"
	rm -rf "$FOOTBALL_GO_ROOT"
	mv "$BOOTSTRAP_TEMP_DIR/go" "$FOOTBALL_GO_ROOT"
}

install_go_tool() {
	binary=$1
	version=$2
	package=$3
	if command -v "$binary" >/dev/null 2>&1 && "$binary" --version 2>&1 | grep -q "$version"; then
		log "$binary $version already installed"
		return
	fi
	log "installing $binary $version into $FOOTBALL_TOOLS_BIN"
	go install "$package@v$version" || fail "go install $package@v$version failed"
}

ensure_container_engine() {
	command -v docker >/dev/null 2>&1 || fail "docker CLI is missing"
	if ! docker info >/dev/null 2>&1; then
		if [ -d /Applications/OrbStack.app ]; then
			log "starting OrbStack"
			open -gj -a OrbStack || fail "unable to start OrbStack"
			attempt=0
			while ! docker info >/dev/null 2>&1; do
				attempt=$((attempt + 1))
				[ "$attempt" -lt 30 ] || fail "Docker engine did not become ready within 60 seconds"
				sleep 2
			done
		else
			fail "Docker engine is unavailable and OrbStack is not installed"
		fi
	fi
	docker compose version >/dev/null 2>&1 || fail "docker compose is unavailable"
	log "pulling pinned PostgreSQL and Redis images"
	docker compose pull || fail "docker compose pull failed"
	log "starting pinned PostgreSQL and Redis services"
	docker compose up -d --wait || fail "docker compose up --wait failed"
}

require_supported_host
ensure_git_repository
mkdir -p "$FOOTBALL_TOOLS_BIN" "$FOOTBALL_PROJECT_ROOT/.local"
make_temp_dir
install_uv
install_python
install_rust
install_go
install_go_tool goose "$GOOSE_VERSION" github.com/pressly/goose/v3/cmd/goose
install_go_tool golangci-lint "$GOLANGCI_LINT_VERSION" github.com/golangci/golangci-lint/v2/cmd/golangci-lint
ensure_container_engine
"$FOOTBALL_PROJECT_ROOT/scripts/doctor.sh"
