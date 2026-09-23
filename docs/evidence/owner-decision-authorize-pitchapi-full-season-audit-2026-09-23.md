# Owner decision: authorize PitchAPI full-season audit — 2026-09-23

```text
Decision ID: AUTHORIZE_PITCHAPI_FULL_SEASON_AUDIT_V1
Status:      APPROVED — CONTROLLED TECHNICAL AUDIT
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision after the replacement pilot
```

The owner authorized the combined PitchAPI full-season audit using 668 base
attempts and at most 10 retries within the remaining 678-attempt absolute
ceiling. Concurrency remains 1, request starts remain at least one second apart,
timeout remains 30 seconds, and execution remains capped at 45 minutes.

Both season manifests must be fetched first. Their identity hashes, expected
306/380 match counts, and deterministic twenty-match selection hashes must
match the replacement-pilot evidence before any sampled shot path is skipped.
Any mismatch stops the audit.

Raw responses remain in memory only. The audit may retain sanitized aggregate
evidence only. It does not authorize ingestion, provider activation, corpus
admission, model implementation, Evaluation V2 execution, frozen-decision
changes, provider communications, production forecast changes, baseline
removal, protected-data access, or a change to the mandatory Rust requirement.
