# Adoption checklist — preserve existing MatchForge progress

**This download is a documentation overlay; it does not edit the repository.** Apply it on a new branch/worktree, never over a protected status/evidence artifact without comparing actual data. Initial supplied PLAN is preserved in [archive](../references/supplied-plan-2026-09-21.md).

- [ ] Record current commit, dirty worktree, deployed versions and original `PLAN.md` checksum. Read actual `docs/project-status.json`, signed owner events, corpus/target firewall, experiment ledger, model registry, current code and CI. Treat this package's reported statuses as provisional until verified.
- [ ] Verify existing 20 Sep 2026 narrow Phase 3A authorization; **do not duplicate**. Verify Evaluation V2 *design-only* scope and absence/presence of newer decisions before requesting any new one.
- [ ] Confirm immutable Sprint 2 `FAIL`, 280-target isolation and shared-pace `TERMINAL_ROUTE_FAIL`; assert no newly introduced task/script references protected target paths. Stop on any mismatch.
- [ ] Diff proposed docs against existing names. Preserve approved contracts/API and existing `rust/simulation-core` plus Python/Go boundaries. Use aliases/compat adapters where legacy `FixtureDisplayTagsV1` and `ForecastRiskAssessmentV1` already exist; do not rename databases or break clients merely to match new docs.
- [ ] Apply root `PLAN.md` as roadmap, then introduce only non-conflicting supporting docs; existing `docs/project-status.json` and decision events are **not included** and must remain unchanged unless separately approved.
- [ ] Freeze hash projection/precision and test Rust/Python/Go golden serialization against existing output representation **before** writing V1 hashes. No retrospective rehash of published artifacts.
- [ ] Define independent simulator authorization, freeze numerical reference/tolerances and engineering budgets, then implement minimum sampler/test suite only if approved. Approval for implementation does not enable production.
- [ ] Independently freeze Evaluation V2 corpus/firewall/policy/thresholds and obtain an authoritative-run owner decision; retain old targets untouched.
- [ ] Test same-kickoff/cutoff, feature parity, calibrator coherence, artifact immutability, simulator reference parity and states, enrichment disabled/faulted parity, publisher crash/idempotency and API backward compatibility.
- [ ] Obtain distinct owner decisions for candidate promotion and production capability enablement; rehearse rollback, recovery, security, licence and cost checks. A Rust `PASS` alone cannot promote predictive performance.
- [ ] Review final diff for deletion of existing documentation, unapproved changes to statuses/artifacts, invented approvals, unsupported threshold values or promises about already-deployed endpoints. Archive evidence before merge.

**Suggested non-destructive integration:** create branch → copy docs alongside tracked files → use `git diff -- PLAN.md docs/` → reconcile existing paths → run repository's documented tests (do not invent commands) → submit scoped review. This package makes **no claim** that code tests have run.
