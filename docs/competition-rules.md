# Competition rules

`CompetitionRulesV1` is the versioned contract for outcome semantics. It
records whether a competition is a league, group, knockout, or playoff; whether
fixtures are single-match, two-leg, or round-robin; the forecast outcome scope;
extra-time and shootout policies; and neutral-venue semantics. Rules bind
explicit source references and a policy version. They are not inferred from a
provider score field, and changing rules produces a new versioned contract.
