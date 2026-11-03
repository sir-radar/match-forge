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
reuses unchanged indexed files and removes deleted entries. Polling is adaptive
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
`.cbmignore` excludes historical evidence/evaluation archives, design screenshots,
local state, dependencies, builds and index outputs. Current engineering docs,
source, shared schemas, migrations and relevant tests/fixtures remain eligible.
The existing Git ignore rules also apply. Index bytes and provider data are never
committed or sent to an external indexing service.

If freshness is uncertain after an edit, branch change or restart, complete an
`index_repository` refresh before relying on relationships. Check partial-parse
warnings with `index_status` and `check_index_coverage`. On failure, inspect source
directly, address the reported error, then retry once. Never delete locks or
caches used by another session. Restarting Codex reconnects the native MCP process
and reruns launcher reconciliation. Native process restart was tested; the
running desktop application was not restarted because another task is active.

## Benchmark and verification

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
measured model token savings**. Model input/output tokens, full-task file reads,
context-window use and peak process-tree memory: **NOT MEASURED**. The baseline
already uses a focused search; CBM is slower than `rg` for known exact text.

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

Known full-repository parse diagnostics initially included 67 partial files
(mainly SQL/Make syntax) and two unusable files: an intentionally malformed JSON
test fixture and `202610210100_unknown_season_fixture_reconciliation.sql`.
Those sources remain authoritative and must be read directly. A coverage result
of `no_recorded_issue` is best-effort, not proof of complete semantic extraction.
GUI-wide agent compliance, independent end-to-end token savings, sustained
resource use and every individual merge/rebase/pull operation remain unmeasured.

Final repository verification passed:
`env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATA_ROOT UV_NO_SYNC=1 make check integration`
(exit 0). This covered formatting, lint, strict typing, complexity, architecture,
1,762 Python unit tests (including four launcher cases), 16 Rust tests, 107
frontend tests, builds, migration validation and disposable database/API
integration. One existing frontend unused-variable warning was unchanged.
The exact configured Codex command also passed a real MCP handshake and targeted
query from a nested directory; every configured tool name exists.
