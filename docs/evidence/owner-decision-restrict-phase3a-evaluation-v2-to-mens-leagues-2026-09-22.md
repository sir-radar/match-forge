# Owner decision: restrict Phase 3A Evaluation V2 to men's leagues — 2026-09-22

```text
Decision ID: RESTRICT_PHASE3A_EVALUATION_V2_TO_MENS_LEAGUES_V1
Status:      APPROVED
Recorded at: 2026-09-22T03:05:08Z
Owner:       repository owner / sir-radar
Map:         phase3a-xg-for-evaluation-v2-freeze
Ticket:      Qualify independent Evaluation V2 source candidates
```

Asked whether women's domestic leagues should be in scope for this xG-for
experiment if they pass every frozen data and integrity rule, the repository
owner answered: “No—restrict to men’s leagues.” This settles the product-scope
review left open for the three acquisition candidates in approved Decision 2.
It does not amend Decision 2's group, coverage, target, source, time, or
integrity rules.

StatsBomb Liga F 2023/24 (`182/281`), Frauen Bundesliga 2023/24 (`135/281`),
and NWSL 2023 (`49/107`) are excluded from this experiment before full data
qualification. They cannot be admitted by passing xG or other checks. The
[candidate screen](phase3a-evaluation-v2-source-candidate-screen-2026-09-22.md)
records their exact available source metadata and `FAIL_PRODUCT_SCOPE`
dispositions. No men's group is approved by this decision.

The proposal file SHA-256 before recording this decision was:

```text
5e26a36f33890f295ad15fbb9dbd0c96f77425bb361fe7f4d4a1c1944b71b681
```

The authoritative corpus remains unfrozen. Source qualification still needs
three independent men's domestic-league season groups from at least two
competitions and two seasons, with at least 500 eligible scored targets under
Decision 2. The result-disposition conflict and pre-registration freeze also
remain open. This decision does not authorize protected EPL access, xG-for
implementation, Evaluation V2 execution, Rust work, promotion, or production
changes. Sprint 2 remains `FAIL`; published forecasts and goals-only baselines
are unchanged.
