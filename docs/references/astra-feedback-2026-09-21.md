> **Reference archive ONLY.** Exact Astra feedback supplied by the user. Its generic proposal incorrectly treats all Phase 3 research as unauthorized and does not include the later plan's mandatory Rust production gate; the updated plan reconciles those specifics with the newer supplied PLAN.

Yes. The plan is technically strong, but it is becoming too large and internally repetitive to function as an execution plan. I recommend these improvements:

\- Make \`PLAN.md\` a control-plane document rather than the source of every detailed schema and experiment.

\- Explicitly separate the immutable forecast artifact from post-forecast enrichment and display tags.

\- Add a formal decision-record and experiment-register mechanism.

\- Add a capability/promotion matrix so “research complete” cannot be confused with “production enabled.”

\- Define a canonical forecast hash to prove that tags, diagnostics, or enrichment cannot change probabilities.

\- Resolve the definition-of-done ambiguity: a forecast can be complete before optional enrichment succeeds.

\- Separate public API contracts from internal diagnostic and provenance contracts.

\- Add explicit dependency, ownership, rollback, and authorization rules.

\- Treat the current feature programme as a gated portfolio rather than an implied commitment to implement every proposed feature.

Below are replacement and supporting files.

**---**

**## \`PLAN.md\`**

\`\`\`md

**# MatchForge Implementation Plan**

*> Revision: 20 September 2026 — control-plane and artifact-boundary revision*  

*> Status: proposed replacement for the roadmap layer of the previous plan*  

*> Authority: repository evidence, frozen evaluation records, and approved decision events remain authoritative*

**## 1. Purpose**

MatchForge is a provider-neutral football forecasting and simulation platform that produces reproducible, calibrated probability distributions for football matches.

This document defines:

\- implementation sequence;

\- decision and authorization boundaries;

\- architectural ownership;

\- evaluation and promotion gates;

\- production capability boundaries;

\- repository document structure.

Detailed schemas, experiments, operational procedures, and research notes belong in versioned documents referenced from this plan.

**## 2. Non-negotiable constraints**

MatchForge must:

1\. Use only information available at the historical knowledge cutoff.

2\. Batch simultaneous fixtures to prevent same-kickoff leakage.

3\. Preserve immutable raw observations and point-in-time feature snapshots.

4\. Use one versioned feature implementation for replay, training, and serving.

5\. Evaluate changes with chronological, leakage-safe backtesting.

6\. Prefer calibrated distributions over single-score predictions.

7\. Preserve uncertainty and expose missingness.

8\. Keep display tags and diagnostics outside the forecast computation graph.

9\. Never reinterpret a failed frozen experiment as a pass.

10\. Promote only capabilities that pass both research and operational gates.

**## 3. Carried-forward status**

The following status is unchanged unless superseded by a repository decision event:

\- Phase 1B: \`PASS\`.

\- Phase 2B: \`PASS\`.

\- Sprint 2 baseline: immutable \`FAIL\`.

\- Sprint 2 decision: \`RETAIN_FAIL_AND_STOP\`.

\- The frozen 280 Sprint 2 targets remain inaccessible to new routes.

\- \`DCV3_SHARED_MATCH_PACE_MIXTURE_V1\` ended in \`TERMINAL_ROUTE_FAIL\`.

\- No model has been promoted from that route.

\- Phase 3 research requires a new owner authorization.

\- Evaluation V2 requires a separate frozen policy, corpus, threshold set, and authorization.

**## 4. Artifact boundaries**

MatchForge has four distinct artifact classes.

**### 4.1 Forecast artifact**

The forecast artifact contains:

\- point-in-time feature snapshot identifiers;

\- approved model and calibrator identifiers;

\- model-generated parameters;

\- probability distributions;

\- uncertainty and prediction intervals;

\- provenance;

\- canonical probability hash.

Once published, the forecast artifact is immutable.

**### 4.2 Enrichment artifact**

The enrichment artifact contains information calculated after the forecast artifact exists, including:

\- rivalry tags;

\- forecast-risk diagnostics;

\- model-disagreement indicators;

\- data-quality warnings;

\- historical-volatility tags;

\- reason codes.

Enrichment may fail, be delayed, or be disabled without invalidating the forecast artifact.

**### 4.3 Revision artifact**

A revision is a new forecast artifact created from a later knowledge cutoff. It must:

\- reference its predecessor;

\- preserve the predecessor unchanged;

\- record newly available information;

\- record distribution changes;

\- use a new forecast identifier.

A revision must never overwrite an earlier forecast.

**### 4.4 Post-match artifact**

Post-match shocks and explanations are stored separately. They may support later research and evaluation but cannot enter the same match's pre-match feature snapshot.

**## 5. Governing ownership**

\| Concern | Authoritative artifact |

\| --- | --- |

\| Provider semantics | Provider qualification report and adapter |

\| Team and fixture identity | Identity resolver |

\| Dataset membership | Frozen corpus manifest |

\| Feature definitions | Versioned feature library |

\| Model state | Model registry artifact |

\| Calibration | Calibrator artifact |

\| Forecast probabilities | \`ForecastArtifactV1\` |

\| Enrichment and display tags | \`ForecastEnrichmentV1\` |

\| Experiment authorization | Experiment register and decision event |

\| Promotion status | Capability and promotion registry |

\| Public response shape | Versioned API schema |

\| Operational readiness | Release record and runbook |

No implementation may create a second source of truth for one of these concerns.

**## 6. Architecture**

\`\`\`text

providers

  -> immutable raw observations

  -> provider normalization

  -> identity resolution and quarantine

  -> point-in-time views

  -> shared versioned features

  -> candidate model

  -> parameter generator

  -> calibration

  -> immutable ForecastArtifactV1

  -> optional ForecastEnrichmentV1

  -> API response composition

  -> monitoring and audit

\`\`\`

The simulator is downstream of validated forecast parameters. It must not estimate hidden team strength or repair weak forecasting inputs.

Start with a modular monolith and durable workers. Additional deployables require a documented scaling, fault-isolation, or ownership justification.

**## 7. Research policy**

Research is conducted in bounded, registered families.

Initial order:

1\. Baseline reproduction and infrastructure validation.

2\. Goals-only and dynamic-strength references.

3\. xG/xGA expected-performance features.

4\. Opponent adjustment and game-state candidates.

5\. Travel, rest, and fixture-load candidates.

6\. Residualized H2H and matchup candidates.

7\. Lineup and squad-transition candidates.

8\. Goalkeeper post-shot candidates.

9\. Pre-shot threat and territory candidates.

10\. Forecast diagnostics and display tags.

11\. Forecast horizons and revisions.

12\. Ensemble candidates.

13\. Simulation comparisons.

Each family requires:

\- a registered hypothesis;

\- a frozen candidate definition;

\- a declared data dependency;

\- an ablation;

\- a chronological evaluation;

\- proper scoring rules;

\- calibration analysis;

\- segment analysis;

\- complexity and operational measurements;

\- an accept, reject, or defer decision.

A failed family cannot be silently combined with other failed families.

**## 8. Display-only policy**

The following are display-only unless a future decision explicitly changes this plan:

\- derby and rivalry status;

\- unpredictability labels;

\- historical-volatility labels;

\- model-disagreement labels;

\- data-quality warnings;

\- OOD warnings;

\- risk bands.

These values must not enter:

\- training matrices;

\- calibration;

\- parameter generation;

\- simulation inputs;

\- probability post-processing;

\- automatic forecast revisions;

\- promotion decisions as predictive features.

The enrichment layer must be computable independently of the forecast layer.

**## 9. Evaluation policy**

Authoritative evaluation requires a frozen:

\- corpus;

\- exclusion policy;

\- target firewall;

\- knowledge-cutoff policy;

\- same-kickoff batching rule;

\- warm-up and minimum-history rule;

\- feature availability policy;

\- forecast horizon policy;

\- calibration policy;

\- metric set;

\- segment set;

\- bootstrap method;

\- promotion threshold;

\- stopping and failure rules.

Primary evaluation metrics must be proper scoring rules and calibration measures. Exact-score accuracy and simulated betting profit are secondary diagnostics only.

**## 10. Promotion policy**

A candidate may be promoted only when all applicable categories pass:

**### Scientific integrity**

\- no target leakage;

\- no same-kickoff leakage;

\- reproducible corpus and artifacts;

\- point-in-time feature audit passes;

\- evaluation targets are untouched;

\- calibration is out of sample.

**### Predictive evidence**

\- primary proper scores do not materially regress;

\- improvement exceeds the registered practical threshold or provides an approved operational benefit;

\- results are stable across folds and required segments;

\- uncertainty intervals support the decision.

**### Product safety**

\- missing-data behaviour is explicit;

\- confidence is not overstated for sparse fixtures;

\- non-H2H fixtures are not materially degraded;

\- display enrichment cannot change forecast probabilities;

\- public and internal schemas remain compatible.

**### Operational readiness**

\- latency and resource budgets pass;

\- replay is deterministic;

\- deployment and rollback are tested;

\- observability and runbooks exist;

\- backup restoration meets the approved RPO and RTO;

\- security and dependency checks pass;

\- cost budgets pass;

\- an owner records the promotion decision.

Passing research does not automatically enable production use.

**## 11. Implementation phases**

**### Phase 0 — Reconcile and authorize**

\- preserve the frozen Sprint 2 failure;

\- record the new owner decision;

\- register Evaluation V2;

\- approve architecture and ownership;

\- create the capability registry.

**### Phase 1 — Data and engineering foundation**

\- immutable raw storage;

\- provider qualification;

\- identity resolution;

\- point-in-time snapshots;

\- same-kickoff batching;

\- migrations;

\- idempotent workers;

\- artifact registry;

\- CI and deterministic replay;

\- observability, security, rollback, restore, and cost controls.

**### Phase 2 — Freeze Evaluation V2**

\- freeze corpus and policy;

\- implement references;

\- implement metrics;

\- implement target firewall;

\- run a non-authoritative dry run;

\- obtain owner authorization.

**### Phase 3 — Expected-performance research**

\- qualify xG/xGA;

\- implement opponent adjustment;

\- test multi-window features;

\- test uncertainty;

\- test game-state candidates;

\- report chronological results.

**### Phase 4 — Matchup and rivalry research**

\- residualized H2H;

\- shrinkage and decay;

\- matchup wrapper;

\- H2H counterfactuals;

\- rivalry registry;

\- matched-control descriptive analysis.

**### Phase 5 — Diagnostics and enrichment**

\- risk assessment;

\- display tags;

\- post-match shock labels;

\- parity and immutability proof;

\- API reason codes.

**### Phase 6 — Dynamic strength and context**

\- dynamic attack and defence;

\- competition and promoted-team priors;

\- travel, rest, and congestion;

\- manager-transition context;

\- objective competition-state features.

**### Phase 7 — Lineups and squad context**

\- predicted and confirmed lineup contracts;

\- lineup scenarios;

\- player and goalkeeper effects;

\- continuity;

\- squad transition;

\- strict fallbacks.

**### Phase 8 — Simulation and probability products**

\- validated parameter generator;

\- analytic parity;

\- deterministic simulation;

\- convergence and tail checks;

\- H2H counterfactual simulation.

**### Phase 9 — Production delivery**

\- immutable forecast endpoints;

\- revision history;

\- provenance;

\- dashboards;

\- shadow deployment;

\- rollback and recovery evidence;

\- governed production enablement.

**## 12. Definition of done**

A forecast artifact is complete when:

\- the fixture and teams are resolved;

\- the knowledge cutoff is explicit;

\- point-in-time eligibility passes;

\- missingness is recorded;

\- the approved model and calibrator are identified;

\- probabilities are coherent;

\- provenance is complete;

\- the artifact is immutable;

\- the canonical probability hash is recorded.

Enrichment is complete separately when:

\- the forecast artifact already exists;

\- enrichment inputs are versioned;

\- tags and diagnostics have reproducible reason codes;

\- \`forecast_effect\` is \`false\`;

\- the forecast hash is unchanged;

\- enrichment failure does not invalidate the forecast.

**## 13. Repository structure**

\`\`\`text

PLAN.md

docs/status/current-state.md

docs/governance/decision-events/

docs/governance/decision-record-template.md

docs/governance/experiment-register.md

docs/architecture/

docs/contracts/forecast-artifact-v1.md

docs/contracts/forecast-enrichment-v1.md

docs/contracts/forecast-enrichment-parity-v1.md

docs/evaluation/evaluation-v2-policy.md

docs/evaluation/promotion-gates.md

docs/operations/capability-registry.md

docs/operations/runbooks/

docs/api/openapi.yaml

docs/models/

docs/simulation/

infra/

\`\`\`

The plan defines sequence and boundaries. Contracts define exact fields. Experiment records define what was tested. Decision events define what was authorized. Evidence artifacts define what actually happened.

\`\`\`

\---

\## \`docs/contracts/forecast-artifact-v1.md\`

\`\`\`md

\# ForecastArtifactV1

\## Purpose

\`ForecastArtifactV1\` is the immutable, model-produced forecast record.

It is created before optional diagnostics, rivalry tags, or frontend enrichment.

\## Required fields

\`\`\`text

forecast_id

fixture_id

issued_at

knowledge_cutoff

forecast_horizon

supersedes_forecast_id

model_id

calibration_id

dataset_snapshot_id

feature_snapshot_id

parameter_snapshot_id

probability_distributions

expected_goals

uncertainty

data_quality_status

canonical_probability_hash

artifact_hash

code_revision

created_by_run_id

schema_version

\`\`\`

**## Probability requirements**

The artifact must include, where supported:

\- home/draw/away probabilities;

\- home and away goal distributions;

\- exact-score matrix;

\- explicit score tail policy;

\- total-goal distribution;

\- BTTS probabilities;

\- clean-sheet probabilities;

\- approved market-line probabilities;

\- expected goals;

\- prediction intervals or credible intervals.

All probabilities must be finite, non-negative, and coherent.

**## Immutability**

After publication:

\- no field may be updated in place;

\- corrections create a new artifact or correction record;

\- a revision references the predecessor;

\- the predecessor remains retrievable;

\- API responses for the same artifact are byte-equivalent after canonical serialization.

**## Canonical probability hash**

The canonical probability hash is calculated from a canonical serialization containing only forecast outputs:

\`\`\`text

home_draw_away

goal_distributions

score_matrix

score_tail

total_goal_distribution

btts

clean_sheets

approved_markets

expected_goals

uncertainty

\`\`\`

The hash must exclude:

\- request identifiers;

\- timestamps added after publication;

\- frontend tags;

\- diagnostics;

\- display text;

\- transport metadata.

**## Prohibited dependencies**

The following may not affect this artifact unless separately promoted as model inputs:

\- derby tags;

\- unpredictability tags;

\- post-match shock labels;

\- frontend risk bands;

\- unreviewed H2H information;

\- closing odds;

\- post-match cards, penalties, or errors;

\- future lineup or registration information.

**## Validation**

Publication fails if:

\- required provenance is missing;

\- probabilities are incoherent;

\- the feature snapshot is not point-in-time valid;

\- the model or calibrator is not approved for the data tier;

\- the canonical hash cannot be reproduced;

\- same-kickoff leakage is detected.

\`\`\`

\---

\## \`docs/contracts/forecast-enrichment-v1.md\`

\`\`\`md

\# ForecastEnrichmentV1

\## Purpose

\`ForecastEnrichmentV1\` contains diagnostics and frontend metadata calculated after a \`ForecastArtifactV1\` is immutable.

Enrichment is optional and must not alter the forecast.

\## Required fields

\`\`\`text

enrichment_id

forecast_id

fixture_id

computed_at

knowledge_cutoff

risk_band

risk_components

display_tags

reason_codes

evidence_snapshot_ids

tag_policy_version

risk_model_id

forecast_probability_hash

forecast_effect

schema_version

\`\`\`

**## Allowed tags**

\`\`\`text

DERBY

HISTORICALLY_VOLATILE

HIGH_FORECAST_UNCERTAINTY

HIGH_MODEL_DISAGREEMENT

OUT_OF_DISTRIBUTION

DATA_INCOMPLETE

INSUFFICIENT_EVIDENCE

\`\`\`

**## Rules**

\- \`forecast_effect\` must always be \`false\`;

\- the referenced forecast must already be immutable;

\- every tag must have reason codes;

\- insufficient evidence must not be represented as normal confidence;

\- derby status comes only from the reviewed rivalry registry;

\- derby status does not imply unpredictability;

\- post-match information cannot be used for pre-match enrichment;

\- enrichment may be delayed or unavailable;

\- enrichment failure must return the original forecast unchanged.

**## Required parity check**

Every enrichment build must compare:

\`\`\`text

forecast_probability_hash_before

forecast_probability_hash_after

\`\`\`

The values must be identical.

If the hashes differ, enrichment publication must fail and raise a high-severity integrity alert.

**## Prohibited uses**

Enrichment values must not be joined into:

\- training data;

\- calibration data;

\- parameter generation;

\- simulator inputs;

\- forecast revisions;

\- model promotion features.

**## Public API rule**

The public API may expose selected tags and reason codes, but must not expose internal diagnostic fields unless they are explicitly included in the versioned public schema.

\`\`\`

\---

\## \`docs/contracts/forecast-enrichment-parity-v1.md\`

\`\`\`md

\# Forecast Enrichment Parity Test

\## Objective

Prove that adding, removing, changing, or failing frontend enrichment does not change the forecast.

\## Test cases

For the same immutable forecast:

1\. enrichment disabled;

2\. enrichment enabled with no tags;

3\. derby tag only;

4\. uncertainty tags only;

5\. all eligible tags;

6\. enrichment failure;

7\. enrichment timeout;

8\. stale enrichment policy;

9\. changed reason-code ordering;

10\. changed frontend presentation text.

\## Required invariant

For every case:

\`\`\`text

canonical_probability_hash(case_n)

  \== canonical_probability_hash(case_0)

\`\`\`

The following must also remain unchanged:

\- model parameters;

\- simulator inputs;

\- calibrated probabilities;

\- exact-score matrix;

\- score tail;

\- expected goals;

\- forecast identifier;

\- forecast artifact hash.

**## Allowed differences**

Only these may differ:

\- enrichment identifier;

\- tag list;

\- reason codes;

\- enrichment timestamp;

\- enrichment policy version;

\- API presentation fields explicitly classified as enrichment.

**## Failure response**

If parity fails:

1\. reject enrichment publication;

2\. preserve the original forecast;

3\. disable the offending enrichment version;

4\. create an incident record;

5\. attach the failing artifact hashes;

6\. require owner review before re-enablement.

**## Automation**

This test must run:

\- in CI for contract changes;

\- in integration tests;

\- during staging deployment;

\- during production canary;

\- after every enrichment-policy change.

\`\`\`

\---

\## \`docs/evaluation/evaluation-v2-policy.md\`

\`\`\`md

\# Evaluation V2 Policy

\## Status

This policy is a template until authorized by an explicit owner decision event.

The policy must not access or modify the frozen Sprint 2 target set.

\## Required frozen values

Before an authoritative run, freeze:

\`\`\`text

policy_id

corpus_manifest_id

target_firewall_id

knowledge_cutoff_policy

same_kickoff_batching_rule

warmup_rule

minimum_history_rule

data_tier_policy

forecast_horizons

reference_models

candidate_family_registry

calibration_windows

primary_metrics

secondary_metrics

mandatory_segments

bootstrap_method

practical_equivalence_margin

promotion_thresholds

failure_rules

compute_budget

\`\`\`

**## Evaluation split**

\`\`\`text

historical training

  -> optional tuning

  -> calibration

  -> untouched evaluation

\`\`\`

No authoritative result may use a random match split.

**## Leakage controls**

The evaluator must prove:

\- all features were available at the historical cutoff;

\- simultaneous fixtures were batched;

\- later corrections were not visible before publication;

\- future lineups and registrations were excluded;

\- post-match events were excluded;

\- display tags were absent from feature and calibration matrices;

\- H2H values were constructed only from eligible prior meetings;

\- calibration did not observe evaluation outcomes.

**## Required metrics**

Primary:

\- multiclass log loss;

\- multiclass Brier score;

\- ranked probability score;

\- CRPS or approved discrete equivalent;

\- score-distribution log score;

\- calibration slope and intercept;

\- reliability diagrams;

\- interval coverage and width.

Secondary:

\- accuracy;

\- exact-score top-k rate;

\- expected-goal error;

\- binary-market discrimination;

\- latency;

\- memory;

\- artifact size;

\- failure rate.

**## Required decision outcomes**

Each candidate must receive exactly one status:

\`\`\`text

PROMOTE_CANDIDATE

RETAIN_CHAMPION

REJECT

DEFER_INSUFFICIENT_DATA

TERMINAL_ROUTE_FAIL

\`\`\`

A candidate cannot be marked \`PROMOTE_CANDIDATE\` without passing integrity, predictive, segment, and operational gates.

**## Reproducibility**

An evaluation run is reproducible only if the following reproduce:

\- corpus manifest;

\- feature snapshots;

\- predictions;

\- calibration outputs;

\- metrics;

\- confidence intervals;

\- reports;

\- decision recommendation.

All outputs must reference immutable artifact identifiers.

\`\`\`

\---

\## \`docs/governance/decision-record-template.md\`

\`\`\`md

\# Decision Record

\## Metadata

\`\`\`text

decision_id:

title:

status: PROPOSED | APPROVED | REJECTED | SUPERSEDED

created_at:

decided_at:

owner:

approvers:

related_phase:

related_experiment_ids:

related_artifact_ids:

\`\`\`

**## Decision**

State the decision in one or two sentences.

**## Context**

Describe:

\- the problem;

\- the evidence available;

\- the constraints;

\- the alternatives considered.

**## Chosen option**

Describe the selected approach and its boundaries.

**## Explicit non-decisions**

List what this decision does not authorize.

**## Invariants**

List requirements that must remain true after implementation.

**## Consequences**

**### Positive**

\-

**### Negative**

\-

**### Operational impact**

\-

**### Data and contract impact**

\-

**## Rollback or reversal**

Describe how the decision can be reversed without corrupting immutable artifacts.

**## Evidence**

List repository files, experiment reports, metrics, and checksums.

**## Follow-up actions**

\| Action | Owner | Due date | Evidence |

\| --- | --- | --- | --- |

\|  |  |  |  |

\`\`\`

\---

\## \`docs/operations/capability-registry.md\`

\`\`\`md

\# Capability and Promotion Registry

\## Purpose

The registry distinguishes research availability from production availability.

\## Capability states

\`\`\`text

NOT_STARTED

RESEARCH_ONLY

EVALUATION_READY

PROMOTION_CANDIDATE

SHADOW_ENABLED

PRODUCTION_ENABLED

SUSPENDED

RETIRED

\`\`\`

**## Required fields**

\`\`\`text

capability_id

name

description

state

owner

model_id

feature_set_id

calibration_id

policy_id

data_tier

approved_competitions

approved_horizons

last_evaluation_id

promotion_decision_id

rollback_version

enabled_at

suspended_at

suspension_reason

\`\`\`

**## Initial capabilities**

\| Capability | Initial state |

\| --- | --- |

\| Goals-only reference | \`EVALUATION_READY\` |

\| Dynamic attack/defence reference | \`EVALUATION_READY\` |

\| xG/xGA challenger | \`RESEARCH_ONLY\` |

\| Residualized H2H | \`RESEARCH_ONLY\` |

\| Derby display tag | \`RESEARCH_ONLY\` |

\| Forecast-risk diagnostics | \`RESEARCH_ONLY\` |

\| Lineup-aware forecast | \`RESEARCH_ONLY\` |

\| Simulator | \`RESEARCH_ONLY\` |

\| Automatic recalibration | \`SUSPENDED\` |

\| Derby forecast coefficient | \`RETIRED\` |

\| Frontend-tag probability adjustment | \`RETIRED\` |

**## Enablement rule**

A capability may move to \`PRODUCTION_ENABLED\` only through an approved decision event referencing:

\- evaluation policy;

\- evaluation run;

\- promotion gates;

\- deployment artifact;

\- rollback artifact;

\- owner approval.

**## Suspension rule**

A capability must be suspended when:

\- parity fails;

\- leakage is discovered;

\- calibration materially degrades;

\- required data coverage falls below policy;

\- rollback evidence is invalid;

\- provider semantics change without requalification;

\- security or licensing conditions are violated.

Suspension must not delete historical forecasts or evaluation artifacts.

\`\`\`

These changes preserve the substantive research content of the original plan while making the execution model clearer: the forecast is immutable, enrichment is downstream, experiments are registered, and production capabilities are explicitly enabled rather than implicitly assumed.
