# Matchup Intelligence V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.8 `MatchupIntelligenceV1`

This contract is a wrapper for opponent-specific evidence. It prevents H2H from becoming a standalone source of truth.

```text
fixture_id
base_model_snapshot_id
h2h_context_id
style_interaction_features_if_qualified
manager_matchup_features_if_qualified
lineup_and_formation_interactions_if_qualified
set_piece_matchup_features_if_qualified
component_coverage
component_uncertainty
adjustment_mode
reason_codes
knowledge_cutoff
version
```

`adjustment_mode` must be one of `DISPLAY_ONLY`, `MEAN_CANDIDATE`, `DISPERSION_CANDIDATE`, `CORRELATION_CANDIDATE`, or `PROMOTED`. Production may use only a separately promoted mode.

Derby registry membership is deliberately absent. Rivalry metadata belongs only to `FixtureDisplayTagsV1`; H2H and other matchup candidates must prove value independently of the derby tag.
