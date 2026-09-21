# Data Programme

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Tier/coverage thresholds are design inputs, not proof that any provider or competition has been qualified.** See Evaluation V2 for frozen eligibility and the protected-target firewall. `FeatureAvailabilityV1` is owned only by [its contract](../contracts/feature-availability-v1.md).

---

## 7. Data programme

### 7.1 Required coverage before advanced modelling

Qualify at least three competition-season groups with enough history to test both within-league and cross-league generalization. The exact corpus belongs in the frozen Evaluation V2 policy.

For each competition-season, measure:

- fixtures and final scores;
- kickoff-time completeness and timezone correctness;
- team identity resolution;
- event and shot coverage;
- xG/xGA availability or ability to compute xG from qualified events;
- post-shot xG/xGOT, shot-target, trajectory, and goalkeeper identity coverage;
- possession-sequence, box-entry, turnover, and territory-event coverage;
- lineup, availability, registration, transfer, and historical player-minute coverage;
- manager, stadium, travel, rest, and promotion status coverage;
- odds observation-time coverage for benchmarking only;
- corrections, conflicts, and quarantined records.

Do not represent incomplete rich-event coverage as complete competition coverage. StatsBomb Open Data contains selected competitions and 360 data only for selected matches.

### 7.2 Data tiers

```text
TIER_A: qualified event/shot data with enough semantics to build xG
TIER_A_PLUS: Tier A plus qualified event sequences and post-shot/goalkeeper semantics
TIER_B: qualified fixtures, results, and aggregate match statistics
TIER_C: contextual data such as lineups, availability, managers, venues, weather, or referees
TIER_M: market benchmark data with exact observation times
```

Forecasts must declare the tier used. A model trained on Tier A cannot silently fall back to differently defined aggregate fields.

### 7.3 Feasible context sources

Prioritize context that is stable, obtainable, and time-stamped:

- rest days and fixture congestion;
- home, away, and neutral venue;
- travel distance where venue coordinates are reliable;
- promoted/relegated team status;
- manager change date;
- competition stage and two-leg state;
- predicted or confirmed lineup when qualified;
- rivalry registry membership.

Defer weather, referee style, injuries, suspensions, and tactical formations until historical availability time and coverage can be proved.
