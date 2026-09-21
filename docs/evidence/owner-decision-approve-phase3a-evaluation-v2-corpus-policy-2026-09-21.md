# Owner decision: approve Phase 3A Evaluation V2 corpus policy — 2026-09-21

```text
Decision ID: APPROVE_PHASE3A_EVALUATION_V2_CORPUS_POLICY_V1
Status:      APPROVED
Recorded at: 2026-09-21T10:18:56Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Owner decision: freeze evaluation corpus rules
```

This append-only record captures the repository owner's direct answer to the
Wayfinder decision ticket. The owner approved Decision 2 in
`docs/governance/phase3a-xg-for-evaluation-v2-freeze-proposal.md` without
amendments.

## Decision

Freeze the qualified StatsBomb La Liga 2015/16 source as development-only:

```text
Provider scope:           StatsBomb La Liga 2015/16 (11/27)
Dataset version:          670662d6-6ed7-5fa1-ba3c-1cfd561e524f
Source snapshot:          01a08471-f763-7787-80ca-4293316b7e44
Source Git SHA:           4b73468fc5b0f1950f9f66fada70ad3a4f9327cb
Dataset manifest SHA-256: cd32d1c44620116cedefc09860efeccb91da19db4e6006ace8b8b6df1dd8e4e0
Knowledge mode:           retrospective-fixed-snapshot-v1
Evaluation V2 membership: permanently excluded
```

Freeze these minimum authoritative-corpus eligibility rules:

```text
Independent groups:       at least 3 competition-season groups
Competitions:             at least 2
Seasons:                  at least 2
Group type:               complete domestic league season
Matches per group:        at least 120
Eligible scored targets:  at least 500 total
Team history:             at least 10 prior eligible matches
Provider xG:              100% finite on retained Shot rows
Knowledge mode:           retrospective-fixed-snapshot-v1
```

Every admitted group must pass exact source/dataset identity and hash checks,
complete coverage, lifecycle and kickoff checks, point-in-time feature-history
checks, same-kickoff isolation, target-outcome sealing, and zero protected and
development-source intersection. Quarantine findings, incomplete coverage,
ambiguous identity, incompatible knowledge mode, or failed integrity make the
group ineligible.

Authorize independent source qualification as the next bounded data task.
StatsBomb Liga F 2023/24 (`182/281`), Frauen Bundesliga 2023/24 (`135/281`),
and NWSL 2023 (`49/107`) are acquisition candidates only. Catalog presence or
prior route evidence does not admit them.

The proposal file SHA-256 at approval was:

```text
ffe512464ebb404ec86116902ff1a79260d58bfd934894c8c08c9c0828b67d79
```

## Explicit non-decisions

This decision does not freeze or authorize:

- exact Evaluation V2 group membership, corpus ID, target manifest, or hashes;
- access to protected Sprint 2 EPL source, admission, or 280-target outcomes;
- use of the development source as independent evaluation evidence;
- Phase 3A implementation or fitting;
- Evaluation V2 execution or result access;
- Rust implementation, promotion, or production changes.

## Dependencies

Qualification must produce reviewable evidence for every candidate. Exact
corpus membership requires a later owner freeze after the minimum groups,
competitions, seasons, eligible targets, and firewall checks all pass.
Evaluation V2 still requires a separate run authorization after implementation
and every policy, corpus, threshold, budget, owner, artifact, and evidence hash
is frozen.
