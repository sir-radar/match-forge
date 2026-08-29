# ADR 0003: Use commit-pinned immutable source acquisition

- Status: Accepted
- Date: 2026-08-29

## Context

StatsBomb Open Data is published through a Git repository. Branch contents can change, and ingestion must remain reproducible, idempotent, and auditable after upstream changes or interrupted runs. Raw provider bytes must remain separate from normalized and curated data.

## Decision

Require a full Git commit SHA for every StatsBomb adapter instance. Preserve exact response bytes under a provider-and-revision path before parsing. Publish raw resources and source manifests with exclusive immutable writes. Derive the manifest scope path from the sorted resource descriptors, and verify completed scopes from local bytes without a network request.

## Consequences

- Historical acquisitions remain addressable after upstream branches move.
- Identical completed reruns do not alter files or require provider availability.
- Partial acquisitions can resume, but existing conflicting bytes fail closed.
- Callers must select and record a source commit before acquisition.
- Local filesystem storage is the first implementation; object storage must preserve the same contract.
