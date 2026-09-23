# PitchAPI live-audit pilot — 2026-09-23

Status: `STOPPED — TRANSPORT_FAILURE`

The owner-approved pilot stopped on its first manifest path after the initial
attempt and its single permitted retry both failed at the transport layer. No
HTTP response was observed, so no manifest or match-shot payload was available
to validate. No further PitchAPI request was made after the stop condition.

## Sanitized result

| Item | Result |
| --- | ---: |
| Attempts used | 2 |
| Retries used | 1 |
| Successful manifests | 0 of 2 |
| Successful shot resources | 0 of 20 |
| HTTP `429` responses | 0 |
| Minimum request-start interval | 5.027 seconds |
| Concurrency | 1 |
| Raw responses retained | No |

The minimum interval exceeds the one-second floor because the first transport
failure and five-second retry delay governed the second start. The pilot did
not reach an HTTP response, so it cannot establish real-response schema
compatibility, missing or invalid field behavior, season coverage, shot-level
xG coverage, penalty or period semantics, identifier stability, or provider
rate-limit behavior.

## Budget and continuation boundary

- Total ceiling: 702 attempts.
- Consumed: 2 attempts.
- Remaining absolute ceiling: 700 attempts.
- Nominal retry reserve remaining: 13 attempts.
- Successful required base paths: 0 of 688.
- Required base paths still unresolved: 688.

Completing all 688 unresolved base paths within the remaining 700-attempt
ceiling would leave at most 12 further retry attempts, not 13. Continuing would
also require explicit owner authority to revisit the first manifest path after
its existing two-attempt path limit and transport-failure stop. The prior
authorization does not provide that authority.

Ticket 46 remains blocked. No ingestion, persistent raw retention, provider
activation, corpus admission, frozen-decision change, model implementation,
Evaluation V2 execution, production forecast change, or Rust requirement
change occurred.

Machine-readable evidence:
`docs/evidence/pitchapi-live-audit-pilot-2026-09-23.json`.
