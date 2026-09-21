# New-forecast publication state machine — proposed

**Not yet production-authorized.** Reconcile existing job persistence, Rust scaffold and outbox before applying; do not backfill historic forecast IDs with synthetic validation.

```text
DRAFT → SEALED → VALIDATION_PENDING → VALIDATED → PUBLISHED
                         │                 │
                         ├→ FAILED         └→ publication retry (same IDs/hashes)
                         └→ INCONCLUSIVE → bounded retry / human review
```

`SEALED` denotes internally complete and immutable candidate; it is **not public** under a mandatory Rust product. Validate only after approved engine capability, policy and parameter eligibility. `VALIDATED` requires linked `PASS` and exact hash matching. `PUBLISHED` atomically (or via durable transactional outbox and recoverable reconciliation) exposes **unchanged** sealed forecast and immutable validation evidence. A crash between writes must never expose a simulation-validated record without the linked `PASS` evidence. Publication idempotency key: fixture ID + cutoff/horizon + model/calibrator/parameter/policy fingerprints + forecast candidate hash; retries cannot create competing published IDs.

- On `FAIL`/`INCONCLUSIVE`/timeout: preserve sealed candidate and evidence, do **not** silently publish or rerun with loosened thresholds, surface `SIMULATION_UNAVAILABLE` for new simulation-required products. Already published forecasts remain readable.
- On approved analytic-only exception: a **separate explicit branch** records owner-approved exception policy, reason, scope/expiry and delivery mode `ANALYTIC_ONLY`. It cannot claim `RUST_VALIDATED` or fabricate a `PASS` artifact. No exception exists just because Rust is down.
- On valid `PUBLISHED`: schedule optional enrichment asynchronously through outbox; a failed tag job must never roll back publication.
- On corrections/new cutoff: create a new candidate/revision ID, retain predecessor and run prospective validation as applicable.

Operations: transaction/outbox integration tests, kill/restart between every transition, duplicate message/idempotent consumer tests, stale-policy/engine rejection, authorization audit, timeout/cancellation, reconciliation of orphan candidate/validation records, rollback of deployment (not history), alert and cost telemetry. See [failure runbook](../operations/runbooks/simulation-failure.md).
