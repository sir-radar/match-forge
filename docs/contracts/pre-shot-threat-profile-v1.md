# Pre Shot Threat Profile V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.14 `PreShotThreatProfileV1`

```text
box_entries
deep_completions
final_third_entries
high_turnovers
field_tilt
possession_to_shot_rate
possession_to_box_entry_rate
transition_and_settled_attack_splits
for_and_against_values
game_state_adjustment_version
provider_semantic_version
effective_sample_size
knowledge_cutoff
version
```

This bounded family tests whether a team consistently creates or suppresses dangerous possessions before a shot occurs. It precedes xT/VAEP adoption and must not treat possession volume as chance quality.
