# Local code intelligence

MatchForge uses [codebase-memory-mcp 0.12.1](https://github.com/DeusData/codebase-memory-mcp/releases/tag/v0.12.1)
for focused code navigation. This is development tooling; scientific gates,
production behavior and approved architectural decisions are unchanged.

## Decision and alternatives

Research date: 2026-11-03. Official source, the two latest release entries and
five recent open issues/PRs were inspected for each candidate. These are samples,
not a complete maintenance or security audit. No candidate's marketing benchmark
is treated as a MatchForge measurement.

| Candidate | Evidence and fit | Decision |
| --- | --- | --- |
| [CodeGraph](https://github.com/colbymchenry/codegraph) 1.6.2 | Local MCP/CLI, macOS, Python/Go/Rust/TS/TSX; native debounced watcher, startup reconciliation. Release indexed 687 executable-source files. Its extension map omits SQL, ordinary JSON Schema and Markdown. Current README also documents `init --local-only`, absent from the release. [Issue 3219](https://github.com/colbymchenry/codegraph/issues/3219) reports a stale bundled Node runtime. | Strong code navigator, but incomplete coverage for this repository's contracts. Not installed permanently. |
| [Graphify](https://github.com/Graphify-Labs/graphify) 0.9.101 | Local AST indexing, budgeted query/path/explain, macOS and target languages; SQL extra. `update --no-cluster` worked without an LLM. Watch is a separate CLI lifecycle; documentation semantics can require an LLM. Codex skill describes parallel extraction, which this task does not authorize. | Benchmarked only its deterministic local path; not selected. |
| [Serena](https://github.com/oraios/serena) 2.1.0 | Official README names Codex App, MCP and target executable languages. Precise LSP symbol references, file watching and persistent memories; separate language-server dependencies. SQL is absent from its published LSP language list. | Reviewed, not installed or benchmarked. More setup for a mixed-language repository. |
| [GitNexus](https://github.com/abhigyanpatwari/GitNexus) 1.6.13-rc.197 | Local MCP, Codex and macOS support; `analyze --watch` serializes incremental updates. Node/native graph dependencies and separate watcher lifecycle; current release stream is prerelease. PolyForm Noncommercial license requires separate consideration outside this private experiment. | Reviewed, not installed or benchmarked. No demonstrated benefit over the smaller selected deployment. |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp/tree/v0.12.1) 0.12.1 | Single local binary; native MCP, persistent SQLite graph, Git polling, serialized indexing, bounded structural queries, source coverage diagnostics, Markdown/JSON/SQL plus executable languages. No LSP or embedding download needed for this workflow. | Selected. Broader contract coverage and verified session synchronization outweigh slower one-shot CLI queries. |

All five projects were active in the sampled release/source history. Free local
operation does not guarantee perfect call resolution. React and Next.js sources
are indexed as TS/TSX; framework-generated and dynamic relationships remain
best-effort. Native CBM does not collect telemetry. The launcher disables the UI;
no hosted service, model download, external semantic API, agent system or custom
background watcher is introduced.

## Install and connect

From a MatchForge checkout on macOS:

```sh
sh scripts/code-intelligence.sh install
codex mcp list --json
```

The installer downloads the official **pinned** macOS ARM64 or AMD64 archive,
checks its recorded SHA-256 before extracting the binary and notices, and
preserves the current installation on checksum failure. Checksums come from the
[release checksum manifest](https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.12.1/checksums.txt).
Other platforms fail explicitly; their builds were not validated in this task.
Upgrade only after reviewing the release, updating the pin/checksums, and rerunning
verification. Do not run the upstream global installer or automatic updater.

`.codex/config.toml` starts the launcher as the `matchforge_code` stdio MCP server.
The shell resolves the current Git checkout, so nested directories and linked
worktrees find their own launcher. Existing user MCP settings remain intact.
Project configuration requires a trusted checkout; see the official
[Codex configuration documentation](https://developers.openai.com/codex/config-basic)
and [MCP configuration](https://developers.openai.com/codex/mcp).
Open a new Codex conversation in the trusted checkout after merging this PR.
The current conversation's tool registry is not dynamically reloaded.

Linked worktrees share the primary checkout's ignored
`.tools/code-intelligence/0.12.1/` binary and `.local/code-intelligence/` cache.
Individual graphs retain their native checkout-path identity. Removing a task
worktree therefore retains the installed tool and primary cache. CBM enforces
one exact build and canonical cache per account; another CBM installation with a
different build/cache produces an explicit admission error. Do not bypass that
barrier or stop another task's daemon. Coordinate its cache/build before use.
No `.env` variables are added.

## Navigation and synchronization

The root `AGENTS.md` permanently requires focused index queries before broad
exploration, approximately 1,200-token output budgets, relationship tracing,
source verification, reuse of results and direct fallback on stale or incomplete
results. There are no nested tracked `AGENTS.md` files overriding this rule.
The project exposes navigation, coverage and indexing MCP tools; native ADR
mutation and unrelated analysis tools are not enabled in Codex.

The launcher configures native automatic indexing/watching, reconciles the
checkout with `index_repository(mode=full, doc_candidates=false)` before MCP
starts, then delegates to the native server. Startup fails if reconciliation
fails, preserving MCP stdout for JSON-RPC. Subsequent changes use CBM's existing
Git watcher and index locks. No Git hooks or custom background service are needed.

CBM polls HEAD and dirty state, including recursive untracked files and repeated
edits to already-dirty files. It coalesces edits observed within a poll interval,
can reuse unchanged indexed files and removes deleted entries. New files, added
definition names and semantic configuration changes can instead trigger a full
rebuild in 0.12.1; incremental reuse is not a guarantee for every edit. Polling is adaptive
(5–60 seconds in the inspected source), so there is a freshness window. New files,
directories, moves, deletes, generated source and Git operations all follow the
same mechanism. Source-control operation types are not special hooks.

`index_status` exposes `watch.watched`, strategy, poll cadence and last scan.
The watcher runs while MCP sessions are connected. One-shot CLI calls report
`cli_session` and do not keep watching; refresh before standalone CLI navigation:

```sh
sh scripts/code-intelligence.sh cli index_repository --repo-path "$PWD" --mode full --doc-candidates false
sh scripts/code-intelligence.sh cli search_graph --project "$PWD" --name-pattern normalize_resource --limit 8 --max-output-tokens 1200
sh scripts/code-intelligence.sh cli trace_path --project "$PWD" --function-name normalize_resource --direction inbound --depth 2 --limit 20 --max-output-tokens 1200
sh scripts/code-intelligence.sh cli index_status --project "$PWD"
```

`mode=full` includes docs and migrations that `fast` deliberately excludes; it
still supports native incremental reuse. Documentation scoring is disabled.
`.cbmignore` retains all 13 authoritative `web/ui-designs/<design>/code.html`
references and their design notes. It excludes only PNGs in that directory,
historical evidence/evaluation archives,
local state, dependencies, builds and index outputs. Current engineering docs,
source, shared schemas, migrations and relevant tests/fixtures remain eligible.
The existing Git ignore rules also apply. Index bytes and provider data are never
committed or sent to an external indexing service.

If freshness is uncertain after an edit, branch change or restart, complete an
`index_repository` refresh before relying on relationships. Check partial-parse
warnings with `index_status` and `check_index_coverage`. A ready status or recent
scan alone is insufficient: verify metadata for the changed paths and the expected
new symbols/paths, including disappearance of obsolete results. On failure, inspect source
directly, address the reported error, then retry once. Never delete locks or
caches used by another session. Restarting Codex reconnects the native MCP process
and reruns launcher reconciliation. Native process restart was tested; the
running desktop application was not restarted because another task is active.

## Initial discovery probes (PR #180)

Machine-readable observations: [code-intelligence-benchmark.json](code-intelligence-benchmark.json).
The five fixed discovery probes were normalization, a manifest contract, a forecast
adapter, a frontend hook and remediation recovery. Each tool received the same
symbol string in the same checkout, with one deterministic CLI query per probe;
there was no model, judge, subagent or model-setting difference.

| Five discovery queries | Total output bytes | Total elapsed seconds | Symbol matches |
| --- | ---: | ---: | ---: |
| Scoped `rg -n` baseline | 12,693 | 0.110 | 5/5 text matches |
| CodeGraph `query --limit 5 --json` | 12,897 | 1.031 | 4/5; contract text is not a symbol |
| Graphify `query --budget 1200` | 16,421 | 4.614 | 4/5; manifest contract query exits 4 |
| CBM `search_graph --limit 5 --max-output-tokens 1200` | 1,312 | 5.298 | 4/5; manifest contract needs text/source fallback |

These are discovery probes, not complete architecture investigations. They return
different information: `rg` includes text references, CBM returns compact symbol
locations/degrees, and other tools emit richer records. Output reduction is **not
measured model token savings**. In those initial probes, model input/output
tokens, full-task file reads,
context-window use and peak process-tree memory were **NOT MEASURED**. The later
controlled CLI comparison and finite resource sample below supersede those gaps
where explicitly measured. The baseline already uses a focused search; CBM is slower than `rg` for known exact text.

Initial observed indexing was 8.01 seconds for CodeGraph and 16.704 seconds for
Graphify. CBM's initial `fast` index was 12.13 seconds; expanding it to `full` with
exclusions took 6.50 seconds. Those runs have different file coverage and CBM's
second run was warm, so they do not establish a fastest indexer. Graphify indexed
977 eligible files and CodeGraph 687. CBM's verified full graph initially held
16,393 nodes and 74,484 edges; counts change with eligible repository edits.

Relationship checks found the production `normalize_resource` caller in its CLI
and all five frontend consumers of `useResource`; these were verified against
source. Test callers are excluded by default from `trace_path`. Dynamic dispatch,
contract-name strings and cross-language serialization need direct verification.
In particular, a JSON Schema file being eligible does not imply that `$ref` or
all schema consumers have complete graph edges.

Run repeatable local acceptance checks with the existing Python toolchain:

```sh
uv run pytest tests/test_code_intelligence.py
uv run python scripts/verify_code_intelligence.py
```

The second command opens a real local MCP connection, verifies targeted
navigation, then creates a disposable Git repository to test native sync. It
removes that repository and its graph registration in cleanup. Outputs go to
ignored `.local/code-intelligence-verification.json` and `.log`. It requires
local process/socket access and does not call a model or provider. The launcher
tests cover missing-install recovery, startup failure, clean MCP stdout and
checksum rejection preserving an existing binary.

The remediation rechecked all 67 partial and two unusable files; details follow.
These sources remain authoritative and must be read directly. A coverage result
of `no_recorded_issue` is best-effort, not proof of complete semantic extraction.
GUI-wide agent compliance, sustained resource use and every individual
merge/rebase/pull operation remain unmeasured. The controlled CLI usage comparison
is reported below.

Initial PR #180 repository verification passed:
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT UV_NO_SYNC=1 make check integration`
(exit 0). This covered formatting, lint, strict typing, complexity, architecture,
1,762 Python unit tests (including four launcher cases), 16 Rust tests, 107
frontend tests, builds, migration validation and disposable database/API
integration. One existing frontend unused-variable warning was unchanged.
The exact configured Codex command also passed a real MCP handshake and targeted
query from a nested directory; every configured tool name exists.

## Parsing and coverage investigation (2026-11-03)

Before the ignore correction, the same checkout indexed 16,491 nodes and 74,599
edges. Restoring design coverage produced 16,567 nodes and 74,678 edges, including
13 HTML files and two design documents. These are the isolated ignore-change
observations; later documentation/test edits also change graph counts. All 13
HTML paths were discovered with `search_graph(file_pattern="web/ui-designs/*/code.html",
label="File")` and checked for matching saved metadata. HTML file/module discovery
does not encode its visual layout: read the authoritative HTML before frontend work.

Full diagnostics reproduced **67 partial files and two unusable files**, with no
warnings hidden or sources changed to improve the counts. The benchmark JSON
retains every affected path and error range.

| Category | Finding and navigation impact | Required source verification |
| --- | --- | --- |
| 66 partial PostgreSQL migrations | The bundled generic SQL grammar recovers only parts of PL/pgSQL, PostgreSQL constraints/casts, qualified DROP statements, ON CONFLICT and other dialect constructs. Definitions can survive while function bodies, constraints and table dependencies are missing. | Read DDL and function bodies, search callers' SQL, and check migration/integration tests. |
| `Makefile` | Eight recipe lines contain nested Make `$(if ...)` expressions inside shell commands. Execution/build targets remain valid; extracted command dependencies can be incomplete. | Read the relevant recipe and its prerequisites directly. |
| Malformed JSON fixture `data/fixtures/statsbomb/sprint1/malformed-events/data/events/1003.json` | Contains only an opening brace intentionally. `tests/test_sprint1_fixtures.py` and its integration counterpart assert ingestion failure. | Preserve the negative fixture and its warning. |
| `202610210100_unknown_season_fixture_reconciliation.sql` | The valid 159-line migration wraps a PostgreSQL reconciliation function with procedural statements, CTEs, JSON aggregation and casts; the generic parser marks nearly the entire file unusable. | Read the function and callers directly; PostgreSQL migration/integration validation is authoritative. |
| JSON Schema and cross-language contracts | Eligible JSON becomes file/module/key records. This does not resolve `$ref`/`$defs` or establish Python/Go/Rust/TypeScript serializer-consumer parity. | Follow references, serializers, consumers and contract/parity tests in source. |
| Python, Go, Rust, TS/TSX and architecture docs | No additional parse warnings in these languages were reported in this run. Dynamic calls, route wrappers, re-exports and ambiguous document mentions can still be incomplete or wrong. | Confirm critical call/import paths and the cited document text. |

The pinned [extension configuration](https://github.com/DeusData/codebase-memory-mcp/blob/v0.12.1/docs/CONFIGURATION.md)
allows mapping extensions to built-in grammars. Its separate `plsql` grammar is
for Oracle PL/SQL, not PostgreSQL; remapping production `.sql` files would not be
a justified fix. No supported PostgreSQL grammar selector or JSON Schema resolver
was found. The source's [SQL extraction](https://github.com/DeusData/codebase-memory-mcp/blob/v0.12.1/internal/cbm/extract_defs.c)
collects selected DDL and FROM/JOIN relationships, while
[language specifications](https://github.com/DeusData/codebase-memory-mcp/blob/v0.12.1/internal/cbm/lang_specs.c)
define the grammar node types. No parser warning was resolved safely by configuration.

Relevant upstream reports remain caveats, not MatchForge measurements:
[Go route-wrapper relationships #2883](https://github.com/DeusData/codebase-memory-mcp/issues/2883),
[TS re-export work #2900](https://github.com/DeusData/codebase-memory-mcp/pull/2900),
[one-shot CLI hashing overhead #2834](https://github.com/DeusData/codebase-memory-mcp/issues/2834),
and [full-rebuild fallbacks #2835](https://github.com/DeusData/codebase-memory-mcp/issues/2835).
An open upstream fix is not part of the pinned release.

## Freshness findings

The [pinned watcher](https://github.com/DeusData/codebase-memory-mcp/blob/v0.12.1/src/watcher/watcher.c)
uses Git HEAD plus dirty/untracked path metadata. Its cadence is 5 seconds plus
1 second per 500 tracked files, capped at 60 seconds. Poll-loop scheduling,
indexing and the verifier's one-second observation interval add latency. No
supported event-driven switch or poll-interval setting exists in the inspected
release. Retain native polling and serialization; do not add a watcher or shorten
an undocumented setting.

The expanded verifier separately checks file deletion, remaining-directory deletion,
saved JSON Schema/SQL/HTML metadata, obsolete rename-path removal, and actual
launcher recovery after offline edits. The earlier SQL timing shared a preceding
create batch, so its near-zero wait was not an independent save-to-index latency.
The new per-file metadata checks avoid that ambiguity. Native restart and launcher
reconciliation are distinct: launcher startup finishes the refresh before queries.
A real desktop application restart remains unexercised; restarting the running app
would interrupt this chat and other work. The production launch command is exercised
against a disposable Git checkout instead.

## Actual Codex task comparison

Five read-only development tasks covered all ten requested areas in five matched
pairs. Both arms used `gpt-6.1-terra`, medium reasoning, CLI
`0.166.0-alpha.5.1`, the same audited source snapshot based on `30776210`, identical
task/verification requirements, and fresh ephemeral sessions. Order alternated by
task. Normal source navigation was the baseline; the other arm used the configured
MCP navigation rules and verified relationships against source.

The Homebrew CLI `0.137.0` rejected current model names; the desktop-bundled CLI
worked. Initial optional-MCP trials fell back to source and were discarded. Valid
optimized runs set `required=true` and an explicit snapshot working directory;
each actually used MCP. Trial/pilot and interrupted-run tokens are excluded from
paired savings, rather than being represented as successful optimized work.

The owner's approved isolation conditions were applied before the comparisons:
976 source/config files were audited and 449 files excluded, including data and
payload directories, environment files, binary assets, and 12 files matching
credential/sensitive-content patterns. A separate local index held only this
snapshot. Shell commands could read only the snapshot and minimal platform paths;
command networking, plugins and external-account tools were disabled. Raw JSONL,
model answers, audit records and generated outputs remain local and ignored.
Tracked evidence contains task definitions, aggregate measurements and hashes.

Counts come from the documented
[`codex exec --json` usage event](https://learn.chatgpt.com/docs/non-interactive-mode),
not output-size estimates. Input includes cached input; cached and reasoning
counts are reported separately and are not added again to total input + output.

| Task | Baseline total tokens | MCP total tokens | Token reduction |
| --- | ---: | ---: | ---: |
| Provider acquisition, normalization and identity mapping | 240,000 | 271,347 | -13.06% |
| Canonical storage, SQL, recovery and quarantine | 200,155 | 184,035 | 8.05% |
| Forecast routing and cross-language simulation contracts | 276,747 | 354,533 | -28.11% |
| Go serving, frontend hook consumers and refactor tests | 134,214 | 170,081 | -26.72% |
| Frontend markets implementation and authoritative HTML | 243,611 | 193,971 | 20.38% |
| **Total** | **1,094,727** | **1,173,967** | **-7.24%** |

Baseline input/output: **1,085,706 / 9,021**. MCP input/output:
**1,162,824 / 11,143**. Cached input: **934,784 / 999,936** respectively.
Uncached input: **150,922 / 162,888**. Tool calls rose from **44 to 97**;
observed total execution time rose from **231.429 to 324.676 seconds**. This is
one sample per task/arm, not a statistically established universal effect or a
billing comparison. Startup reconciliation is included in optimized wall time;
the snapshot graph was warm after the separate required-MCP preflight.

Independent review checked the answers’ key relationships against source; neither
arm claimed unperformed test execution. Both found all five production `useResource` consumers and inspected the HTML
for the design task. Both qualified the simulation-contract gap: the inspected
Python/Rust V3 wire payload had no established standalone JSON Schema or Go wire
consumer in the audited snapshot. Go serving persisted forecasts is a different
relationship. SQL and cross-language investigations still required source reads.
The benchmark asked for discovery and test-impact analysis; neither arm changed
production code or claimed it had executed the discovered tests.

Full filesystem-read counts, irrelevant-file counts, peak context-window usage,
per-request token attribution and actual desktop-GUI usage are **NOT MEASURED**.
The JSON records only partial explicit source-read paths observable from shell
commands and MCP snippet responses; broad search reads and implicit runtime reads
are not counted as complete file-read telemetry. The partial explicit shell-read
counts sum to 38 for baseline and 34 for MCP across tasks; these exclude search
reads and do not establish fewer irrelevant files. Pure MCP latency was measured
separately, since these Codex events do not expose per-call durations.

## Resource observations and recommendation

A separate 63.034-second local sample measured full-repository startup/idle and a
small disposable edit burst. Full-repository launcher initialization took
**10.159 seconds**. Summed CBM resident memory peaked at **222,176 KiB** during
startup and **27,664 KiB** in the full-repository idle phase. Observed CBM CPU time
in that roughly 20-second idle phase was **0.20 seconds**. The repository watcher
reported a **7,000 ms** poll interval. Twenty persistent-MCP fixture queries had
median/max latency **0.013125 / 0.015593 seconds**; the fixture burst converged in
**1.058 seconds** because of its position within the polling cycle.

Sampling every 0.5 seconds can miss short-lived children. These CPU observations
exclude Git subprocesses, and summed RSS double-counts shared pages. They do not
establish sustained memory or CPU behavior during continuous full-repository
editing. No extra watcher, polling override, embedding service or permanent
background process was added.

**Recommendation: REVISE.** The selected tool is useful for some focused tasks,
including finding restored HTML designs, but this sample demonstrates **higher
overall model-token consumption**, more calls and more latency. Keep it available
for bounded relationship discovery; allow direct reads for known paths/text and
switch to source when a targeted graph query misses or reaches an unsupported
relationship. The refined `AGENTS.md` enforces that distinction, fresh-path
verification and SQL/schema/serializer checks. Do not claim that the refined rules
already deliver token savings: that would require another comparable measurement.


## Final remediation verification

`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT UV_NO_SYNC=1 make check integration`
completed with exit 0: formatting, lint, strict typing, complexity, architecture,
1,765 Python unit tests (including seven tooling cases), 16 Rust tests, 107
frontend tests, builds, migrations, disposable PostgreSQL storage/recovery tests,
and Go operational API integration. One pre-existing frontend unused-variable
warning remains. No production code, SQL, schema, model contract or phase gate changed.

`python3 scripts/verify_code_intelligence.py` passed against the pinned real MCP.
The final run measured 5.1–6.2-second routine edit/metadata convergence, 11.2-second
first discovery/native restart, and completed launcher startup in 8.921 seconds.
File and recursive-directory creation, modification, rename/move, deletion,
branch switches, JSON/SQL/HTML/document changes and offline launcher recovery
passed; the disposable repository and graph registration were removed. A final
bounded coverage check confirmed all 13 HTML designs plus ten contract, language
and architecture-document paths had matching saved metadata. All ten Codex usage
records matched their local event logs and SHA-256 hashes.
