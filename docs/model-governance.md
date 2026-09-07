# Model Governance

## Purpose

This document defines durable rules for model fitting, artifacts, forecasts, calibration variants, evaluation evidence, challenger progression, failure handling, and promotion.

Model-specific mathematical contracts belong in versioned model policies, ADRs, schemas, or resolved owner/Wayfinder decisions.

This document defines durable governance behavior. It does not replace current project-status records, active Wayfinder authorization, model-specific policies, or executed evidence.

---

## Baselines and Challengers

Approved simple baselines remain the reference for their phase.

A more complex model must demonstrate additional value under compatible, leakage-safe, out-of-sample evaluation.

A valid result is retaining the simpler model.

Do not promote a model because it is more flexible, realistic, or sophisticated.

Complexity must earn its place.

---

## Model Identity

Keep these concepts separate:

```text
fit execution
logical fitted state
model artifact
human-readable label
promotion event
forecast
evaluation
```

A fit execution identifies an attempt.

The logical fitted state identifies the mathematical result.

A retry is another execution, not automatically another logical model result.

A new artifact is justified only when the governed fit specification or resulting logical fitted state differs according to the active contract.

---

## Fit Specification

A governed fit specification should bind the applicable:

- model family;
- algorithm version;
- configuration checksum;
- point-in-time dataset identity;
- source/dataset lineage;
- feature versions;
- training cutoff;
- knowledge cutoff;
- knowledge mode;
- quality policy where applicable;
- random seed where applicable;
- code Git SHA;
- dependency lock.

A frozen challenger may not silently change any of these after validation, admission, or authoritative results are observed.

---

## Fit Identity and Retry Convergence

Equivalent governed fit specifications must converge on one logical fitted-artifact identity.

Conceptually:

```text
same model family
+ same algorithm version
+ same configuration
+ same governed training data
+ same cutoffs
+ same feature contract
+ same code/dependency identity where required
= same logical fit identity
```

Caller-supplied UUIDs, retries, worker IDs, or execution IDs must not create multiple logical model artifacts for the same deterministic fit specification.

Where concurrency is possible, persistence constraints and coordination must make competing equivalent fits converge on one semantic result.

A fit execution ID may differ across attempts.

The logical fitted-artifact identity must not.

---

## Fitting Failures

Fail explicitly on:

- invalid inputs;
- impossible parameter state;
- optimizer failure;
- non-convergence;
- unsupported contract version;
- NaN or infinity;
- invalid probabilities;
- failed identifiability criterion where defined;
- failed deterministic-reproduction requirement where defined.

Do not silently fall back to a simpler parameter value unless the mathematical contract explicitly defines that boundary behavior.

Do not silently change the objective, optimizer, tolerances, parameter bounds, initialization, regularization, training window, or other frozen fit behavior after observing a failed governed result.

---

## Probability Contract

Related goal products must derive from one coherent joint score distribution.

Required products may include:

- exact scores;
- compact score buckets;
- 1X2;
- total goals;
- over/under;
- BTTS;
- clean sheets.

`5+` means five or more, not an exact score.

Every emitted probability must satisfy:

```text
0 <= p <= 1
```

Required probability families must normalize within the approved tolerance.

Do not silently clip materially invalid values.

Do not silently renormalize an invalid distribution unless the frozen mathematical contract explicitly requires and justifies it.

Numerical repair must never hide a mathematically invalid model state.

---

## Model Artifacts

Published fitted artifacts are immutable.

Every authoritative artifact must include or resolve the applicable:

- model family;
- algorithm version;
- artifact schema version;
- serializer version;
- loader version where independently governed;
- configuration;
- training dataset version;
- source/dataset lineage;
- feature versions;
- football cutoff;
- knowledge cutoff;
- knowledge mode;
- quality policy where applicable;
- code Git SHA;
- dependency lock hash;
- physical file checksum;
- physical byte size where applicable;
- logical model-state checksum;
- runtime compatibility declaration where required;
- feature-contract compatibility declaration;
- loader compatibility declaration where required.

Prefer transparent, portable formats such as JSON or Parquet.

Do not use pickle, joblib, or cloudpickle as the canonical production format.

Corrections or refits create new artifacts.

Published bytes, manifests, lineage, and configuration do not change.

---

## Logical and Physical Identity

Maintain distinct identities for logical fitted state and stored physical bytes.

Where physical writers can produce byte-different but mathematically equivalent files, record both:

- logical checksum of the canonical fitted state;
- physical checksum of the stored artifact.

A deterministic semantic refit with identical governed inputs should reproduce the same logical model state within the approved numerical rules.

Physical identity may differ only where the storage/serialization contract explicitly allows byte-level variation.

Never use physical byte identity alone as proof of model equivalence when the contract defines logical state separately.

---

## Artifact Loading

An authoritative artifact loader must fail closed unless it verifies the applicable:

- manifest checksum;
- state-file checksum;
- artifact schema version;
- serializer compatibility;
- loader compatibility;
- algorithm compatibility;
- runtime compatibility where required;
- feature-contract compatibility;
- dataset/model-state compatibility where required;
- logical model-state checksum.

Do not return partially verified fitted state.

Do not bypass compatibility checks merely because the artifact can be parsed.

If the loader cannot establish that the artifact satisfies the active contract, loading fails.

---

## Serialize, Reload, and Reproduce Before Forecast Publication

Before an artifact is used for authoritative forecast publication, the system must verify that the serialized artifact can be reloaded and reproduces the expected fitted state or predictions within the approved tolerance.

Conceptually:

```text
fit
→ serialize
→ checksum
→ unload
→ reload
→ verify compatibility
→ reproduce state/predictions
→ compare within approved tolerance
→ publish authoritative forecast
```

A successful in-memory fit is not enough.

An artifact that cannot be reloaded and reproduced must not be used for authoritative forecast publication.

Retain the applicable reload/reproduction evidence in the owning evaluation or artifact evidence.

---

## Forecast Identity

Every persisted forecast must bind exact immutable inputs, including as applicable:

- target MatchForge match ID;
- forecast time;
- football cutoff;
- knowledge cutoff;
- knowledge mode;
- forecast context identity/checksum;
- exact primary model artifact IDs;
- calibration artifact IDs where applicable;
- probability contract version;
- forecast output version;
- payload checksum.

Resolve mutable aliases before forecasting.

Never persist only:

```text
latest model
current baseline
latest Dixon-Coles
```

Historical forecasts must not change when an alias later moves.

Use this rule:

```text
aliases may move
artifact identities may not
```

Target outcomes remain separate from forecast payloads.

---

## Forecast Identity and Retry Convergence

Equivalent forecast requests must converge on one logical forecast identity.

Conceptually:

```text
same target
+ same forecast context
+ same exact artifact set
+ same calibration artifacts where applicable
+ same probability contract
+ same output specification
= same logical forecast identity
```

Caller-supplied UUIDs, retries, workers, or execution IDs must not create multiple logical forecasts for the same semantic forecast specification.

Persistence must make identical retries converge.

A retry must never mutate a previously published immutable forecast payload.

---

## Partial Publication Recovery

Partial artifact or forecast publication must be recoverable without mutating already published immutable bytes or creating a second logical object for the same identity.

If file/object publication succeeds before relational registration, or relational work is interrupted after immutable bytes exist, retry must reconcile the existing valid publication.

Retry must not regenerate conflicting metadata or bytes merely to make the publication appear new.

Where timestamps or manifest metadata are part of immutable identity, recovery must preserve the original published identity rather than manufacture replacement values.

All artifact/forecast publication paths must define safe retry behavior for:

- publication succeeds, registration fails;
- registration transaction rolls back;
- process dies between publication steps;
- duplicate concurrent workers;
- checksum conflict;
- partial/corrupt output.

---

## Calibration Governance

Calibration is a challenger layer, not an automatic repair.

Raw probabilities remain immutable.

A calibrated forecast is a separate forecast variant.

Calibration may fit only from prior out-of-sample forecasts and outcomes already known before the calibration cutoff.

Never train calibration from:

- base-model in-sample predictions;
- future outcomes;
- the target match being calibrated;
- retrospectively complete future-season outcomes presented as historical evidence.

If calibration fails to improve the governed evidence, retain raw predictions.

Calibration approval does not mutate the raw model artifact or raw forecast history.

---

## Challenger Authorization

A challenger requires an explicit owner decision that names:

- one model or direction;
- its bounded scope;
- frozen pre-evaluation specification, or the route that must freeze it;
- allowed inputs;
- forbidden inputs;
- parameter budget where applicable;
- fitting objective and numerical contract where applicable;
- feasibility gate;
- admission/evaluation gate;
- stop conditions;
- whether authoritative target access is authorized.

Do not turn an authorization into a candidate search.

Do not automatically try challenger B if challenger A fails unless the repository owner explicitly authorized that sequence before seeing results.

Do not reinterpret a direction-level authorization as permission to explore multiple mathematical formulations.

---

## Feasibility

Technical feasibility may include:

- mathematical property tests;
- parameter-domain tests;
- deterministic fitting;
- optimizer and failure behavior;
- identifiability checks where defined;
- artifact round trip;
- checksum identity;
- reload prediction equivalence;
- input-order stability;
- allowed historical training fit;
- point-in-time invariants;
- same-kickoff behavior;
- retry/recovery behavior.

Feasibility `PASS` does not imply predictive admission.

A technically correct model may still be rejected by its predictive gate.

---

## Training-Only Admission

When an owner decision defines a training-only admission firewall:

- use the exact frozen folds and population;
- fit only from each fold's governed training history;
- tune nothing against validation outcomes;
- compare against the frozen reference;
- use the same governed targets and equivalent eligible history;
- apply the exact frozen metric inequalities;
- require integrity, determinism, artifact, leakage, and reproduction checks;
- stop on failure.

A near-tie that fails a strict precommitted inequality remains `FAIL`.

Do not rescue failure through:

- rounding;
- epsilon added after the result;
- "practical equivalence";
- altered folds;
- altered training windows;
- alternate objective;
- alternate optimizer;
- alternate parameterization;
- owner discretion after seeing the result.

Passing admission does not imply authorization to access an authoritative target population.

---

## Authoritative Evaluation

Authoritative evaluation must be separately authorized when the active route or policy requires that boundary.

Do not run the authoritative target set merely because:

- implementation is complete;
- feasibility passed;
- admission passed;
- the command exists;
- the challenger looks promising.

When target access is forbidden, treat access itself as a hard process failure according to the active route.

Candidate and reference must be evaluated on the same governed target population and comparable point-in-time history unless the frozen policy explicitly defines otherwise.

Do not change:

- target population;
- scoring policy;
- uncertainty method;
- thresholds;
- blocking dimensions;
- calibration policy;
- comparison reference;

after observing authoritative results unless a new explicit governance decision creates a new evaluation policy.

---

## Evaluation Identity

An authoritative evaluation must bind the applicable:

- evaluation policy version;
- dataset/source lineage;
- governed target-plan identity/checksum;
- target-set identity/checksum;
- first and final evaluation football cutoffs;
- knowledge mode;
- exact model artifact identities;
- exact persisted forecast identities;
- calibration artifact identities where applicable;
- probability/output contract versions;
- code Git SHA;
- dependency lock;
- analysis configuration;
- resampling/uncertainty policy and seed where applicable;
- evaluation-run identity;
- report checksum;
- completion time;
- terminal status.

Retained prediction rows should make it possible to trace each scored target back to the exact fitted artifact(s) and persisted forecast(s) that produced it.

Do not present the first batch's scope as the identity of the complete run.

Equivalent-run reproduction requires equivalence of all inputs that the frozen policy declares material.

---

## Evaluation Evidence

Evaluation reports are immutable evidence.

A repeated review or re-execution creates a new evaluation run rather than mutating an old report.

Durable evaluation evidence should record:

- exact model/config identity;
- exact data identity;
- exact target population;
- code/dependency identity;
- metrics;
- reference metrics;
- paired deltas and intervals where required;
- integrity checks;
- deterministic reproduction;
- leakage checks;
- artifact/forecast identities;
- target-access statement where relevant;
- terminal decision.

Do not create duplicate prose evidence when a machine-readable report already owns the result.

Prefer a short human explanation that references the machine-readable authority.

---

## Promotion

Implementation, feasibility, admission, authoritative evaluation, and promotion are separate decisions.

Promotion requires:

- an eligible non-failed governed evaluation;
- all required integrity checks;
- all required reproducibility checks;
- all required leakage checks;
- explicit owner or policy approval.

A technically valid artifact with no eligible governed evaluation is not promotable.

Never automatically promote after:

- retraining;
- refitting;
- feasibility PASS;
- admission PASS;
- one successful evaluation;
- calibration improvement.

Preserve the previous approved model/artifact until promotion is explicitly recorded.

Promotion events are append-only.

Retirement is also an explicit governance event.

Historical forecasts continue to reference the exact artifact identities they originally used even after a mutable production alias changes.

---

## Failure and Stop Semantics

A model route may terminate with:

```text
PASS
PASS_WITH_WARNINGS
FAIL
STOP
```

according to its frozen policy.

A failure is evidence.

Do not erase, rewrite, or reinterpret a terminal failed route.

Do not reopen, reclaim, or mutate tickets from terminal, failed, abandoned, or superseded routes unless a new explicit owner decision authorizes revisiting that work.

Historical failed, abandoned, or superseded tickets remain evidence, not an automatic backlog.

Newly authorized work should normally use a new route and new tickets.

A terminal failure in challenger A does not authorize challenger B.

---

## Evidence and Current State

Durable model evidence should be machine-readable where practical.

Use human-readable documents to explain or reference governed evidence, not to duplicate complete machine-readable reports.

Current project status belongs in the repository's tracked current-state authority and applicable Wayfinder decision/event ledger.

This document must not be used as a manually maintained source for:

- current Sprint status;
- current challenger authorization;
- current model-promotion state;
- current Phase authorization;
- exact current evaluation metrics.

Those change more often than the durable governance rules in this document.

---

## Core Governance Principles

```text
A fit execution is not the fitted model state.

Equivalent governed fits converge on one logical artifact.

Artifacts are immutable.

Loaders fail closed.

Authoritative forecasts use reloaded, verified artifacts.

Equivalent forecast retries converge.

Partial publication is recoverable without mutation.

Aliases may move; artifact identities may not.

Raw and calibrated forecasts remain separate.

Feasibility PASS is not admission PASS.

Admission PASS is not authoritative-evaluation authorization.

Evaluation PASS is not promotion.

Challenger authorization is not candidate search.

A failed frozen gate remains failed.

Terminal routes are evidence, not backlog.

Promotion requires eligible evidence and explicit approval.

Historical forecasts keep exact artifact identities forever.
```
