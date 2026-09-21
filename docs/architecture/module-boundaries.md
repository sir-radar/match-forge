# Module Boundaries

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Ownership rule:** actual module layout and Rust/Python/Go interfaces must be reconciled against the repository. This text preserves the proposed modular-monolith boundaries and single-owner matrix.

---

## 5. Target architecture

```text
providers
  -> immutable raw observations
  -> provider-specific normalization
  -> identity resolution and quarantine
  -> point-in-time match/event/lineup/odds views
  -> leakage-safe feature snapshots
  -> matchup, squad, and load context
  -> statistical candidate models
  -> validated match parameters / coherent base distribution
  -> out-of-sample-fitted calibration (coherent distribution-level policy)
  -> sealed immutable forecast candidate, not yet public
  -> REQUIRED authorized Rust sampling and parity / convergence validation
  -> immutable linked SimulationValidationArtifactV1
  -> publish unchanged forecast + validated simulation evidence atomically
  -> optional display-tag and diagnostic sidecar
  -> API response composition and monitoring
```

### Boundary rules

- The feature layer calculates only pre-match eligible values.
- Statistical models estimate team strengths, goal intensities, and outcome distributions.
- The parameter generator converts model state and match context into simulator inputs.
- Rust samples only validated parameter/distribution inputs; it does not learn hidden team strength, tune calibration, or alter forecast probabilities in response to sampling noise.
- The finalized forecast candidate is sealed before simulation. For a simulation-backed production product, publication is gated on a passing linked simulation-validation artifact; a failure retains the candidate internally for diagnosis but publishes neither an unvalidated simulated product nor a silently altered forecast. Already-published analytic artifacts remain immutable and retrievable. An explicitly authorized analytic-only fallback must be labeled and must never masquerade as simulation-validated.
- Once publication passes, the immutable forecast is completed before optional derby or unpredictability enrichment is attached.
- The display-tag and diagnostic layer describes fixture categories, confidence, and evidence quality. It cannot be joined into model features, parameter generation, simulation, calibration, or probability post-processing.
- Removing the display-tag sidecar must produce exactly the same forecast artifact.
- The calibration layer is fitted only on training/calibration periods and is versioned separately.

### Initial deployment shape

Start with one modular application and separately runnable worker processes rather than a network of microservices. Maintain these code boundaries from the first release:

```text
domain          team identity, fixture time, eligibility, probability types
ingestion       provider adapters, raw writes, corrections, quarantine
features        point-in-time transformations shared by replay and production
forecasting     model loading, parameter generation, calibration
simulation      Rust deterministic sampling and validation; Python owns analytic modelling and calibration
diagnostics     post-forecast risk assessment and display tags
delivery        API schemas, persistence, authentication, rate limits
operations      jobs, observability, audit, deployment and recovery
```

Rules:

- domain modules must not import provider, transport, database, or framework code;
- provider-specific logic ends at normalization adapters;
- batch replay and production forecasting call the same feature library with explicit cutoff and version arguments;
- long-running ingestion, replay, training, and simulation use durable workers with idempotent job keys;
- a new deployable service requires measured scaling pressure, a fault-isolation need, or a clear ownership boundary;
- cross-module calls use typed interfaces and versioned contracts, even while modules share one deployment.

### Single-source-of-truth ownership

| Concern | Authoritative owner | Forbidden duplication |
| --- | --- | --- |
| Provider semantics | Provider adapter and qualification report | Reinterpreting raw fields inside models or API handlers |
| Team and fixture identity | Identity resolver | Local name matching in feature or UI code |
| Feature definition | Versioned feature library and contract | Separate training and serving transformations |
| Dataset membership | Frozen corpus manifest | Ad hoc query filters inside experiments |
| Model state | Model registry artifact | Untracked files or embedded parameters in services |
| Calibration | Versioned calibrator artifact | Endpoint-specific probability adjustment |
| Simulation inputs | Versioned match parameter / calibrated distribution contract owned by forecasting | Simulator-side strength estimation or recalibration |
| Simulation validation | `SimulationValidationArtifactV1` produced by approved Rust engine | API or frontend inventing run counts, parity, convergence, or approval |
| Display tags | Post-forecast sidecar | Tag logic inside forecast generation or calibration |
| Public response | Versioned API schema | Frontend reconstruction of model semantics |

If two sections mention the same concern, this table determines which artifact owns the executable rule; other sections define gates, tests, or sequencing only.
