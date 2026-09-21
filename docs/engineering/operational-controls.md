# Operational Controls

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

This preserves the supplied operational requirements; ownership, approved SLO numbers, RPO/RTO and cost budgets require repository review and decision. No infrastructure files are created by this documentation change.

---

## 18. Engineering and operational controls

Section 18 owns platform implementation requirements. Section 17 owns the tests that prove them, and Section 13 owns the gates that block promotion.

### 18.1 Persistence and data lifecycle

- keep provider payloads immutable in raw storage and operational state in a transactional database;
- make derived caches disposable and reproducible from authoritative artifacts;
- use versioned migrations with an expand-migrate-contract sequence for incompatible schema changes;
- checksum datasets, feature snapshots, models, calibrators, and simulation builds;
- define retention, archival, correction, deletion, and provider-license policies by data class;
- record lineage from API forecast back to source observations, transformations, code revision, and artifact versions.

### 18.2 Jobs, retries, and replay

- assume at-least-once job delivery and make handlers idempotent using stable operation keys;
- use durable queues, bounded retries, exponential backoff, dead-letter handling, and operator-visible replay;
- persist checkpoints so ingestion, backfills, evaluation, and simulation batches resume safely;
- separate transient provider failure from invalid or quarantined data;
- schedule in UTC and make same-kickoff batch boundaries explicit;
- prevent concurrent jobs from publishing conflicting current versions.

### 18.3 API and access boundaries

- publish a versioned machine-readable API schema and explicit compatibility policy;
- validate match, lineup, scenario, pagination, and bounded-simulation inputs;
- apply authentication, authorization, tenant or role boundaries where applicable, rate limits, request size limits, and timeouts;
- attach request and forecast correlation IDs to responses and telemetry;
- support idempotency keys for state-changing administrative operations;
- never expose raw or licensed provider data unless the provider contract permits it.

### 18.4 Observability and service levels

- correlate structured logs, metrics, and traces across API, workers, storage, model loading, and provider calls;
- define measurable SLOs for API availability and latency, forecast freshness, scheduled-job success, correction lag, feature coverage, and recovery;
- track saturation, queue age, error budgets, provider failures, cache effectiveness, and artifact-load failures;
- make alerts actionable with an owner, severity, runbook, and clear recovery condition;
- ensure display-tag enrichment failure cannot consume the forecast-availability error budget.

### 18.5 Security and software supply chain

- manage secrets outside source code and rotate provider and infrastructure credentials;
- enforce least privilege, encryption in transit and at rest, and immutable audit events for datasets, experiments, administrative changes, and promotion;
- lock dependencies and scan source, secrets, dependencies, licenses, containers, and infrastructure definitions;
- generate a software bill of materials and verifiable build provenance for release artifacts;
- verify artifact signatures or checksums before deployment and model loading;
- document vulnerability triage, patch timelines, and incident response ownership.

### 18.6 Delivery, recovery, and cost

- define infrastructure as code and keep development, staging, and production configuration differences explicit;
- use automated migrations, smoke tests, shadow or canary validation, and reversible deployment steps;
- prove rollback for application, schema, model, calibrator, and feature releases;
- define RPO and RTO, automate backups, and test restoration on a schedule;
- set budgets and alerts for provider calls, storage growth, training, replay, simulation, and per-forecast serving cost;
- scale workers independently before introducing additional network services.
