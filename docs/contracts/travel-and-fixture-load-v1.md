# Travel And Fixture Load V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.9 `TravelAndFixtureLoadV1`

```text
origin_venue_id
destination_venue_id
distance_km
travel_direction
timezone_delta
international_or_border_crossing
neutral_venue
rest_days
matches_last_3_7_14_30_days
minutes_by_projected_core_xi
recent_extra_time_minutes
recent_international_duty
days_to_next_match
next_match_competition
travel_load_features
recovery_disadvantage_features
fixture_congestion_features
effective_coverage
knowledge_cutoff
version
```

The first implementation must expose objective components. A learned composite is allowed only after an ablation shows stable incremental value.
