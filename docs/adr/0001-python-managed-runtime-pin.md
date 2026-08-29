# ADR 0001: Pin uv-managed CPython 3.13.14 for macOS arm64

Status: accepted

Date: 2026-08-29

## Context

The Wayfinder toolchain decision selected CPython 3.13.15 managed by uv 0.12.1. During Gate A bootstrap, the required command failed:

```text
uv python install 3.13.15
error: No download found for request: cpython-3.13.15-macos-aarch64-none
```

`uv python list 3.13 --all-versions` confirmed that 3.13.14 is the newest managed macOS arm64 build available to uv 0.12.1.

## Decision

Use uv-managed CPython 3.13.14 for the supported macOS arm64 Gate A environment. Keep the project compatibility range at `>=3.13,<3.14`.

## Consequences

- Bootstrap remains automatic, native arm64, and reproducible.
- System Python remains untouched.
- `.python-version` pins 3.13.14.
- Gate A must revalidate all prototype tests on 3.13.14.
- A future upgrade to 3.13.15 requires a uv-managed macOS arm64 build and normal lock/test validation.
