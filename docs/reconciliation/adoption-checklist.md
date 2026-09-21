# Repository reconciliation checklist

The initial supplied plan is preserved in [archive](../references/supplied-plan-2026-09-21.md). The root `PLAN.md` is the tracked proposed roadmap. Repository status, owner decisions, approved contracts, and retained evidence remain higher authority.

- [x] Reconcile `docs/project-status.json` with the 20 September 2026 owner decision. The narrow Phase 3A authorization is recorded; **do not duplicate or broaden it**.
- [x] Confirm the retained Sprint 2 `FAIL` and shared-pace `TERMINAL_ROUTE_FAIL` references. The 280-target isolation rule remains unchanged.
- [x] Record Evaluation V2 as design/pre-registration only. No authoritative run is authorized.
- [x] Keep the minimal Rust authorization proposal separate and unapproved.
- [ ] Before each implementation task, record the current commit and worktree state; inspect applicable contracts, code, CI, protected-target controls, experiment records, model registry, and newer decisions.
- [ ] Assert that each new task or script cannot access protected Sprint 2 targets. Stop on any mismatch.
- [ ] Compare proposed contracts with existing names and interfaces. Preserve approved APIs, `rust/simulation-core`, and Python/Go boundaries. Use approved compatibility changes rather than renaming databases or breaking clients to match proposed docs.
- [ ] Freeze hash projection/precision and test Rust/Python/Go golden serialization against existing output representation **before** writing V1 hashes. No retrospective rehash of published artifacts.
- [ ] Define independent simulator authorization, freeze numerical reference/tolerances and engineering budgets, then implement minimum sampler/test suite only if approved. Approval for implementation does not enable production.
- [ ] Independently freeze Evaluation V2 corpus/firewall/policy/thresholds and obtain an authoritative-run owner decision; retain old targets untouched.
- [ ] Test same-kickoff/cutoff, feature parity, calibrator coherence, artifact immutability, simulator reference parity and states, enrichment disabled/faulted parity, publisher crash/idempotency and API backward compatibility.
- [ ] Obtain distinct owner decisions for candidate promotion and production capability enablement; rehearse rollback, recovery, security, licence and cost checks. A Rust `PASS` alone cannot promote predictive performance.
- [ ] Review final diff for deletion of existing documentation, unapproved changes to statuses/artifacts, invented approvals, unsupported threshold values or promises about already-deployed endpoints. Archive evidence before merge.

**Change workflow:** create a task branch → inspect tracked status and decisions → make the smallest scoped change → use `git diff -- PLAN.md docs/` where applicable → run documented relevant checks → submit a scoped review. Never treat a documentation proposal as implementation or approval evidence.
