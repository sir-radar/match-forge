# Evaluation V2 Policy

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Status: authorized to DESIGN/PRE-REGISTER ONLY, not to run authoritatively.** Freeze and approve every parameter below as concrete, immutable values with IDs before evaluating. Unset values are `UNSET — BLOCKING`, never silently defaults. The 280 old Sprint 2 targets are permanently excluded.

**Freeze manifest (all fields required before run):** policy ID/hash; independent corpus/exclusion manifest; target firewall and access audit; knowledge-cutoff and same-kickoff rules; minimum-history and warm-up; data tiers and horizon eligibility; models and candidate register; training/tuning/calibration/evaluation intervals; metrics and aggregation; score-tail conventions; segmentation; paired/bootstrap procedure; practical margins and threshold directions; multiplicity handling; failure/stopping rule; compute budget and responsible owner; distinct run authorization event.

**Decision statuses:** `PROMOTE_CANDIDATE`, `RETAIN_CHAMPION`, `REJECT`, `DEFER_INSUFFICIENT_DATA`, `TERMINAL_ROUTE_FAIL`. These are evidence dispositions, not production flags. A `PROMOTE_CANDIDATE` also requires separate operations and owner enablement.

---

## 12. Evaluation V2

### 12.1 Pre-registration

Freeze before an authoritative run:

```text
corpus and exclusions
competition-season groups
knowledge cutoff rules
same-kickoff batching
warm-up and minimum history
data tier requirements
forecast horizons and revision rules
reference models
candidate feature families
forbidden display-tag columns
hyperparameter budget
calibration windows
primary and secondary metrics
segment definitions
bootstrap method
promotion thresholds
latency and complexity budgets
failure and stopping rules
```

The original frozen 280 Sprint 2 targets are permanently excluded.

### 12.2 Temporal evaluation design

Use rolling-origin or expanding-window evaluation:

```text
train -> optional tuning -> calibration -> untouched evaluation
```

Requirements:

- no random match split for authoritative evidence;
- same-kickoff fixtures predicted as one batch;
- hyperparameters selected without evaluation outcomes;
- all feature snapshots materialized at the historical knowledge cutoff;
- one immutable prediction artifact per model and fixture;
- separate within-competition, future-season, and cross-competition results;
- evaluate each supported forecast horizon separately and retain every superseded forecast;
- attribute forecast revisions to point-in-time information changes without using the later outcome.

### 12.3 Metrics

Primary metrics:

- multiclass log loss for 1X2;
- multiclass Brier score;
- ranked probability score for ordered away/draw/home outcomes;
- CRPS or an approved discrete equivalent for goal distributions;
- log score for the score matrix with a defined tail policy;
- calibration intercept/slope and reliability diagrams;
- interval or prediction-set coverage and width.

Secondary metrics:

- accuracy and top-k exact-score hit rate;
- MAE for expected goals or total goals;
- discrimination/AUC for binary markets;
- sharpness conditional on calibration;
- latency, memory, artifact size, and failure rate.

Never select a model primarily by exact-score accuracy or simulated betting profit.

### 12.4 Mandatory segments

Report every candidate for:

```text
competition
season
home/draw/away
favourite-probability band
expected-total-goals band
derby versus non-derby
H2H effective-sample band
risk band
newly promoted teams
manager-change window
predicted versus confirmed lineup
forecast horizon and revision count
travel-load and rest band
lineup-continuity and lineup-impact band
retained-minutes and squad-transition band
goalkeeper post-shot coverage band
pre-shot threat coverage band
game-state-adjustment coverage
style-interaction coverage
data tier and coverage band
```

Small segments need confidence intervals and may be descriptive only.

### 12.5 Statistical comparison

- paired bootstrap at match or matchday block level;
- confidence intervals for score differences;
- pre-defined practical-equivalence margins;
- multiple-comparison control or a strictly bounded candidate family;
- stability checks across folds and competitions;
- no promotion based on one favourable segment.

### 12.6 Feature-family experiment order

Run one bounded family at a time:

1. Baseline reproduction and infrastructure validation.
2. xG-for challenger.
3. xG-for plus xGA challenger.
4. opponent-adjusted expected-performance challenger.
5. raw versus game-state-adjusted expected-performance challenger.
6. travel, rest, and fixture-load challenger.
7. dynamic state-space challenger.
8. residualized H2H challenger.
9. H2H counterfactual mean, dispersion, and correlation simulation candidates.
10. derby and volatility tag validity analysis, display-only.
11. lineup impact and continuity challenger.
12. team-plus-player strength and squad-transition challenger.
13. goalkeeper post-shot shot-stopping challenger where coverage permits.
14. pre-shot possession and territory challenger where coverage permits.
15. style and tactical interaction challenger where coverage permits.
16. forecast-diagnostic tag validation, display-only.
17. forecast-horizon and revision information-value analysis.
18. ensemble challenger.
19. independently authorized Rust simulation validation and comparison: parity/convergence first; then full-distribution real-outcome evaluation if simulation-derived forecasting is separately proposed.

Each failed family remains failed. Do not silently combine several failed ideas into a new unregistered candidate.

Display-tag analyses can validate whether a badge has honest descriptive meaning, but they cannot promote the tag into a predictive feature under this plan.
