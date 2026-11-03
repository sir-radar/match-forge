#!/bin/sh
# Project-scoped launcher; CBM owns indexing, locking and automatic synchronization.
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
COMMON_GIT_DIR=$(git -C "$REPO_ROOT" rev-parse --path-format=absolute --git-common-dir)
SHARED_ROOT=$(dirname "$COMMON_GIT_DIR")
CBM_VERSION=0.12.1
CBM_BIN="$SHARED_ROOT/.tools/code-intelligence/$CBM_VERSION/codebase-memory-mcp"
# All linked worktrees must use one cache: CBM enforces one canonical cache per account.
CBM_CACHE_DIR="$SHARED_ROOT/.local/code-intelligence"
CBM_ALLOWED_ROOT="$REPO_ROOT"
export CBM_CACHE_DIR CBM_ALLOWED_ROOT

install_cbm() {
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) platform=darwin-arm64; checksum=9bfcbe38414b47969a3e1d1c1999f5357409387c86fa3d24221b5458267660d2 ;;
        Darwin-x86_64) platform=darwin-amd64; checksum=ca6e64397a8ae80cec898a8205a6aa16750ac798acc05a0c3ed983837944a581 ;;
        *) echo 'MatchForge pins the macOS CBM build; see docs/engineering/code-intelligence.md.' >&2; exit 2 ;;
    esac
    mkdir -p "$(dirname "$CBM_BIN")"
    download_dir=$(mktemp -d "$(dirname "$CBM_BIN")/download.XXXXXX")
    trap 'rm -rf "$download_dir"' EXIT HUP INT TERM
    archive="$download_dir/cbm.tar.gz"
    curl --fail --location --retry 2 --proto '=https' \
        "https://github.com/DeusData/codebase-memory-mcp/releases/download/v$CBM_VERSION/codebase-memory-mcp-$platform.tar.gz" \
        --output "$archive"
    actual=$(shasum -a 256 "$archive" | cut -d ' ' -f 1)
    if [ "$actual" != "$checksum" ]; then
        echo 'CBM archive checksum mismatch; existing installation preserved.' >&2
        exit 1
    fi
    tar -xzf "$archive" -C "$download_dir" codebase-memory-mcp LICENSE THIRD_PARTY_NOTICES.md
    "$download_dir/codebase-memory-mcp" --version
    mv "$download_dir/codebase-memory-mcp" "$CBM_BIN"
    mv "$download_dir/LICENSE" "$download_dir/THIRD_PARTY_NOTICES.md" "$(dirname "$CBM_BIN")/"
}

if [ "${1:-}" = install ]; then
    install_cbm
    exit 0
fi
if [ ! -x "$CBM_BIN" ]; then
    echo 'CBM is missing. Run: sh scripts/code-intelligence.sh install' >&2
    exit 1
fi
case "${1:-}" in
    serve)
        # Never put startup output on MCP stdout. Reconcile missed edits before queries.
        # Explicit reconciliation owns initial indexing; do not auto-index new projects.
        "$CBM_BIN" config set auto_index false >&2
        "$CBM_BIN" config set auto_watch true >&2
        "$CBM_BIN" config set watcher_enabled true >&2
        "$CBM_BIN" config set doc_candidates false >&2
        "$CBM_BIN" cli index_repository --repo-path "$REPO_ROOT" --mode full --doc-candidates false >&2
        cd "$REPO_ROOT"
        exec "$CBM_BIN" --ui=false
        ;;
    cli)
        shift
        cd "$REPO_ROOT"
        exec "$CBM_BIN" cli "$@"
        ;;
    status|stop)
        # Native stop refuses to interrupt committed clients in other sessions.
        exec "$CBM_BIN" daemon "$1"
        ;;
    *) echo 'Usage: sh scripts/code-intelligence.sh {install|serve|status|stop|cli <tool> [args]}' >&2; exit 2 ;;
esac
