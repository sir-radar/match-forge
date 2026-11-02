# MatchForge Backend Engineering Standards

**Scope:** All backend changes, including Python data/modelling, Rust simulation, Go APIs/operations, SQL migrations, persistence, and background work. Read with the root `AGENTS.md` and relevant architecture, contract, testing, and governance documents. These standards do not authorize new phases, product features, or changes to approved boundaries.

## 1. Architecture and Ownership

- **Respect the established language boundaries:** Python owns football data, features, models, and evaluation; Rust owns authorized pure deterministic simulation; Go owns HTTP serving and operations; SQL migrations own database schema. Schemas and versioned contracts define cross-language interfaces.
- Keep business rules in their established owning modules. Do not duplicate modelling in Go, provider ingestion in Rust, or the same normalization, eligibility, identity, or validation logic across services.
- Prefer simple, cohesive modules and explicit data flow. Keep HTTP handlers, job entry points, and adapters thin; isolate domain logic from transport, persistence, and provider-specific details.
- Follow approved contracts, phase gates, and existing implementation patterns before applying generic best practices. Do not introduce a new service, framework, queue, abstraction, or architecture without a demonstrated need and authorization where required.

## 2. Prefer Established Open-Source Solutions

- **Search the repository and installed dependencies first.** For nontrivial common problems, research proven open-source libraries and standard-library capabilities instead of implementing them from scratch.
- Prefer mature, maintained, compatible, appropriately licensed, secure, and well-tested solutions. Verify the documentation and supported versions; consider operating cost, transitive dependencies, and long-term maintenance.
- Use existing approved tooling and libraries when they solve the problem well. Do not add dependencies for trivial functionality or duplicate packages with overlapping responsibilities.
- Research independently when details are uncertain, but do not replace a repository-approved contract or architectural decision with a library's defaults.

## 3. APIs, Jobs, and Failure Handling

- Define or reuse explicit request/response and cross-service contracts. Validate inputs at trust boundaries, return consistent errors, and enforce authentication, authorization, and tenant/resource scope where applicable.
- Use parameterized queries, safe serialization, least-privilege access, secret-safe configuration, and security-conscious logging. Never expose secrets, sensitive source data, or internal errors in public responses.
- Use context propagation, deadlines/timeouts, resource limits, and bounded retries appropriate to the operation. Retry only recoverable failures; use backoff and jitter where appropriate, and avoid retry storms.
- **Design side-effecting jobs and handlers for safe retries.** Use durable idempotency keys or existing uniqueness/claim mechanisms where needed; prevent duplicate writes, double execution, inconsistent partial state, and concurrency races.
- Make failure states explicit and observable. No silent success, swallowed exceptions, fabricated fallback data, or hidden incomplete processing.

## 4. Data, Identity, and Persistence

- **Preserve established data ownership:** immutable raw provider bytes; PostgreSQL for relational state; Parquet for large analytical datasets; object storage for immutable artifacts; Redis for cache and ephemeral coordination only.
- SQL migrations remain the sole schema authority. Use approved migration processes; review compatibility, locking, backfill behavior, constraints, indexes, and rollback/recovery before schema or data changes.
- Use transactions, uniqueness constraints, and safe concurrency controls for operations requiring atomicity. Do not rely on application-only checks to enforce critical database invariants.
- Preserve provider provenance, original values, stable MatchForge identities, and traceable mappings. Never silently resolve cross-provider identities by fuzzy names or discard unknown values.
- Preserve point-in-time eligibility and the separation of `football_cutoff`, `knowledge_cutoff`, and `knowledge_mode`. Never let future outcomes, same-kickoff results, or current-state shortcuts contaminate historical forecasts.
- Do not introduce duplicate authoritative stores, untracked derived state, silent schema coercion, or destructive data cleanup without the required decision and evidence.

## 5. Reuse and Maintainability

- **No duplicate backend logic.** Search existing adapters, validators, services, domain functions, queries, schemas, and job orchestration before adding new implementations.
- Centralize only genuinely shared rules in their proper owning layer; use composition and narrow interfaces instead of copied workflows or premature generic frameworks.
- Favor explicit types, versioned contracts where required, clear errors, simple control flow, and testable functions. Keep side effects at boundaries and deterministic calculations isolated from I/O.
- Remove task-introduced unused code and superseded paths. Do not add speculative compatibility layers, fallbacks, flags, or helpers.

## 6. Testing and Reliability

- **No flaky tests.** Use isolated fixtures, controlled clocks/time zones, fixed random seeds, deterministic ordering, and reproducible data. Never depend on test order, arbitrary sleeps, live external providers, or uncontrolled network access.
- Wait on observable conditions in async/concurrent tests. Make database and queue setup/cleanup repeatable; test important transaction and concurrency behavior against the appropriate real infrastructure rather than trusting mocks alone.
- Cover successful behavior, failures, boundaries, retry/idempotency behavior, contract compatibility, and relevant migrations. For forecasting/evaluation, preserve leakage, artifact, and reproducibility gates from the root guide.
- Investigate intermittent failures and fix their causes. Do not skip, weaken, suppress, or rerun tests until they happen to pass.

## 7. Performance, Observability, and Verification

- Measure before optimizing. Review query plans and indexes for meaningful database changes; avoid N+1 queries, unnecessary round trips, unbounded memory/CPU work, and premature caching.
- Use established structured logs, metrics, and tracing with request/job correlation where supported. Record useful failures and provenance without leaking secrets or creating unbounded high-volume logs.
- Before delivery, verify the applicable contracts, migrations, type/lint/static checks, unit/integration tests, concurrency/idempotency behavior, and required phase gates using the root `AGENTS.md` validation policy.
- Confirm no duplicated business logic, speculative dependency, bypassed security check, hidden fallback, non-deterministic test, or unapproved cross-language responsibility was introduced. Report meaningful trade-offs and any unresolved limitations.
