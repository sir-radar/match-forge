# Continuous integration

The [CI workflow](../.github/workflows/ci.yml) runs on pull requests and pushes to
`main`. Classify changes runs `git diff --check`. Only pull requests whose
entire diff is prose (`.md`, `.mdx`, `.rst`) skip the test jobs. Missing
comparison commits and pushes to `main` run the full suite. Only newer revisions
of the same pull request supersede a run.

```text
Classify changes ─┬─ Python unit and coverage ────────────┬─ Deterministic checks
                  └─ Build, integration and browser checks ┘
```

`Deterministic checks` keeps the same check name and verifies both job results.
The Python job runs `make test-coverage` once with the same branch coverage
floor. The other job runs the format, lint, architecture, project status,
dependency audit, Rust/Go/frontend unit, and build checks. It builds the
frontend once and uses it for both the live integration test and the standalone
Playwright suite. The Ubuntu runners use the same pinned Python, Go and Rust
toolchains as before; the Linux Rust channel override leaves the local macOS
target in `rust-toolchain.toml` unchanged.

For local verification, run `make check integration web-e2e` in one Make process
so each build runs once. CI times the builds separately and then runs
`make integration-check` against those binaries. The storage and Go API
suites use separate disposable databases, and storage explicitly reruns
migrations to verify that nothing remains pending. Keep those checks separate
from the operating database. CI uses the pinned Compose images and removes
its test volumes after the integration step.

The locked Playwright version supplies Chromium Headless Shell and WebKit for
the existing desktop, mobile, and accessibility tests. System package and
browser installation have separate timings and deadlines. The package deadline
allows slow downloads like the two successful Nov 10 runs. DNS and stalled
connections are bounded separately; incomplete package indexes fail the step.
The small dependency advisory artifact still retains both audits for seven days.

The uv package and Python caches, Go module/build/lint caches, pinned Go tool
binaries, Rust build cache and pnpm store remain in use. Both jobs can restore
uv caches; only the build/integration job publishes them. There is no database,
credential, or frontend build cache. Browser binaries are downloaded on the
runner: in the #194 baseline they took about 13 seconds, including a headed
Chromium download the suite did not use. A browser cache would not remove the
slower Ubuntu package work.

The authoritative `make sprint2-evaluate` remains separate. CI does not change
the retained Sprint 2 `FAIL` or authorize Phase 3.

## November 2026 baseline

GitHub Actions job and step timestamps were reviewed for the newest 52 CI runs
through the #194 merge plus a Nov 3 main control. The snapshot contained 39
successful runs (four prose-only), ten cancellations, three failures, and one
still running. The 35 successful full runs below use the latest attempt.
Wall time is attempt start to last job completion. Queue is the longest
single job's creation-to-start interval per run; it does not include time
waiting for upstream jobs. p95 uses nearest rank; samples below ten show
median only.

| Successful full runs | Count | Wall median / p95 | Longest queue median / p95 |
| --- | ---: | ---: | ---: |
| All | 35 | 17m 16s / 29m 58s | 2s / 5m 03s |
| Pull requests | 26 | 17m 45s / 27m 23s | 2s / 5m 03s |
| Main | 9 | 17m 16s / — | 3s / — |
| Through Nov 10 | 18 | 16m 41s / 30m 06s | 2.5s / 3s |
| Nov 11–12 | 17 | 18m 45s / 27m 23s | 2s / 5m 04s |

1. **Serial tests dominated normal runs.** The combined Make step had a
   median of 15m 08s and p95 of 20m 29s. [PR #194](https://github.com/sir-radar/match-forge/actions/runs/43143806552)
   took 23m 11s: Python unit tests took 6m 52s, storage/API integration about
   10m 26s, and standalone browser tests about 1m 30s. Both fresh schema
   migrations finished in a few seconds. The additional storage CLI build
   in `6d8c74db` was inside the build interval; there is no isolated timing
   attributing the slowdown to that build or to the four additional Python unit
   tests versus [PR #193 main](https://github.com/sir-radar/match-forge/actions/runs/43106540085).
   Its 2,231 tests took 4m 20s, versus 2,235 tests in 6m 52s on #194.
   The [Nov 3 main control](https://github.com/sir-radar/match-forge/actions/runs/41658007260)
   ran 1,768 Python tests in 3m 38s. Nov 11's `84f9cc29` added branch coverage
   measurement and an advisory audit (1s median). Suite growth and coverage
   change are confounded; the logs cannot isolate their costs.
2. **Ubuntu packages caused the extreme tail.** Playwright setup was 48s
   median and 12m 36s p95. On Nov 10, [main](https://github.com/sir-radar/match-forge/actions/runs/42765754566)
   and [PR #183](https://github.com/sir-radar/match-forge/actions/runs/42797856865)
   spent 12m 40s and 12m 04s fetching 114 MB of Ubuntu packages. Three Nov 11
   attempts ([1](https://github.com/sir-radar/match-forge/actions/runs/43036462193),
   [2](https://github.com/sir-radar/match-forge/actions/runs/43037835303),
   [3](https://github.com/sir-radar/match-forge/actions/runs/43054672426/attempts/1))
   hit the 45-minute job limit after DNS failures for `azure.archive.ubuntu.com`.
   GitHub reported cancellation; none reached the browser downloads or tests.
   The third run passed [on retry](https://github.com/sir-radar/match-forge/actions/runs/43054672426/attempts/2)
   in 21m 16s after a 45m 55s first attempt and a roughly 20-minute gap.
3. **Runner allocation occasionally added five minutes.** The two PRs
   created around 21:19 UTC Nov 11 waited 303–304 seconds for the check runner
   ([#193](https://github.com/sir-radar/match-forge/actions/runs/43101992619),
   [P02](https://github.com/sir-radar/match-forge/actions/runs/43102010799)).
   This delay was outside the check. Runner capacity and host utilization
   during those waits were not observable from GitHub job data.
4. **Other setup was small.** Checkout was 2s median, Go/Rust cache restores
   2s/3s, uv sync 5s, pnpm install 2s, advisory upload 1s, and Compose teardown
   under 1s. In #194, Go used a lock-compatible restore, and Rust, pnpm,
   Python, and Go tools restored caches. The Go cache upload took 4s.
   The API shows about 59–63 MiB per recent Go save, 82 MiB for Rust and
   131 MiB for pnpm. The slow Nov 10 runs also restored these caches.
   There is no comparable all-cold pre-change sample. A cancelled run's
   cache miss is not a cold end-to-end benchmark.

The expected wall-time savings are the Python unit time overlapped with the
integration job, minus a second checkout, Python environment restore/sync
and final check. Extra runner time is the duplicate Python setup and final
check; runner size and paid infrastructure do not change. The historical
median includes many runs well below #194, so a 30% reduction across that
whole cohort is not implied by the #194 estimate.

## Hosted comparison

The [starting main commit](https://github.com/sir-radar/match-forge/actions/runs/43146651604)
and [first #195 run](https://github.com/sir-radar/match-forge/actions/runs/43149075566)
used Ubuntu 24.04 image 20261101.360.1, the same application and lockfiles,
and the same test commands. Both passed. The starting main run was still
in progress at the baseline snapshot and later finished in 22m 08s.

| Metric | Starting main | First #195 run |
| --- | ---: | ---: |
| Workflow wall time | 22m 08s | 10m 53s |
| Longest job queue | 2s | 2s |
| Main job dependency setup and audits, excluding Playwright and upload | 42s | 38s |
| Separate Python setup | — | 7s |
| Python unit test time from pytest | 6m 56s | 3m 08s |
| Database integration and live browser checks | 10m 06s | 7m 19s |
| Playwright setup (system packages and binaries) | 39s | 36s |
| Standalone browser checks | 1m 46s | 58s |
| Build validation | Bundled | 19s |
| Total job execution | 22m 03s | 14m 10s |

The first result was 50.8% below the starting main run and 53.1% below the
#194 PR run. The split removes serial waiting on the Python suite. The
same tests also ran faster on the candidate runners; that difference is
not credited to the split. Both runs reported 2,235 Python tests at 68%
branch coverage and 50 standalone browser tests with the same 26 skips.
The new timings show that storage and serving integration are still the
longest job. Its slowest tests exercise query cancellation, identity
qualification at scale, and a full recovery into an isolated database.

## Monitor and investigate

The separate [CI performance workflow](../.github/workflows/ci-performance.yml)
runs weekly or on demand, with read-only access. It does not run on the PR
critical path. Read its job summary or run
`python3 scripts/ci_performance.py --repo OWNER/REPO` with an authenticated
GitHub CLI (Python 3.11+). It reports PRs and main separately: job and step
timings, median and p95, queue, runner time, outcomes, rerun counts and Go tool
cache hit/miss counts. Detailed cache outcomes and package download timings
are in the original job logs.

The initial median/p95 budgets in the script are advisory. Full PR and main
targets are 15m/19m; format/lint feedback 90s/150s; Python unit 7m/9m;
Rust/Go/frontend unit 40s/90s; build 60s/100s; isolated integration 10m/12m;
standalone browser 95s/130s; longest job queue 10s/60s. They leave room for
recent comparable stage durations and flag large changes without bypassing
a test. A median warning needs five samples; a p95 needs ten. Wall and queue
budgets use first-attempt successes with the new job layout; the report
counts reruns and failures separately.

To investigate a warning, compare the same event, job, test scope and cache
state on the same runner class. Check `created_at` against `started_at`
before blaming test code. In a slow job, check restore/install, build, pytest
durations, Playwright setup/test logs, migration lines and teardown in order.
A cancellation near the job deadline needs its logs checked for timeout;
GitHub's cancellation count alone does not identify the cause. Compare
before/after wall time and total runner time across multiple attempts before
changing budgets, cache policy or runner size.
