# ADR 0002: Scope golangci-lint to syntax-level complexity analysis on Go 1.27

Status: accepted

Date: 2026-08-29

## Context

Sprint 1 pins Go 1.27.0 and golangci-lint 2.11.4. The project-local linter binary was built with Go 1.27.0, but its default type-analysis loader cannot decode Go 1.27 standard-library export data:

```text
cannot decode "internal/goarch", export data version 4 is greater than maximum supported version 2
```

The failure reproduces with a clean project-local cache. Syntax-level cyclomatic-complexity analysis works. Native `go vet` and `go test` also work with the pinned compiler.

## Decision

Keep both approved pins. Configure golangci-lint to enforce `cyclop` with maximum function complexity 10 and package average 5. Run native `go vet` separately for compiler-compatible semantic analysis.

## Consequences

- `make lint` remains green only when Ruff, mypy, Clippy, `go vet`, and the pinned cyclomatic-complexity check all pass.
- No linter or complexity rule is suppressed in source code.
- Type-dependent golangci-lint analyzers remain disabled until a pinned release can decode Go 1.27 export data; changing that pin requires normal bootstrap and regression validation.
