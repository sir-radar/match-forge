# Rollback, suspension and incident ownership

**Status:** proposed operating contract. Actual command names and RPO/RTO/SLO numbers must be copied from the real repository after approval, not invented here.

- Each release records a signed/hashed deployment manifest referencing application revision, DB migration, feature/model/calibrator versions, Rust build, validation policy, API version, capability state and rollback target.
- Feature/model/calibrator/engine rollback changes *future* forecast routing only. Previously published forecasts, failed experiment records, simulation sidecars and decision events are immutable and retrievable.
- A broken schema migration requires a rehearsed compatible rollback or roll-forward remediation; never destructively revert immutable raw observations or historical probability artifacts.
- Rust parity/tail/hash failure immediately blocks **new simulation-required publication**, quarantines the offending build/policy and alerts owner. If and only if a separately approved analytic-only exception policy exists, operators may enable it within recorded scope and with visible response labelling.
- A tag parity/integrity failure disables enrichment, not the valid forecast. Alert incident owner and attach hash evidence.
- Provider availability/semantic failure quarantines affected input tier and associated new forecasts rather than silently substituting incompatible values.
- Restoration drills must verify backups, replay, RPO/RTO, artifact hash chain, target firewall and correct current capability flags. Record actual evidence and improvement actions.

See [simulation failure runbook](runbooks/simulation-failure.md), [operational controls](../engineering/operational-controls.md), and [capability registry](capability-registry.md).
