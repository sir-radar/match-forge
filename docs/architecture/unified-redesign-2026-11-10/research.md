# Research and technical experiments

Research date: 10 November 2026. Repository evidence precedes general advice.
Recommendations remain proposed until separately authorized. External sources
inform mechanisms; they do not establish MatchForge source qualification or
operating adoption.

## Questions, alternatives and decisions

| Engineering question | Existing MatchForge evidence | Primary research / applicable version | Proposed choice and limit |
| --- | --- | --- | --- |
| How to preserve identity without fuzzy admission? | UUIDs, mappings, reviewed crosswalks and prospective correction owners already exist | [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562.html), [PostgreSQL range constraints](https://www.postgresql.org/docs/18/rangetypes.html) | Extend current dated relationships; UUID generation and name similarity do not establish real-world equivalence |
| Retain unresolved observations without admitting them? | Source registration and typed V1–V3 observation artifacts are distinct from canonical resolution | [W3C PROV overview](https://www.w3.org/TR/prov-overview/) | Preserve source/entity/activity/decision links in existing records; no separate provenance platform |
| Browser push transport? | Go GET API and recurring frontend HTTP requests; no inspected event endpoint | [WHATWG EventSource](https://html.spec.whatwg.org/dev/server-sent-events.html) | SSE fits one-way committed notifications and browser reconnection; use bounded replay and exceptional snapshot recovery; WebSocket bidirectional complexity is unneeded |
| Durable cross-worker publication? | PostgreSQL transactions and shared work, no deployed event stream proven | [PostgreSQL 18 NOTIFY](https://www.postgresql.org/docs/18/sql-notify.html), [LISTEN](https://www.postgresql.org/docs/18/sql-listen.html) | Durable transaction-bound event records plus notification as wake-up hint; notification alone is not a replay log |
| Can provider polling disappear? | FotMob/PitchAPI clients are pull-based; no verified push registration in inspected code | [FotMob](https://www.fotmob.com/) publishes restrictive automation terms; [PitchAPI reference](https://pitchapi.dev/) describes read-only REST and source lineup semantics | No provider push capability verified; keep budgeted backend pull. Browser SSE cannot invent upstream webhooks. Owner research authorization is distinct from provider consent |
| Request-scoped Admin SSR? | Server page shells render client fetchers; existing local Origin/token guards | [Next.js Server/Client Components](https://nextjs.org/docs/app/getting-started/server-and-client-components), [authentication](https://nextjs.org/docs/app/guides/authentication), [data security](https://nextjs.org/docs/app/guides/data-security) | Keep Next 16.4.1, authorize close to server data access, pass sanitized initial DTOs to small client islands; test exact installed patch behavior and cache isolation |
| Match research navigation? | HTML references, inline expanded fixture and existing form/H2H/forecast views | [Soccerway](https://www.soccerway.com/), [FotMob](https://www.fotmob.com/) | Public pages expose match/league/team discovery; use date/competition navigation and integrated research, without copying designs or claiming exhaustive competitor parity |
| Safe database snapshot? | Existing baseline exporter shares `pg_export_snapshot` with `pg_dump` | [PostgreSQL 18 SQL dump](https://www.postgresql.org/docs/18/backup-dump.html), [pg_dump](https://www.postgresql.org/docs/18/app-pgdump.html) | Reuse consistent dump and exact referenced immutable files; a live filesystem copy of PostgreSQL is insufficient |
| Full versus WAL/incremental backup? | Custom dumps and prior isolated restore proof; no verified complete DR scheduler | [PostgreSQL 18 backup](https://www.postgresql.org/docs/18/backup.html), [PITR](https://www.postgresql.org/docs/18/continuous-archiving.html), [restic 0.19.1 backup](https://restic.readthedocs.io/en/stable/040_backup.html) | Start with existing dump contract plus encrypted/deduplicated file snapshots to external storage; evaluate restic in a later disposable pilot. WAL/PITR requires continuous archive/restore operations and is not the economical initial default |
| Raw compression? | Parquet already ZSTD level 9, baseline inventories gzip | [Zstandard project](https://github.com/facebook/zstd), [Arrow 25.0.1 Parquet](https://arrow.apache.org/docs/25.0/python/parquet.html) and local codec experiment below | Store new immutable compressed representations only after reader compatibility; do not alter registered source bytes or wrap already-compressed formats indiscriminately |
| APFS accounting? | `du`, filesystem free bytes and Docker sizes describe different levels | [Apple APFS snapshots](https://support.apple.com/en-ca/guide/disk-utility/dskuf82354dc/mac), [APFS FAQ](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/APFS_Guide/FAQ/FAQ.html) | Report logical/allocated/VM layers separately; directory sums cannot prove unique physical extents or snapshot savings |
| Mac wake scheduling? | Existing backend schedules and durable leases | [Apple timed jobs](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html) | Optional launchd supervision starts the existing owner; calendar wake behavior is not a durable per-window execution ledger. Never add a second domain scheduler |
| Proper model comparisons? | Existing proper scoring, chronological datasets, protected routes and explicit promotion | [Gneiting & Raftery 2007](https://doi.org/10.1198/016214506000001437), [rolling-origin validation](https://otexts.com/fpptr/tscv.html) | Reuse governed chronological paired comparisons, coverage and untouched holdout; generic monitoring metrics cannot authorize promotion |
| Go numerical replacement? | Frozen SplitMix64, serialized hashes, beta intervals and research executables | [Go math/rand/v2](https://pkg.go.dev/math/rand/v2), [Gonum distributions](https://pkg.go.dev/gonum.org/v1/gonum/stat/distuv) | Library RNG/distribution defaults do not prove frozen seed/float/artifact parity. Retain Rust; only an independently approved full comparison could support a replacement |

These are source-backed design inferences, not assertions that the cited tools
are installed, licensed for all intended provider activity, or already integrated.
No new package, cloud account, paid service or provider wrapper was installed.

## Compression experiment

Used installed Python 3.13 / PyArrow 25.0.1. Read at most eight deterministic
files per category, at most one MiB per file and eight MiB per category; larger
files contribute prefixes. Each codec ran three times sequentially in memory.
No original file was modified. Every decompressed sample matched exact bytes and
SHA-256. Timings are local medians with other services running, not throughput
SLOs or unbiased population estimates.

| Category | Sample bytes | gzip-6 bytes | ZSTD-3 bytes | ZSTD-9 bytes | ZSTD-3 encode/decode ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Operational JSON | 1,594,431 | 172,073 | 145,453 | 123,228 | 1.783 / 0.693 |
| Historical CSV | 373,154 | 109,726 | 79,237 | 70,221 | 0.913 / 0.273 |
| Parquet | 3,416,349 | 3,382,770 | 3,344,507 | 3,349,329 | 3.043 / 0.256 |
| Baseline gzip | 724,361 | 724,604 | 724,388 | 724,388 | 0.123 / 0.031 |
| Backup dump prefixes | 2,097,152 | 1,541,547 | 782,555 | 771,846 | 2.425 / 0.246 |

Process peak resident size reported by `resource.getrusage` on macOS:
108,068,864 bytes, including Python/Arrow and all buffers. This is not per-codec
peak memory. JSON ZSTD-3 saved 90.88% of sampled original bytes; CSV saved 78.77%.
Parquet saved only 2.10%; gzip grew. Dump-prefix behavior cannot predict full dump
savings. Compare complete representative archives before choosing backup encoding.

Temporary harness: `/tmp/matchforge_architecture_compression.py`; sample paths,
hashes, sizes, timings and limits are in the checksum-bound private receipt.
This proves byte round trips for the selected samples, not an archival reader,
atomic publication, interrupted recovery, cross-version compatibility or safe
eviction. Those remain implementation acceptance tests.

## Rust/Go decision evidence

Actual call graph: research binaries `pitchapi_v2_validate`, `pitchapi_v3_validate`,
`pitchapi_v4_validate`, `pitchapi_parity_investigate` and
`pitchapi_v2_benchmark` call `simulation-core` parsing, canonical serialization,
seed derivation, categorical batches, Clopper–Pearson intervals and protocol
checks. `run`, `run_v3` and `run_v4` have different frozen policy identities.
`run_for`/`run_batch_with_draws` preserve worker-independent ordering. The library
has no database/provider ownership. No direct operational Go/Python runtime call
was found in their inspected source trees; existing research CLI/evidence use is
not evidence of obsolete code.

The isolated harness copied the exact existing `SplitMix64` definition into a
temporary Rust executable and implemented the equivalent arithmetic in temporary
Go. Pinned toolchain: Rust 1.97.1 and Go 1.27.3. Seeds `0`, `1`, `u64::MAX`, eight
integer outputs and eight unit-float bit patterns each yielded **48 identical
lines** (`cmp` exit 0). Three ten-million-step checksum runs agreed at
`14918323355729563013`. Rust timings: 137.238, 39.391, 97.175 ms; Go: 24.487,
24.780, 24.180 ms. These noisy, tiny arithmetic timings do not measure the actual
simulation, serialization, beta inverse CDF, peak process memory or parallel
scheduling. No scientific corpus or frozen target was opened.

| Choice | Benefit | Cost/risk | Decision |
| --- | --- | --- | --- |
| Retain Rust | Existing frozen algorithms, tests, artifacts and parallel determinism preserved | Extra pinned toolchain/build checks remain | Recommended; no demonstrated operational need for a port |
| Full Go port | Potentially one fewer runtime language | Entire RNG/hash/JSON/tails/beta/worker parity and versioned transition; performance/memory unproved | Reject for present scope |
| Partial port | Could move a measured operational wrapper | Leaves both toolchains and two numerical paths unless bounded | No current consumer justifies it; revisit only a profiled need |

`rust/simulation-core/src/tests.rs` already exercises seeds, worker parity,
orientation, tail counts and validation. Existing test presence is not a new
successful run. A future port must use synthetic contract fixtures first, then
only independently authorized frozen comparisons; preserve old artifacts, report
bitwise versus approved numerical parity separately and never adjust thresholds
after outcomes. No production Rust or Go source was changed.

## Developer and agent workflow findings

Pins are real: Python `>=3.13,<3.14`, Go 1.27.3 and Rust 1.97.1 via
`scripts/toolchain.sh`, pnpm 10.19.0 and lockfiles. `scripts/dev.sh` loads the local
environment, runs the Go watcher and Next dev server, optionally Python/Rust
watchers, and terminates its own child processes. `make check` already includes
format/lint/type/architecture/unit/build/status/web checks; `integration` depends
on `build`. A single final `make check integration` avoids duplicate aggregate
build prerequisites. It must run with operating DB/data variables unset.

Measured documentation bytes: `AGENTS.md` 26,733; task 223,038;
`docs/architecture.md` 95,050. Loading all three consumes 344,821 input bytes
before source inspection. Exact-symbol/path searches found source owners without
starting CBM; no claim of measured CBM speedup is made. The full `.local` size scan
was materially slower than bounded source lookup; prefer registered manifests
and incremental metadata inventories for routine work.

Later DX tickets should retain safety rules, add task-to-owner/test links to the
existing guides, expose version mismatch in `doctor`, and record setup failures,
wall-clock check duration and navigation actions for the same bounded task before
and after edits. No target percentage speedup, test-count reduction, blanket
instruction rewrite or new indexing service is justified by these measurements.


I3 verified installed versions: Rust 1.97.1, Go 1.27.3 and Python 3.13.14.
Running `pnpm --version` from the repository root refused the enclosing Yarn
configuration; package-manager commands belong in `web` or the existing Make
web targets. This standalone diagnostic error did not affect the aggregate's
successful web lint/type/test/build stages. It is a working-directory caveat,
not evidence that the web package's pinned toolchain is broken.
