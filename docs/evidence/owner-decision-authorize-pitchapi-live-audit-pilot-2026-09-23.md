# Owner decision: authorize controlled PitchAPI live-audit pilot — 2026-09-23

```text
Decision ID: AUTHORIZE_PITCHAPI_LIVE_AUDIT_PILOT_FIRST_V1
Status:      APPROVED — CONTROLLED TECHNICAL AUDIT
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: authorize the exact PitchAPI request budget
```

The owner authorized at most 702 PitchAPI attempts: 688 base requests and 14
reserved retries. Execution must stop after a pilot and return control to the
owner before the remaining historical audit begins.

The pilot contains exactly two season-manifest requests and ten match-shot
requests from each of men's Bundesliga 2023/24 and Ligue 1 2022/23: 22 base
requests. It may consume the approved retry reserve subject to the existing
one-retry-per-path and second-`429` stop rules, so its hard ceiling is 36
attempts and the total audit ceiling remains 702.

The pilot must use concurrency 1, one request/second, a 30-second timeout, the
approved retry delays, and a 45-minute wall-clock ceiling. Raw responses remain
in memory only. Reports may contain sanitized aggregate evidence only.

After the pilot, the owner must receive validator compatibility results,
missing/invalid-data findings, rate-limit observations, attempts consumed, and
the exact remaining budget. The complete audit remains blocked pending a new
explicit continuation decision.

No ingestion, persistent raw retention, provider activation, corpus admission,
model implementation, frozen-decision change, Evaluation V2 execution, or Rust
requirement change is authorized.
