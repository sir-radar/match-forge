# Goalkeeper Shot Stopping V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.13 `GoalkeeperShotStoppingV1`

```text
goalkeeper_id
post_shot_xg_or_xgot_faced
goals_conceded_excluding_own_goals
goals_prevented_residual
cross_and_set_piece_claim_context_if_qualified
rolling_windows
opponent_and_shot_mix_adjustment
shrinkage_and_uncertainty
projected_start_probability
provider_semantic_version
knowledge_cutoff
version
```

Ordinary xGA measures the chances allowed before the shot outcome; it does not cleanly isolate goalkeeper shot-stopping. Use post-shot information only where its trajectory and on-target semantics are qualified. Reject raw save percentage as a standalone ability signal.
