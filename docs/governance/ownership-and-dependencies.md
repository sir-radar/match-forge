# Ownership, authorization and dependency register

**Owner identities are `TBD` until checked in the actual repository; functional ownership below is a contract, not a claim about assigned people.** A decision must name the real person/role authorized to approve it.

| Concern | Single source of truth / functional owner | Prerequisite | Rollback/suspension boundary |
| --- | --- | --- | --- |
| Provider meanings | Adapter + qualification report / ingestion | Provider terms and timestamp semantics | Quarantine source/version; never mutate raw history |
| Team/fixture identity | Resolver / data domain | Provider mapping review | Suspend ambiguous fixtures |
| Eligible corpus | Frozen independent manifest / evaluation | Owner-authorized policy + target firewall | Suspend evaluation without rewriting results |
| Features | Versioned shared library / features | PIT audit and replay/serve parity | Route new candidates away; preserve snapshots |
| Forecast model/parameters | Model registry / forecasting | Data tier eligibility and independent evaluation | Restore previous approved model version |
| Calibration | Calibrator artifact / forecasting | Real OOS outcomes, coherent joint model | Restore calibrator/version; no tag/sim auto-update |
| Forecast artifact/hashes | Sealed artifact registry / publication | Inputs, distributions, provenance pass | Halt new publish; never change old artifacts |
| Rust numerical validation | Rust engine + immutable evidence / simulation | Separate authorization, accepted policy/build | Disable affected new publication or use owner-approved labelled exception |
| Risk/tag enrichment | `ForecastEnrichmentV1` / diagnostics | Published forecast and eligible evidence | Disable sidecar without affecting forecast |
| Experiment authorization | Verified owner events + ledger / governance | Scoped hypothesis, firewall | Superseding event; retain failed evidence |
| Promotion/enablement | Capability registry / release owner | Predictive, scientific and ops gates | Suspend flag, rollback release; preserve artifacts |
| Public surface | Versioned OpenAPI / delivery | Approved product capabilities and privacy review | Versioned API/feature flag rollback |
| Incident/recovery | Runbook + audited release / operations | SLO/RPO/RTO and budget policies | Tested recovery and incident postmortem |

**Forbidden edges:** diagnostics/enrichment → features/model/calibrator/parameters/simulator/probability/revision; simulator → model training/calibration; API → private provider data or invented model semantics; held-out result → same fixture's issued pre-match snapshot; evaluation → protected Sprint 2 target set.

**Required decision sequence:** authorize bounded design/research → pre-register and freeze → run/record evidence → candidate evaluation disposition → independent model promotion decision → separate engine/capability acceptance and production enablement. A release must prove each relevant upstream event by identifier, never by assumption.
