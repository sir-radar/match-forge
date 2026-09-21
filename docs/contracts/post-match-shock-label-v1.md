# Post Match Shock Label V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.6 `PostMatchShockLabelV1`

This contract is available only after the match and is never joined into its own pre-match snapshot.

Possible labels, when provider semantics are qualified:

```text
early_red_card
multiple_red_cards
penalty_event
own_goal
goalkeeper_error
extreme_finishing_overperformance
extreme_goalkeeping_overperformance
injury_forced_substitution
match_abandonment
data_correction
```

Use it to explain forecast errors, build stratified evaluation, and study whether any pre-match indicators exist. Do not use the label itself to predict the same match.
