# V4 identity admission recovery

Outcome: **BLOCKED_WITH_EVIDENCE**. Recurrence prevention passes. The narrow
identity-correction milestone has **not passed**, and full Issue 2 cannot close.
No independently proven relationship, proof-ready approval or new canonical
admission was established. All independently executable verification is finished.

## Git and phase checkpoints

Starting SHA: `e5b9b88b33212e542ebbd98ae5558a56b41c1e46` on
`ft/v4-execution-programme`. Verified implementation SHA:
`554d09e50e8aa2af297b1d4295599cbf98b778bb`. The ending delivery SHA is the commit containing
this report and `docs/evidence/v4-identity-recovery-final.json`; resolve it with
`git log -1 --format=%H -- docs/evidence/v4-identity-recovery-final.json`.
Its exact SHA is also recorded after commit in `CURRENT_TASK_STATUS.md` and the
owner handoff.

| Phase | Status | Commit |
| --- | --- | --- |
| IDR-A | PASS_WITH_WARNINGS | `ff592523f163b6deeb7996976690808d3e83d2a8` |
| IDR-B | BLOCKED_WITH_EVIDENCE | `7082432642a1cdbfc81d5d86e1271156f924ae9f` |
| IDR-C | BLOCKED_WITH_EVIDENCE | `c22e16f436a1a252fb890fad9ba46fb1bce03acf` |
| IDR-D | BLOCKED_WITH_EVIDENCE | `676584078c582715cd199ef604bd47a89c10aff3` |
| IDR-E | BLOCKED_WITH_EVIDENCE | `554d09e50e8aa2af297b1d4295599cbf98b778bb` |
| IDR-F | PASS_WITH_WARNINGS for verification/handoff; recovery blocked | Commit containing this report; resolve as above |

Every checkpoint was committed, verified and pushed before the next phase.
The existing review PR is [#178](https://github.com/sir-radar/match-forge/pull/178).
The unrelated untracked remediation report is preserved outside these commits.

## Root cause and prospective prevention

Commit `851cf4ef01f674ec2742f8c2ede4ec8827dc6acc` introduced the StatsBomb
canonical hierarchy writer. `_insert_canonical` allocates PostgreSQL UUIDv7
surrogates; `_insert_mapping` called those source-native links `deterministic`.
The method does not establish the provider-derived origin required by admission.
All 21 original team/competition mappings reproduce this mismatch. Their bytes
and exact native IDs verify; the existing origin rejection is correct.
[RFC 9562 section 5.7](https://www.rfc-editor.org/rfc/rfc9562.html#name-uuid-version-7)
was checked alongside the original code, Git history and live SQL defaults.

New StatsBomb competition, season, team, player and match mapping rows now use
`provider_native`. One additive migration permits the method in those five tables
and mapping history. It updates no old row and grants no admission. Deploy the
migration before the updated writer. **No operating migration was run.**
The isolated upgrade preserves legacy rows/history and retries; downgrade refuses
once native-method rows/history exist and rolls its failed transaction back.

## Relationship evidence and correction limits

The pinned Reep `2026-10-31.1` artifact and complete retained bridge/redirect
checksums reverify. Its release quality gate remains false. The candidate census
is 20 teams, 344 fixtures and 601 players. The bounded detailed review covers all
20 teams, the competition case, ten fixtures, ten players and ESPN `704279`.
Provider, namespace, entity type, native ID, redirects, rule identifiers and
independence groups remain explicit.

Nineteen accepted API-Football team anchors reverify. Final read-only checks also
verify accepted API-Football competition `39` as a possible competition target.
That supplement establishes another target origin, **not** a StatsBomb relationship.
Every original team depends on 38 fixtures; competition `2` affects 380.
No canonical IDs were merged or invented.

[Reep coverage](https://reep.football/coverage/) distinguishes shared Opta-derived
feeds from independent observations and identifies bridge-only sources. Its
[public repository](https://github.com/withqwerty/reep/blob/main/README.md) documents
frozen v0 code, while the v1 engine/private case packets are not public.
Multiple bridge logos or confidence values therefore cannot supply the missing
independent relationship proof. Gender, youth/reserve identity, succession,
renaming, aliases, competing targets and competition/season scope remain explicit
negative checks; unknown proof is not relabeled as no conflict.

[Record Linkage Toolkit 0.15](https://recordlinkage.readthedocs.io/en/stable/) and
[OpenRefine](https://openrefine.org/docs/manual/reconciling) informed candidate/review
separation. No matching framework, dependency or parallel review UI was added.
The [Fans United mapping reference](https://docs.fansunitedmedia.com/reference/getfootballidmappings) does not document the required
StatsBomb offline namespace; no unrelated population or paid call was acquired.
Exact questions, versions/dates, alternatives, uncertainty and checks are in phase
evidence. This bounded search does not claim that no external proof exists.

Existing explicit crosswalk qualification requires the stored canonical target
and verified context. The reviewed team correction requires retained FDO and
API-Football mappings, an approved crosswalk and exact fixture proof. Manual
admission requires its existing reviewed fixture-bound decision. None can safely
redirect these legacy StatsBomb UUIDv7 rows unchanged. Competition admission has
distinct semantics and was not forced into the team contract.

**No new StatsBomb correction contract was implemented.** Its proof/policy
prerequisite is unmet; a proof-free contract would be speculative. The existing
FDO/API-Football correction restrictions, transactions, ordered locks, append-only
decisions, revocation and historical reads remain intact and tested.

## Resolution Center and measured qualification

All 21 live APPROVE previews remain blocked, and repeat evidence versions agree.
The existing 20-case bound and overlap checks remain active. Proof-ready cases,
owner approvals requested, actual admissions and isolated StatsBomb corrections
are all **zero**. The owner decision package is empty. Positive browser tests
exercise synthetic existing FDO/API-Football cases; they do not prove or approve
StatsBomb identities. The new StatsBomb success/concurrency/rollback matrix remains
blocked, not passed.

| Population | Before | After |
| --- | ---: | ---: |
| Source-verified legacy mappings | 21 | 21 |
| Independent canonical relationships / review-ready cases / actual admissions | 0 | 0 |
| StatsBomb canonical/time-qualified historical fixtures | 0 | 0 |
| ESPN complete canonical chains | 0 | 0 |
| Existing accepted NPFL fixtures / research goal scalars | 5 / 10 | 5 / 10 |
| Canonical player appearances / qualified minutes | 0 / 0 | 0 / 0 |
| Remaining legacy mapping proof blockers | 21 | 21 |

StatsBomb EPL `2/27` still has 380 native fixtures and no admitted canonical chain.
Original kickoff proof remains incomplete. The rechecked 380 lineup resources
contain 644 native players and 13,678 occurrences: 8,350 started, 2,099 substitute
appearances and 3,229 unknown. Unknown roles do not become nonappearances or
90-minute defaults. Canonical membership, exposure and player targets remain blocked.
ESPN `704279` retains four verified native IDs and its offset-aware UTC timestamp,
but operating team/competition mappings and its complete canonical chain are absent.

The existing API-Football NPFL pilot retains five canonical fixtures, source season
label `2027`, original admissions, UTC/epoch agreement and five regulation-score
pairs / ten research goal scalars. Two read-only audits reproduce the previous
SHA `8d1eaa95b4f62738cdeac6ba6fb81f27117a812a592a6b110b8fd859f4b014e8`.
This is retrospective label eligibility at the frozen later cutoff; it does not
establish pre-kickoff identity knowledge or sportsbook settlement equivalence.
Bookmaker-equivalent labels remain zero.

A fresh guarded experiment, `football_v4_identity_recovery_projection_20261102`,
starts with empty observation/coverage registries and publishes ten observations
and two coverage reports. Identical retry inputs preserve IDs, hashes, counts and
files. This reprojects the **existing** five fixtures; no canonical fixture fact,
identity admission or StatsBomb correction is created. The bound RESULT_1X2/HOME
diagnostic becomes RESEARCH_REQUIRED only in that experiment. Five fixtures do
not establish scientific sufficiency. Actual, isolated and unclaimed hypothetical
impact are separated in the JSON evidence.

## Verification and preservation

The final required command exits **0** at `554d09e50e8aa2af297b1d4295599cbf98b778bb`:

```sh
env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration
```

It passes 2,096 Python unit tests, strict mypy on 497 files, Ruff/format/complexity,
16 Rust tests, Go checks/tests/build, architecture/status checks, 126 web tests and
production build, 871 disposable storage tests, fresh migrations and PostgreSQL/
Redis/API integration. Focused checkpoints pass 48 prevention tests, 64 existing
correction/admission tests, 34 existing Admin/recovery cases and 15 accepted-history
boundary tests. Existing single/batch real-browser journeys pass. Final
`make project-status-check` and `git diff --check` also exit 0.

Five focused red regressions first reproduced the metadata bug. Reusing a full-suite
database retained committed concurrency fixtures and caused an intermediate
26-failed/22-passed run; a fresh isolated target passed. That intermediate raw log
was overwritten by the final fresh log, so only its observed summary/cause is
retained. Red, final green, upgrade and final aggregate logs remain available.
Three browser/restart tests initially lacked exported POSTGRES_ADDR; those failed
cases pass with normal configuration and operating DB variables removed. A local
measurement script needed PYTHONPATH=.; no domain check was changed or suppressed.
Seven existing Python warnings and one existing ESLint warning remain.

All exploratory writes use verified experimental targets or disposable test
fixtures. The experimental guard compares physical system/database identity and
checks the persistent marker. Operating connections are read-only. **Operating
writes and migrations: zero.** All 21 original UUIDs/methods/registrations/hashes
reverify. All 12,310 baseline observation files and 26 capability files verify.
Baseline row hashes retain 14,054 forecasts, 22,515 admissions, 5,230 model artifacts
and 2,475,239 mapping decisions. Source snapshots/resources grew by 15 concurrently;
no globally unchanged operating database is claimed.

Champion reload/file checksum remains
`e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
Serving stays LEGACY. Operating diagnostics remain 53 DATA_COLLECTION_REQUIRED
and 14 INSUFFICIENT_PLAYER_DATA. Protected evaluations, promotion, production
routing, cutover and legacy retirement remain untouched. No model fitting or
scientific evaluation was executed. The final review followed
`docs/review-checklist.md`; no new production helper, dependency, environment
variable, identity registry or UI was introduced.

## Owner handoff

Keep Issue 2 blocked. Obtain an independently verifiable exact relationship/source
packet for one StatsBomb team and its accepted target first; for example,
`statsbomb/offline_team/1` to `api_football/team/42`. If a bounded multi-field review
policy is preferred, it requires a separate explicit owner decision before use.
No invalid identity proposal is submitted for approval. Then implement and test
only the missing prospective correction compatibility, with competition handled
separately where its contract requires it.

Do not start Issue 5, fitting, protected evaluation, promotion, cutover or legacy
retirement. Return control to the owner here.

Final machine-readable evidence: `docs/evidence/v4-identity-recovery-final.json`.
Current project state: `docs/project-status.json`. Local progress and delivery SHA:
`CURRENT_TASK_STATUS.md`.
