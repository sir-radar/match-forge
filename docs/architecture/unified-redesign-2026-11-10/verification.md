# Final verification and decision memo

Checkpoint I3. Investigation status: **PASS_WITH_WARNINGS**. Aggregate validation: **PASS**.
Baseline `0b83991856e9f7d6528beb2477d83a0ac27ea4fb`; branch
`ft/unified-architecture-investigation`. Recommendation: incremental existing-owner
evolution; retain Rust and the exact approved champion. ADR 0005 remains PROPOSED.

## Executed investigation

- Read-only PostgreSQL snapshots/rollbacks and separately timed GET observations;
  exact query/receipt hashes are in current-state and registers.json.
- Primary internet research, source-owner/schema/test inspection and GitHub
  confirmation of merged #178/#179/#182; no new provider-data acquisition.
- Bounded three-repeat byte compression/decompression experiment and exact
  SHA-256 round trips; two large report copies hash-identical.
- Synthetic Rust/Go RNG experiment: 48 identical output lines and matching
  ten-million-step checksums; not full simulation/scientific parity.
- Filesystem metadata inventory: four million files, no scan errors; database,
  WAL, Docker and APFS accounting limits preserved.

## Checkpoints

| Checkpoint | Commit | Scope |
| --- | --- | --- |
| I0 | `f86aec1` | Evidence/research baseline and unchanged owner companion |
| I1 | `39a4b21` | Target, storage/recovery, product/security and learning design |
| I2 | `f254008` | Acceptance/handoff and 19-phase / 40-ticket roadmap |
| I3 | Commit containing this memo; resolve with `git log -1 --format=%H -- docs/architecture/unified-redesign-2026-11-10/verification.md` | Machine-readable registers, status, final review and owner handoff |

I0–I2 were prose-only commits; per AGENTS.md §12, code checks were not run for
those checkpoints. I3 changes project-status/evidence JSON and ran the applicable final checks.
No production implementation changed.

## Final validation

The actual final aggregate completed with **exit 0**:

```sh
env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration
```

It passed Ruff formatting/lint/complexity, strict mypy (498 source files plus two
code-intelligence files), Rust format/Clippy, Go vet/lint/tests/build, Goose
validation, shell syntax, architecture/status checks and production builds.
Counts: **2,157 Python unit tests**, **16 Rust tests**, **181 web tests**,
**975 storage integration cases**, plus PostgreSQL/Redis/Go API integration.
The storage total is the successful progress-outcome count because the script's
double-quiet pytest omits the ordinary summary; every outcome is a passing dot.
Seven existing penaltyblog/NumPy deprecation warnings and one existing ESLint
unused `_input` warning in `web/components/forecast-history.test.tsx:44` remain.
No test, warning policy, assertion or gate was changed or suppressed.

Tested HEAD was `f2540089d2167379c2ffe1ede7f919b58bb5c396` with I3 documentation/
status evidence uncommitted. Production source and lockfiles remain byte-exact
against the main baseline. Final metadata/prose was then reviewed separately;
changing the evidence result does not rerun unaffected application tests.

Private full log: `.local/unified-architecture-investigation/final-check.log`.
SHA-256: `1ed5a43d6ee2d7deeb3e10f9bf380d6a2fff05af07009216228ad9ff984b1a7a`.

Existing container image/config hashes matched Compose before validation, so no
configuration-driven service recreation was needed. Storage/API scripts used
only their disposable DB names/temp roots, disabled provider schedules on the
test API, applied/retried migration `202611100200` there and cleaned up their own
targets. The 09:25 UTC read-only operating check still has migration
`202611100100`, 13 LEGACY routes, unknown running build and no operating
post-match/registry rows. Integration success is not operating rollout or a
new complete system restore claim.

Final metadata validation, source/status preservation, link/ID/phase-graph,
secret-pattern and whitespace results are recorded in the handoff evidence below.

## Final metadata and review evidence

- `make project-status-check`: **exit 0**, `ProjectStatusV2 valid`, after final
  metadata was written. Prior project-status sections compare exactly to baseline;
  only the investigation section and update timestamp are added/changed.
- `.venv/bin/python /tmp/matchforge_validate_investigation.py`: **exit 0**.
  Validates 15 foundation + 24 deferred + one excluded audit ID, nine EXT IDs,
  seven explicitly unverified future-release cases, all 16 FR issues, 15
  discrepancy records, 19 acyclic phases / 40 tickets, dependency references,
  source/input/receipt hashes, local links/cited lines and production-source/lock
  preservation. Secret-pattern findings: **zero**.
- Final metadata receipt SHA-256:
  `e7b36851405418fe8cb111501ad076fa7217307345844cf84e5af6765c620110`.
  Its two JSON input hashes bind the final register and project-status bytes.
- `git diff --check` and staged whitespace checks pass. No source, migration,
  dependency, environment, generated binary or private receipt is staged.

The first metadata audit treated a valid `filename:44` citation as a literal
filename. The corrected resolver verifies both the file and line range; the
initial FAIL is retained in `final-metadata-initial.json`, SHA-256
`7721c2798950470430042a785521c59c69ad8d44f159d273018e01bf157c14ef`. No repository check,
source contract or assertion was weakened. The separate application aggregate
already passed and was not rerun for this temporary validator correction.

Reviewed the applicable `docs/review-checklist.md` items: scope/authority,
current versus proposed state, source/time/model preservation, compatibility,
failure/rollback, source-code minimality, verification and Git delivery. No active
Wayfinder map was identified; no historical route was reopened. All remaining
source, release, restore, budget and scientific requirements are explicit future
gates, not silently accepted warnings. GitHub's handoff query for open repository
PRs returned none; no claim is made about auditing every remote branch.

## Limits and preservation

Operating mutations, operating migrations, protected source rewrites, new
scientific fits/evaluations, promotion, deployment and V2 cutover by this task:
zero. Existing unrelated backend jobs continued; no globally static database claim
is made. No `.env` values or variables were changed. Local source/backup/receipt
files and task trackers stay uncommitted; only the requested documentation,
owner-supplied companion and evidence/status metadata are deliverables.

Original source/identity/holdout/model/parity gates remain unchanged. Future tests
and plans are labelled proposed/unverified. Missing original audit wording,
source/identity proof, running release identity, complete original-file recovery,
full-system restore RTO and scientific/operating budgets remain explicit limits.
No shadow/code PASS is an operating acceptance claim.

Planning/research delivery requires the requested checkpoint commits; automatic
push/PR delivery is not required by `docs/git-delivery.md` for this mode. Push and
PR are intentionally skipped. Final commit and clean task status are verified
from Git after I3; no self-referential commit hash is fabricated in its own bytes.
