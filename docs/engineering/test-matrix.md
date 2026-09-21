# Test Matrix

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

Actual repository test execution has **not** occurred in this package. This is a proposed checklist; add CI enforcement only after reconciliation. Parity tests must compare the sealed forecast with and without enrichment.

---

## 17. Testing requirements

### Software structure and contracts

- architecture tests enforce module dependency direction;
- domain and probability types have deterministic unit and property tests;
- provider adapters pass fixture-based contract tests against versioned samples;
- database migrations are tested both forward and through the supported rollback or roll-forward recovery path;
- API schemas are checked for backward compatibility within the supported version;
- job handlers are idempotent under duplicate delivery and safe under partial retry;
- outbox or equivalent state-transition tests prevent committed data from losing required follow-up work;
- batch replay and production scoring return identical features and scores for the same cutoff, versions, and model.

### Delivery, performance, and resilience

- CI reproduces locked dependencies and verifies build provenance;
- integration tests use real supported database and queue versions rather than mocks alone;
- end-to-end tests cover ingest, correction, feature snapshot, forecast, tag enrichment, and API retrieval;
- load tests cover forecast latency, batch throughput, queue depth, and bounded simulation requests;
- staging tests prove required-product publication blocks on failed or inconclusive Rust validation; historic analytic-only artifacts remain readable;
- simulator outage, timeout, cancellation, duplicate delivery, seed repeatability, precision-budget exhaustion, and artifact/hash mismatch fail explicitly without probability mutation;
- provider timeouts, malformed payloads, rate limits, and partial outages exercise documented fallbacks;
- staging deployment, rollback, backup restore, and disaster-recovery exercises meet the approved SLO, RPO, and RTO;
- authorization, input-fuzzing, secret-scanning, dependency, container, and license-policy checks pass.

### Data and time

- property tests for cutoff eligibility;
- same-kickoff leakage tests;
- daylight-saving and timezone tests;
- provider correction replay;
- identity ambiguity and quarantine tests;
- feature missingness/fallback tests;
- travel distance, direction, and timezone calculations;
- neutral-venue and relocated-fixture handling;
- no future fixture, international-duty, or next-match information enters before publication;
- forecast revisions are immutable and have non-decreasing knowledge cutoffs.

### Derby, display tags, and H2H

- unordered pair identity tests;
- historical validity tests;
- neutral/shared venue tests;
- friendly/competition filtering;
- decay and effective-sample calculations;
- shrinkage tends to zero for sparse pairs;
- no current-match outcome enters its H2H snapshot;
- placebo-pair pipeline tests;
- entropy, covariance, and distribution-divergence calculations;
- same-seed counterfactual variants differ only through registered H2H parameter changes;
- current or future meetings cannot enter a pair's continuity or style-similarity features;
- derby registry fields cannot enter a model feature manifest;
- unpredictability tags cannot enter training, calibration, parameter, or simulator schemas;
- mutating or removing tags leaves forecast and simulation artifacts unchanged;
- tag enrichment failure returns the original forecast without probability changes;
- every tag carries `forecast_effect: false` and reproducible reason codes.

### xG/xGA

- shot coordinate and direction normalization;
- penalties and shootouts handled separately;
- own goals excluded from shot xG unless the contract says otherwise;
- provider semantic version tests;
- xG-for for one team equals xGA attributed to the opponent under the approved match contract;
- rolling windows contain only eligible prior matches;
- game-state slices reproduce from qualified event timelines;
- adjusted values retain raw counterparts and adjustment version;
- historical score state or dismissal data cannot enter its own pre-match snapshot.

### Travel, lineup, and revision context

- projected-core-XI minute totals use only lineup probabilities available at cutoff;
- lineup continuity and minutes-together exclude future appearances;
- predicted and confirmed lineup contracts cannot be mixed silently;
- lineup scenario probabilities plus residual mass are coherent;
- travel/load fallbacks are explicit when venue or player-minute data is missing;
- every revised forecast points to an existing predecessor and preserves the predecessor unchanged;
- forecast-horizon bucketing is deterministic and timezone-safe.

### Squad transition, goalkeeper, and pre-shot threat

- retained-minute and newcomer features use identities and appearances known at cutoff;
- transfer rumours, fees, and future registrations cannot enter snapshots;
- projected player and goalkeeper contributions are weighted by start probability;
- player and goalkeeper effects shrink toward their approved population priors when samples are sparse;
- pre-shot and post-shot xG semantics cannot be mixed;
- own goals, penalties, blocked shots, off-target shots, and shootouts follow explicit post-shot rules;
- box-entry, field-tilt, turnover, and possession-sequence calculations reproduce from versioned events;
- possession and territory windows contain only eligible previous matches.

### Probabilities and mandatory Rust simulation validation

- probabilities are finite, non-negative, and sum to one; score-matrix tail is explicit;
- final calibrated joint distribution is internally coherent before sampling; do not accept a 1X2-only adjustment that contradicts score-derived markets;
- deterministic Rust seed reproducibility, independent batch schedules, and analytic parity within pre-registered Monte Carlo confidence tolerances;
- convergence, uncertainty half-width, rare-event and tail checks have PASS, FAIL, and INCONCLUSIVE tests;
- validation-artifact hashes bind exactly to the sealed forecast candidate, Rust build, parameter/distribution version, and seed schedule;
- required-product publication rejects failed, missing, or inconclusive validation; existing published artifacts remain unchanged;
- monotonic market-line relationships where mathematically required;
- calibration artifact cannot train on its evaluation outcomes or Rust-generated synthetic outcomes;
- no Rust simulation runs on the frozen 280 Sprint 2 targets for the new route.

### Display-tag and diagnostic layer

- risk components are pre-match eligible;
- post-match shock labels cannot join the same match's pre-match snapshot;
- thresholds are frozen and versioned;
- reason codes reproduce;
- `INSUFFICIENT_DATA` is not converted to normal confidence;
- `FixtureDisplayTagsV1` is created only after the referenced forecast is immutable;
- no frontend tag can trigger forecast revision or recalibration.
