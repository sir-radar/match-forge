# Squad Transition V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.12 `SquadTransitionV1`

```text
retained_minutes_share
retained_starting_minutes_share
departed_core_minutes
newcomer_projected_minutes
newcomer_matches_and_minutes_with_team
role_replacement_deltas
goalkeeper_change
manager_and_squad_change_interaction
promoted_or_relegated_transition
effective_sample_size
identity_and_lineup_coverage
knowledge_cutoff
version
```

This contract should detect rapid changes that a slow-moving team rating may miss. It must use actual roles, appearances, minutes, and availability known at cutoff—not transfer fees, rumours, or subjective reputation.
