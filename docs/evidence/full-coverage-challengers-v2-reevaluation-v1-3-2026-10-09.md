# V2 final replacement evaluation V1.3: pre-execution block

Disposition: `PREEXECUTION_DATA_INTEGRITY_BLOCK`. Scientific evaluation did not start.
All target outcomes remain sealed. No winner, comparative metrics, confidence intervals,
or production promotion can be inferred from this rehearsal.

## Owner decision required

The frozen ensemble assigns 0.8126236786545866 weight to the champion.
For champion-ineligible targets, only 0.18737632134541342 trained weight remains,
below the frozen 0.5 minimum. Its fallback requires the unavailable champion.
Substituting the competition prior or changing weights is not authorized.

The static rehearsal also cannot forecast 273 targets designated eligible using
sequential identity counts. Their earlier selected targets' outcomes remain sealed.
This is not evidence that those sequential forecasts would fail or pass; under
the required 100% readiness gate it is a pre-execution block.

No targets were dropped after rehearsal. The 750-target manifest is unchanged.
Owner must resolve frozen ensemble semantics and static/sequential readiness
before any later execution authorization. Do not reopen V1.2.

## Required final report

1. Branch: `ft/canonical-history-integrity-v2-final-evaluation`.
2. PR #158 merged: YES, merge `f19c3dcb2ec515da6ac76c2305197a4798aeb7bc`.
3. SOURCE_COMMIT: `6b0246c3d964f63e4af4bbfb921508e89e35a074`.
4. EXECUTION_COMMIT: NOT CREATED. The following commit records blocked evidence,
   not an executable preregistration.
5. Frozen V2 artifact SHAs: verified byte-for-byte by runtime loading:
   - ensemble: `d61625324300e310b8c1d8e7e2f4df86bb55f218e4b3735486dc391765f5387c`
   - Dixon-Coles: `62041a5c67c5673e173368986c1c9f9c3e57ac4f15ac4e1e7a6d292723ea3b27`
   - negative binomial: `e5d87b998a80e03b2aae730c8b1782826aacf4a0fad1f7345d03b6a8a92e863b`
   - Weibull copula: `93c8fb0ae16bb166b4fb537280fc2ba9ea178f55cf58236aed6db57b261f2763`
6. Canonical audit: 330,643 raw rows; 318,041 admitted real fixtures; 798 exact
   duplicate clusters; 300 resolved duplicate clusters; 241 ambiguous clusters;
   11,549 impossible-timeline clusters; 11,790 total quarantined clusters;
   314 duplicate alias rows collapsed; 12,288 source rows quarantined.
   Unresolved admitted timeline conflicts: 0.
7. Known OpenFootball pair:
   `10151aeb-0deb-57e1-9d36-22aa6f7b2d9e`,
   `ddfe2ee5-c301-58e4-89dc-710a2170695b`.
   Real fixture `5cf5d17f-1ec4-5404-9854-b9cfe9df8aec`:
   `AMBIGUOUS_QUARANTINED`,
   `COMPETITION_IDENTITY_CONFLICT_NO_UNIQUE_PROVIDER_SUPPORT`.
   Arsenal Tula–Dinamo Moskva, 2019-07-12 17:00 UTC, 1–1 in both retained
   sources; conflicting `ru.1` / `ru.2` identities. Snapshot
   `7389bfe6-2d25-5b4c-b51e-e8f22e159c6d`; source revision
   `e6744429ee395bc86f247348c6184bb08d4eb361`.
   Evidence SHA `da718c45956ebeae541021716eddd223bb3ed121b7c2bbe463057abaf8abff72`.
   Complete resource hashes and facts are in the audit JSON.
8. Resolved-history manifest: `docs/evaluation/resolved-history-manifest-v1.json`,
   contract `MatchForgeResolvedHistoryManifestV1`, 11,763 rows;
   SHA `51fab6acb33d1c767d118834a6d1c88186117c6e643958614bb440b5514da399`.
9. Global forbidden targets: 8,586;
   SHA `a2bf2443d46a81f71f9b4a9adf8e3e7767f047909a8894608e6703b6a1e68d9b`.
10. Fresh HOLDOUT: 750, Eredivisie / J3 League / Brazilian Serie A, 250 each.
    Seasons: 2021/2022 (13), 2022/2023 (162), 2023/2024 (226), 2024/2025 (95),
    2025 (250), 2025/2026 (4).
    SHA `0cbdda69bf819311efe613c0d5a2f6523ceb7061622cf5f6d84ab792557c80a0`. Forbidden overlap: 0.
11. Champion eligible: 450.
12. Champion ineligible: 300; away insufficient 39, both insufficient 217,
    home insufficient 44.
13. Native cold-start expected: 0 across every required V2B model; floor 100 FAIL.
    Three models have 177 validated cold-start routes; Weibull has 177 champion fallbacks.
14. Readiness: FAIL; 750 targets, 11,763 history rows; 750 snapshots and Elo ready;
    177 compound reference/V2A/V2B forecast sets validated.
    573 target failures (300 ensemble precondition, 273 static champion forecast)
    plus one aggregate cold-start-floor failure = 574 unresolved failures.
    The 300 ineligible targets stop before reference/model prediction.
15. Target real-fixture duplicates: 0.
16. Target team/timestamp conflicts: 0.
17. Qualification/runtime history-count parity: synthetic shared-history regression
    PASS; full scientific runtime parity NOT PROVEN. Static histories exclude
    all sealed targets; sequential metadata counts can include earlier selected identities.
18. Target outcome access before forecast: 0 columns selected, 0 getter calls.
19. Execution: outcomes loaded false; logical executions 0.
20. V2A STRATUM A coverage/metrics: NOT RUN.
21. V2B STRATUM A vs champion metrics/CIs: NOT RUN.
22. V2B STRATUM B vs competition prior metrics/CIs: NOT RUN.
23. Overall V2B vs ReferenceStackV1 metrics/CIs: NOT RUN.
24. Validated rehearsal routes only (not scientific coverage):
    ensemble, Dixon-Coles and negative binomial: COLD_START_BOTH 177 each;
    Weibull: CHAMPION_FALLBACK 177.
25. Low-history results: NOT RUN.
26. Promoted-team results: NOT RUN.
27. Per-domain results: NOT RUN.
28. Development winner: NONE.
29. Final disposition: PREEXECUTION_DATA_INTEGRITY_BLOCK.
30. Independent evaluation available: NOT ASSESSED; search not triggered because
    development did not pass. Do not infer availability.
31. Production champion changed: NO.
32. Verification:
    - `make canonical-history-audit`: PASS, retained audit/resolutions persisted.
    - `make check integration`: PASS, 856 Python tests, 15 Rust tests,
      21 web tests, Go tests; lint/type/build and fresh database migrations/
      canonical storage/operational integration passed.
      Seven upstream penaltyblog NumPy deprecation warnings remain; no test failed.
    - Final scoped checks: 20 fixture/protocol tests and 21 project-status tests
      PASS; affected-file Ruff/mypy PASS.
    - `make project-status-check`: PASS before recording the blocked track;
      repeated on the final evidence state.
    - `make v2-final-readiness`: expected FAIL at the protected readiness gate;
      all 750 targets visited, execution state not consumed.
    - `make v2-final-evaluate`: NOT RUN.
    - `git diff --check`: PASS before evidence commit.

## Diagnostic count caveats

The emitted rehearsal's `duplicates_collapsed` and `quarantined_history_rows`
each contain 12,602 aggregate excluded rows. They are not separate quantities
and must not be added. Quarantine manifest derivation gives 314 collapsed aliases
and 12,288 quarantined source rows, summing to 12,602.

The emitted `competition_prior_readiness_count` is 177 successful compound
forecast sets, not proof that all competition-prior reference predictions were
tested. Assigned reference routes (450 champion / 300 prior) are metadata counts.
Snapshot/Elo readiness does not imply model or reference readiness.

V1.2 remains FAIL_CLOSED_PROTOCOL_VIOLATION with outcomes loaded true and
one logical execution. No prior result or consumed target was reused.
