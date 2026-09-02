# Foundation hardening gate

`FoundationHardeningReportV1` is the immutable Phase 2B gate report. It
aggregates provider-platform, dependency-graph, rebuild, CI, observability,
backup/restore, integrity, and competition-rules evidence, binding each report
to a policy version, code Git SHA, dependency-lock checksum, and evidence
references.

The aggregate is fail-closed: any `FAIL` makes the report `FAIL`, any unrun
category keeps it `NOT_RUN`, and warnings are preserved as
`PASS_WITH_WARNINGS`. This report does not alter Sprint 2 evidence or authorize
Phase 3; it is the foundation gate evidence required for later governance
review.
