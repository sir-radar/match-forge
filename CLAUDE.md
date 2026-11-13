# CLAUDE.md

Guidance for Claude Code in this repository. [AGENTS.md](AGENTS.md) is the binding engineering guide and applies in full. This file adds Claude Code specifics and the rules for keeping documents consistent. If the two disagree, AGENTS.md wins; fix this file.

## What MatchForge is

A phase-gated football forecasting and simulation platform: Python for data and modelling, Rust for deterministic simulation, Go for serving and operations, SQL for schema, JSON Schema for cross-language contracts, Next.js for the web app. See [docs/architecture.md](docs/architecture.md).

## Which document wins

Highest first (this is AGENTS.md section 1; repeat nothing else from it here):

1. The repository owner's current instructions, then AGENTS.md.
2. Resolved owner decisions and decision events, [docs/project-status.json](docs/project-status.json), and the immutable evidence they cite.
3. ADRs, versioned contracts, schemas and migrations.
4. [PLAN.md](PLAN.md) and its follow-on roadmaps: the [post-redesign F0–F11 plan](MatchForge_Post_Redesign_Extensible_Football_Product_Implementation_Plan_v2_2026-11-09.md) and the [unified architecture investigation](docs/architecture/unified-redesign-2026-11-10/README.md).
5. Other repository documentation, then research proposals.

The original 21 September plan is archived in [docs/references/supplied-plan-2026-09-21.md](docs/references/supplied-plan-2026-09-21.md) and kept locally as the git-ignored `PLAN.OLD.md`. It is comparison material, not a second authority. A roadmap never authorizes work and never overrides a newer owner decision.

## Where each fact lives

Keep one owner per fact. Change the owner first, then the documents that summarize it.

| Fact | Owner | Summaries to update afterwards |
| --- | --- | --- |
| Gate, route, programme and authorization state | `docs/project-status.json` and the owner-decision evidence it lists | `docs/status/current-state.md`, then PLAN.md "Where things stand" |
| Sequence, invariants, gate definitions | PLAN.md | `docs/README.md` |
| Engineering rules | AGENTS.md and `docs/*-engineering.md` | This file only if the authority order changes |
| Public API fields | `docs/api/openapi.yaml` | `docs/frontend/api-requirements.md` |
| Provider access and acquisition | `docs/source-acquisition.md` | README and PLAN.md banners that link to it |
| Which docs exist | `docs/README.md` | none; add every new document to it |

## Do not edit these to make them agree

They record what was true on a date. If a later fact differs, record it in a new file or in the current-state docs.

- `docs/evidence/**` and `docs/governance/decision-events/**`
- Dated reports: `docs/*_REPORT.md`, `docs/MVP-*.md`, `docs/V4_*.md`
- `docs/references/**`

Present-tense wording inside a dated log (for example "now awaits an owner decision") describes that date. Mark the log as history and put current wording in the current-state section instead.

## Consistency checklist for documentation changes

1. Check each status claim against `docs/project-status.json`, not against another prose document.
2. Use the repository's exact identifiers for routes, decisions and statuses (`TERMINAL_FAIL_RUST_PARITY`, not a paraphrase).
3. Do not describe a proposal as approved, or an authorized protocol-scoped run as production enablement. Rust is the standing example: `rust_simulation_authorized` is `false`, while frozen V3–V5 Rust builds ran as evaluation evidence.
4. Add new documents to `docs/README.md` and link them from the document that owns their topic.
   Prefer a section in an existing document to a new file. When a feature is finished, retire its temporary documents in the same PR (AGENTS.md, Documentation lifecycle).
5. Relative links and anchors must resolve. `make docs-check` checks every maintained document.
6. Do not edit `docs/project-status.json` by hand to match prose; it needs an owner decision and `make project-status-check`.
7. Keep to one concern per commit and describe the inconsistency in the message.

For prose-only changes follow AGENTS.md section 12: review the diff and run `git diff --check` and `make docs-check`. Skip `make check` and integration unless a code, schema or status file changed.

## Working in this checkout

- `.env`, `CURRENT_TASK*.md`, `TASKS_TO_CONTINUE.md` and `PLAN.OLD.md` are git-ignored local files. Never commit them, and never put secrets or local paths from them into tracked files.
- Use the Edit tool for single changes and avoid `sed -i`; it behaves differently on macOS.
- Branch from `main` with a task branch (for example `docs/<topic>`). Commit each logical stage separately, push, and open a PR following [docs/git-delivery.md](docs/git-delivery.md) and [docs/pr-template.md](docs/pr-template.md).
- Ask the owner when two authoritative sources conflict and the order above, newer decisions and Git history do not settle it. Do not ask for facts the repository already holds.
- Finish a phase gate or Wayfinder map by reporting the result and stopping. Do not begin the next phase without authorization.
