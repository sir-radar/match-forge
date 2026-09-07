# Model Routing

## Goal

Use the lowest-cost model that can safely complete the work.

Routing is about correctness risk, not task prestige.

## Levels

### L1 / Luna

Use for bounded, mechanical, low-risk work where requirements and contracts are already clear.

Examples:

- straightforward formatting;
- simple renames;
- deterministic boilerplate;
- small test additions for already-defined behavior;
- mechanical refactors with no contract change;
- documentation edits with no governance impact.

### L2 / Terra

Use for normal production engineering that requires judgment but does not introduce unresolved high-risk architectural, historical, statistical, or security decisions.

Examples:

- feature implementation from a frozen contract;
- normal service or repository changes;
- migrations whose semantics are already decided;
- integration work within established interfaces;
- focused performance improvements after profiling;
- ordinary reliability and maintainability work.

Default implementation model:

```text
gpt-5.6-terra
```

### L3 / Sol

Use for architecture, statistical correctness, historical correctness, governance, security, or other high-risk reasoning.

Treat a task as L3 when it affects any of:

- statistical/model mathematics;
- point-in-time correctness;
- `football_cutoff`, `knowledge_cutoff`, or `knowledge_mode`;
- historical leakage;
- same-kickoff batching;
- authoritative evaluation;
- gate policies or thresholds;
- model promotion/governance;
- MatchForge identity-resolution rules;
- bitemporal behavior;
- immutable model/forecast identity;
- security-sensitive architecture;
- difficult concurrency or transaction correctness.

A lower-tier model must not independently resolve these decisions.

## Escalation

Escalate:

```text
Luna → Terra → Sol
```

when:

- requirements conflict;
- a resolved contract is unclear;
- implementation requires changing architecture;
- the same substantive failure occurs twice;
- correctness cannot be established mechanically;
- completing the task would require weakening a test, gate, or invariant;
- an implementation path would alter a frozen decision.

Do not repeatedly retry a weaker model when the problem requires stronger reasoning.

## De-escalation

After Sol resolves architecture or ambiguity:

1. freeze the decision;
2. record it in the appropriate owner/Wayfinder/ADR/policy location;
3. return bounded implementation work to Terra or Luna where appropriate.

## Scope

Model escalation does not authorize scope expansion.

If a stronger model concludes that a resolved contract should change, surface the conflict. Do not silently change the contract.

## Task routing preflight

Before substantial implementation:

1. Break the requested work into independent concerns.
2. Classify each concern as L1, L2, or L3.
3. Identify any L3 decision that blocks implementation.
4. Resolve architecture/high-risk decisions before delegating lower-risk work.
5. Use the cheapest appropriate model for bounded implementation where the environment supports model-specific delegation.
6. Never downgrade a task merely to reduce token usage.

## Wayfinder interaction

A Wayfinder ticket's type does not by itself determine the model level.

Examples:

- a mechanical implementation ticket from a frozen contract may be L2;
- a research/grilling ticket that decides model mathematics is L3;
- a checksum-only evidence update may be L1 or L2;
- any ticket that can change an authoritative evaluation rule is L3.

Model choice never changes the ticket's authorization boundary.
