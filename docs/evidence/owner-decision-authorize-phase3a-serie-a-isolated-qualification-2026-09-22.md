# Owner decision: authorize isolated Serie A qualification — 2026-09-22

```text
Decision ID: AUTHORIZE_PHASE3A_SERIE_A_2015_16_ISOLATED_QUALIFICATION_V1
Status:      APPROVED — RESEARCH ONLY
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Qualify independent men's Evaluation V2 sources
```

The owner approved the Italy `Europe/Rome` kickoff policy and isolated canonical
dataset and claim publication for pinned StatsBomb Serie A 2015/16 (`12/27`),
subject to full validation. The required checks are lifecycle, kickoff accuracy,
exact eligible-target counts, source hashes, and zero protected/development
intersection. This extends the earlier research-only raw-source authorization;
it does not change its source revision or allow another competition or season.

The research environment must have its own data root and PostgreSQL database.
The exact existing source files and manifests may be staged there only after
their pinned checksums pass. The governed Python ingestion, validation,
lifecycle, kickoff, and point-in-time readers must be used. Any missing or
failed integrity prerequisite fails qualification; no value may be inferred
from the structurally complete match list alone.

This decision does not freeze or admit an Evaluation V2 corpus, authorize an
Evaluation V2 run, implement the xG-for challenger, alter published forecasts,
or revisit protected Sprint 2 EPL targets or development La Liga targets.
The approved Decision 2 requirements for three independent men's groups,
two competitions, two seasons, and at least 500 eligible scored targets remain
in force. Sprint 2 remains `FAIL`.
