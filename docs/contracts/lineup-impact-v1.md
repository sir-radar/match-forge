# Lineup Impact V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.10 `LineupImpactV1`

```text
lineup_mode
lineup_scenarios
player_start_probabilities
attack_strength_delta
defence_strength_delta
goalkeeper_strength_delta
set_piece_strength_delta
xi_continuity
defensive_midfield_attacking_unit_continuity
minutes_together
formation_continuity
replacement_uncertainty
residual_scenario_mass
knowledge_cutoff
version
```

Predicted and confirmed lineups are different forecast contracts. Strength deltas must preserve player and scenario uncertainty instead of substituting one guessed XI.
