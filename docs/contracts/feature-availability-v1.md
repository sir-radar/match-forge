# Feature Availability V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use.

---

### 6.7 `FeatureAvailabilityV1`

Each feature must declare:

```text
event_time
observation_time
provider_publication_time
ingestion_time
correction_time
knowledge_cutoff
eligibility_status
missingness_reason
source_lineage
```
