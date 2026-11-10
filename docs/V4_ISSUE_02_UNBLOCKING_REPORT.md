# V4 Issue 2 unblocking report

Outcome: **PASS_WITH_WARNINGS** for the bounded historical-label milestone.
Full Issue 2 and V4 acceptance remain **BLOCKED_WITH_EVIDENCE**.

1. **Starting SHA:** `eb4f8104da3070b3a58a64755fdcc88b5d8419d1` on `ft/v4-execution-programme`.
   Task reference `851790f` differs only by the owner engineering-guide commit.
2. **Ending SHA:** the commit adding this report and final JSON. Its exact SHA
   is recorded in `CURRENT_TASK_STATUS.md` and the final handoff. The verified
   implementation SHA is `c0184125a9c9d2c579e23e602e16ee438577c8e3`.
3. **Phase commits:**

| Phase | Commit |
| --- | --- |
| R02-G | `30f24c44a007961771b379f3fee8da15fb7979f5` |
| R02-H | `37295332a04963a8de310d3d541c3b95dfff7b9a` |
| R02-I | `960ce949596519df346a66e7139e0c55bf8c5263` |
| R02-J | `a42825cfdbc8890e1928251294c00cdb9d8c4a2f` |
| R02-K | `d5c848142ba99f25616a7499d8796ad1ff2e660f` |
| R02-L | `2d9a8a355d142a33f860ab2d3380e5e61e429118` |
| R02-M reader correction | `c0184125a9c9d2c579e23e602e16ee438577c8e3` |
| R02-M final evidence | Commit adding this report; resolve with `git log -1 --format=%H -- docs/evidence/v4-issue-02-unblocking-final.json`. |

4. **Internet research:** official [StatsBomb resource layout](https://github.com/statsbomb/open-data),
   [Reep data](https://www.reep.football/data/),
   [SportsDataverse Football-Data UK reference](https://py.sportsdataverse.org/docs/soccer/reference/football_data),
   and [API-Football v3 documentation](https://www.api-football.com/documentation_v3).
   Exact questions, retrieval dates, observed versions, alternatives and remaining
   uncertainties are in the root-cause and qualified-target evidence. Live ESPN
   access was unavailable; its actual retained registered summary supplied proof.
   Football-Data UK notes returned HTTP 429. No broad acquisition or Reep upgrade ran.
5. **Verifier root causes:** StatsBomb/ESPN exclusion and unsupported native shapes
   hid a real source-reader gap. Generic legacy reading hashed StatsBomb manifest
   bytes against a resource checksum. Source verification is separate from target trust.
6. **Formats corrected:** StatsBomb competition indexes, scoped match indexes,
   lineups and exact ESPN summaries. Existing native parsers and one shared
   manifest/resource reader enforce hashes, resource paths, namespaces and shapes.
   Duplicate JSON keys and players assigned to both sides are rejected.
7. **Origin UUID findings:** all 21 original StatsBomb owner mappings point to
   database-generated UUIDv7 values. Ingestion's `deterministic` method does not
   establish a supported deterministic UUID origin. The origin allowlist is unchanged.
8. **Original provenance:** the retained EPL index at revision
   `b0bc9f22dd77c206ddedc1d742893b3bbe64baec` and SHA
   `e07d6d360b30e0cd17f9aeea0db1502d2a5666d298f1b44b83a2d2f21ba3d21b`
   verifies. Mapping IDs, manifest/resource hashes and exact source records remain pinned.
9. **Reep bridges:** reuse release `2026-10-31.1` and the immutable Issue 4
   candidate artifact. Bounded review covers 20 teams, ten matches, ten players,
   one ESPN fixture and a separate competition check. Nineteen accepted API-Football
   team anchors exist. Release quality remains false; bridge relations remain candidates.
10. **Proof-ready Resolution Center cases:** zero. All 20 current team APPROVE
    previews and the competition preview reject admission. Exact evidence versions
    and permissible actions are in `v4-issue-02-crosswalk-proposals.json`.
11. **Owner approvals:** none requested for rejected proposals. Independently
    qualified source-to-target evidence must precede consequential review through
    Resolution Center. No parallel approval workflow was added.
12. **Actual canonical admissions:** zero. No UUID, old decision or published fact
    was rewritten. Existing accepted target anchors and fixtures were reused.
13. **Track A:** 380 native StatsBomb fixtures, 21 now source-verified owner checks,
    zero complete admitted canonical/time chains. Origin/target and kickoff proof remain.
14. **Track B:** ESPN `704279` has four source-verified identifiers and native UTC.
    Its canonical competition/team/fixture chain remains absent.
15. **Track C:** five existing accepted API-Football NPFL fixtures, native
    competition `399`, source season label `2027` preserved verbatim. Exact retained
    rows, 15 accepted entity checks, fixture origins and R2 history decisions verify.
    The original CSV and StatsBomb alternatives were inspected; no name/date/score join
    or anonymous-record admission was invented. FBref has no exact accepted bindings
    to these selected fixtures.
16. **UTC:** five existing UTC-qualified fixtures reverified by matching offset-aware
    dates, explicit UTC metadata, Unix epochs and accepted history. New UTC claims: zero.
    England/Spain/Italy StatsBomb policies and pinned tzdata `2026.3` were inspected,
    but their existence did not qualify the original naive-time pilot.
17. **Source-native labels:** ten FT and ten HT goal scalar fields already existed.
    No new football facts were acquired. Corners/cards/shots/SOT are not supplied
    by these selected fixture resources.
18. **Research-qualified labels:** five regulation score pairs / ten goal scalars,
    under unchanged `ResultObservationV2 / FINISHED / REGULATION_90` semantics.
    Source FT, elapsed 90, fulltime/goals equality and absent extra-time/shootout
    values are checked against exact accepted history. The ten HT values remain
    source-native; no separately qualified period-target output is claimed.
19. **Bookmaker-equivalent labels:** zero. Research compatibility is explicit;
    no sportsbook settlement equivalence or publication permission is inferred.
20. **Players:** 644 native IDs verify across 380 lineups and 13,678 occurrences.
    Native roles: 8,350 started, 2,099 substitute appearances, 3,229 unknown.
    The 15 multi-team cases remain individual review candidates. Retained samples
    have 27 FBref and four Sofascore reported-minute occurrences; ESPN/Understat
    samples have no reported minutes. Canonical player identities, appearances,
    exposure, continuous memberships, transfer dates and player target labels remain zero.
21. **Market readiness:** the existing isolated diagnostic changes the bound
    `RESULT_1X2 / HOME` target from `DATA_COLLECTION_REQUIRED` to `RESEARCH_REQUIRED`
    with `RESEARCH_COMPATIBLE_ONLY`. This is one experimental bound family/input
    result, not scientific history sufficiency. Operating diagnostics remain
    53 `DATA_COLLECTION_REQUIRED` and 14 `INSUFFICIENT_PLAYER_DATA`.
22. **Tests:** final aggregate command below exits `0`. It includes
    2,092 Python unit tests, strict mypy on 497 files, 16 Rust tests, Go checks,
    126 web tests/build, 865 disposable storage tests and PostgreSQL/Redis/API
    integration. Focused identity/Resolution Center integration: 51 passed.
    New tests: 23 native-identity cases and 15 accepted-history boundary cases.
    Seven existing Python dependency warnings and the existing ESLint warning remain.
    The initial aggregate failed three missing-source diagnostics after the shared
    reader moved. Correction `c018412` restores its prior ValueError contract.
    Four new regression cases and all three failing integration cases pass.
    The complete aggregate was rerun after the correction; no gate was weakened.
    Final `make project-status-check` and `git diff --check` pass.
    Exact logs/receipts and focused red/green commands are in phase evidence.
23. **Isolation/preservation:** final target
    `football_v4_unblocking_r02_replay_20261102` passes system-identifier/database-OID separation
    and the persistent experimental marker. Ten native observations and two
    coverage reports register identically twice; no duplicate files or rows.
    Canonical-resource resolutions/admissions remain zero. Coverage registration
    knowledge stays separate from the frozen label cutoff. Both read-only audit
    invocations produce SHA `8d1eaa95b4f62738cdeac6ba6fb81f27117a812a592a6b110b8fd859f4b014e8`.
    All 12,310 baseline observations and 26 capability artifacts verify. All baseline
    row hashes remain present, including 14,054 forecasts, 22,515 admissions and
    5,230 model artifacts. Concurrent operating additions are disclosed in final JSON.
    The champion remains `e856dedf1879135eea547ac00d7e6243621dd6ff5c59164c6697131e22e46eb4`.
    Operating writes/migrations: zero. Serving remains LEGACY; cutover controls,
    promotions and protected evaluation execution are untouched.
24. **Unresolved decisions:** exact StatsBomb/ESPN source-to-target relationships,
    applicable original kickoff proof, canonical player/fixture identity, exposure
    and target-specific void/settlement rules. Scientific thresholds and evaluation
    authorizations were not changed or invented.
25. **Narrow milestone:** passed with warnings. The usable population reuses five
    previously accepted fixtures and proves their source/native/canonical/time/target
    chain; it does not claim five newly admitted football matches.
26. **Full Issue 2 closure:** not legitimate. Broader historical and player
    requirements remain unresolved. Earlier Issue 2/3/4 reports are unchanged.
27. **Later Issue 5:** the bound result target now has a concrete research-compatible
    input path. Five fixtures do not establish frozen scientific sufficiency; no study,
    model fitting, protected evaluation, promotion or publication is authorized here.
28. **Next action:** owner handoff. Preserve this bounded research-only pilot.
    Obtain exact independent identity relationship evidence before submitting valid
    Resolution Center proposals. Any later scientific protocol requires separate
    authorization. Stop; do not start another map, phase, provider route or cleanup.

Measured comparison (units and limits are specified in final JSON):

| Metric | Before | After |
| --- | ---: | ---: |
| source identifiers verified in new extractors | 0 | 669 |
| preexisting reep candidate records in bounded review | 41 | 41 |
| proof ready identity cases | 0 | 0 |
| new canonical identity admissions | 0 | 0 |
| existing selected canonical fixture bindings | 5 | 5 |
| new canonical fixture resolutions | 0 | 0 |
| existing selected utc fixtures | 5 | 5 |
| existing selected historically eligible fixtures | 5 | 5 |
| canonical fixtures in new experimental qualified coverage | 0 | 5 |
| retained source native ft and ht goal scalars | 20 | 20 |
| research qualified goal scalars in new experimental projection | 0 | 10 |
| bookmaker equivalent labels | 0 | 0 |
| qualified canonical player identities | 0 | 0 |
| native started or substitute occurrences | 10449 | 10449 |
| verified canonical player appearances | 0 | 0 |
| verified canonical minute exposures | 0 | 0 |
| qualified continuous membership intervals | 0 | 0 |
| experimental bound market families with research required diagnostic | 0 | 1 |
| remaining original statsbomb owner mapping blockers | 21 | 21 |

Reproduce the read-only frozen audit with the existing retained source root:

```sh
set -a
. ./.env
set +a
. ./scripts/toolchain.sh
uv run --locked --no-sync python -m scripts.inspect_v4_accepted_history \
  --database-url "$DATABASE_URL" \
  --source-root .local/football-data \
  --pilot docs/evidence/v4-issue-02-canonical-pilot.json \
  --pilot-sha256 f0ac014d7e1194715f8d6e1fe1ce5f236439410f12f26bc460f61b09d3ccd99d \
  --artifact-root .local/shadow-v4/unblocking-r02
```

Final comprehensive verification:

```sh
env -u DATABASE_URL -u TEST_DATABASE_URL -u FOOTBALL_DATABASE_URL -u FOOTBALL_DATA_ROOT make check integration
```

The first isolated measurement expected the wrong market diagnostic and stopped
only after safe publication. Its baseline receipt was incomplete. A fresh guarded
experimental database supplied the final zero-to-ten observation / zero-to-two
coverage baseline and repeat. The initial database is retained separately; no
production gate or output was changed to satisfy the measurement.

Machine-readable result: `docs/evidence/v4-issue-02-unblocking-final.json`.
Current project state: `docs/project-status.json`.
