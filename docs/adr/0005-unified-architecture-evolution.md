# ADR 0005: Incremental unified architecture evolution

Date: 10 November 2026.
Status: **ACCEPTED — Option B; operating adoption remains separately authorized**.
Scope: Owner's 10 November 2026 foundation task authorizes P00-01, P00-02,
P01-01, P01-02, manual Admin backup and monthly reminders. Other roadmap tickets
remain proposals. This supersedes the investigation's proposed status.

## Context

The merged main baseline `0b83991` already contains immutable sources,
provider-neutral identity/history, typed observations, canonical resolution,
Work Orchestrator, artifact/forecast lineage and bounded post-match evaluation.
Operating evidence separately shows LEGACY routes, unknown running commit,
missing forward migration `202611100200`, no runtime model registrations and no
post-match evaluation records. Existing code is therefore reusable but not proof
of unified runtime adoption or autonomous model learning.

## Decision

Use [incremental existing-owner evolution](../architecture/unified-redesign-2026-11-10/design.md):

1. Reuse current provider, identity, qualification, shared work, publication,
   settlement, model and recovery owners. Keep Python/Rust/Go/SQL boundaries.
2. Use transaction-bound durable scoped events and SSE for one-way browser
   updates, with snapshot/replay and bounded exceptional revalidation. Preserve
   backend provider pull where push is unverified. Do not use sequence allocation
   as commit order or notification-only delivery as a durable log.
3. Reuse snapshot-bound dumps and add verified referenced-file backup/restore,
   encrypted/deduplicated destinations and dependency-aware archival only after
   source-read and restore compatibility pass. Never rewrite registered bytes.
4. Retain Rust. A synthetic RNG comparison is not full scientific parity or a
   reason to rewrite frozen algorithms/artifacts.
5. Start authorized learning automation at monitoring; fitting, independent
   evaluation and promotion remain distinct governed actions. No implicit
   challenger fallback or automatic promotion.
6. Evolve typed SQL/API/event/model/UI contracts additively, preserve old readers,
   and use the scoped BASE-EXTENSION handoff for later product slices. A01 stays
   excluded. Deferred feature pages are not prerequisites for core design.

## Alternatives and consequences

Minimal defect repair remains useful and can ship independently, but alone does
not deliver event replacement, complete recovery or governed learning. A new
identity platform, scheduler, broker, storage service or ML framework would add
migration and reproducibility risk without measured necessity. The recommended
option requires explicit mixed-version, fencing, replay, recovery and scientific
acceptance evidence; it does not erase missing source proof or phase blockers.

Use the [single roadmap](../architecture/unified-redesign-2026-11-10/roadmap.md)
and [research/experiment evidence](../architecture/unified-redesign-2026-11-10/research.md).
Independent Architecture V2 Phase 35/36 and model-governance gates remain binding.
Acceptance follows the owner's explicit foundation implementation instruction,
not documentation checks. It does not authorize operating migrations, data
acquisition, cutover, fitting, promotion, automatic backups or destructive cleanup.
The four investigation commits are included in main by planning
[PR #183](https://github.com/sir-radar/match-forge/pull/183); retain that historical
planning evidence without repeating the investigation.
