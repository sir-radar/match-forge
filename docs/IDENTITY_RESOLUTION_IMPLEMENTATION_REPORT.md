# Identity Resolution Center implementation

## Phase 0 baseline and implementation map

The read-only audit on `football_architecture_v2_shadow_20261016` revalidated 4,160 unresolved mappings, 108 contradictory mappings, one revoked mapping, 984 unsafe shared identity groups, 33 unavailable source resources, and three unavailable dataset files. There are 59,903 provisional fixtures. The audit used existing identity qualification and both supported raw-file verification owners; the frozen 4,253 proof-availability set has a different denominator and is not relabeled as the current mapping backlog. See `docs/evidence/identity-resolution-baseline-2026-10-31.json`.

Reuse:

- Existing crosswalks, alias normalization, admissions and effective-dated team corrections own identity. Review candidates never authorize admission.
- Existing operational mapping qualification and fixture reconciliation own fixture decisions and retained observations.
- Existing immutable file store and integrity verifier own source/dataset verification and publication.
- Existing Work Orchestrator owns downstream leases, fencing, retries and completion.
- Existing Go Admin private-local checks and owner credential protect the new routes; Python retains domain decisions.
- Existing Next.js shell, tables, form styling and resource states provide navigation and presentation.

Gaps: unified case discovery, bounded review, evidence-version previews, authenticated decision endpoints, review audit history, retained-file recovery controls, actionable parity views, and isolated migration preparation. One additive append-only review log records workflow state without duplicating domain decisions.

Phase order: (1) identity diagnostics; (2) read-only queue; (3) protected preview/apply; (4) independent bounded batches; (5) qualified fixture/recovery integration; (6) source recovery/disposition; (7) existing evidence-backed parity; (8) isolated controls/rehearsal; (9) retirement preparation; (10) final verification and delivery. Each checkpoint is recorded in local ignored `CURRENT_TASK_STATUS.md`.

Production Phase 35 cutover and Phase 36 retirement remain blocked by missing identity proof, authentic source bytes/lineage, complete production-scope parity, and explicit acceptance. The 59 generic Elo conflicts and 327 insufficient-history targets remain explicit limitations. No provider requests, authoritative evaluation, model fitting or promotion is authorized by the review interface.

## Phase 1 — Identity diagnostics

`resolution_identity.py` reuses existing trust and effective-dated identity owners.
It reports the five requested review statuses, retains explicit contradictions and
revocations, discovers native-ID and exact-alias candidates without admitting them,
and returns retained correction contexts, bounded fixture impacts and evidence
versions. No identity table, admission rule, model input or historical query changed.

Verification: seven focused unit tests and five PostgreSQL acceptance tests passed.
The database tests migrate disposable databases only through `202610310300`, before
any Resolution Center migration. They prove read-only operation, stable evidence
hashes, explicit crosswalk discovery, protected alias-only candidates, missing-byte
blocking, and prospective correction/revocation without changing earlier cutoffs.
The exact staged commit was also tested separately from later-phase drafts:

```sh
uv run --locked --no-sync pytest tests/test_resolution_identity.py tests/integration/test_resolution_identity_database.py
```

Result: 12 passed. Ruff, format checks, mypy, architecture checks and
`make project-status-check` passed for this phase.

Later phases remain in progress; their drafts are excluded from the Phase 1 commit.
