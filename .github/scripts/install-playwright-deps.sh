#!/usr/bin/env bash
set -euo pipefail

# Fail on incomplete indexes instead of waiting on stale mirrors.
sudo tee /etc/apt/apt.conf.d/99-matchforge-ci >/dev/null <<'APT'
Acquire::Retries "1";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
APT::Update::Error-Mode "any";
APT
pnpm exec playwright install-deps "$@"
