# Owner decision: authorize PitchAPI retry pilot — 2026-09-23

```text
Decision ID: AUTHORIZE_PITCHAPI_RETRY_PILOT_AFTER_TRANSPORT_STOP_V1
Status:      APPROVED — CONTROLLED TECHNICAL AUDIT
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision after the stopped PitchAPI pilot
```

The owner approved the exact continuation presented after the first pilot
stopped on `TRANSPORT_FAILURE`.

The replacement pilot may revisit the first manifest path. Its per-path
attempt counter is reset once for this new pilot. The audit retains an absolute
remaining ceiling of 700 attempts. All 688 required base paths remain
unresolved; completing them leaves no more than 12 attempts for retries.

The replacement pilot remains limited to two season manifests and ten
deterministically selected match-shot resources from each season. It must use
concurrency 1, one request/second, a 30-second timeout, one retry per path, the
existing retry delays, the second-`429` stop, and the 45-minute wall-clock
ceiling. Its local ceiling is 34 attempts: 22 base paths plus at most 12
retries.

The pilot must stop and return sanitized results before the complete audit.
Raw responses remain in memory only. No ingestion, persistent raw retention,
provider activation, corpus admission, frozen-decision change, model
implementation, Evaluation V2 execution, production forecast change, or Rust
requirement change is authorized.
