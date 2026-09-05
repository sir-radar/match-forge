# Competition rules

`CompetitionRulesV1` is the versioned contract for outcome semantics. It
records whether a competition is a league, group, knockout, or playoff; whether
fixtures are single-match, two-leg, or round-robin; the forecast outcome scope;
extra-time and shootout policies; and neutral-venue semantics. Rules bind
explicit source references and a policy version. They are not inferred from a
provider score field, and changing rules produces a new versioned contract.

The completed Ticket 07 check is recorded in
[`evidence/phase2b-competition-rules-2026-09-06.md`](evidence/phase2b-competition-rules-2026-09-06.md).

## Forecast and evaluation binding

Each new `BaselineForecastV1` embeds its full `CompetitionRulesV1` record in
the immutable forecast artifact and its semantic hash. Each
`EvaluationCorpusV1` embeds the same record in the immutable evaluation report.
PostgreSQL registries store the rule ID, rule checksum, and outcome scope for
new forecast and evaluation rows. The database constraint applies to new rows
without rewriting older immutable records.

The executed binding evidence is in
[`evidence/phase2b-competition-rule-bindings-2026-09-06.md`](evidence/phase2b-competition-rule-bindings-2026-09-06.md).
