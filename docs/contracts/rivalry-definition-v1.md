# Rivalry Definition V1

> **Document status:** proposed supporting specification extracted from the supplied 21 September PLAN; not proof of implemented code, passed gates, or additional authorization. The current repository evidence and owner events take precedence.

**Source-derived proposed field contract.** Require separate owner approval, point-in-time eligibility and implementation/schema review before production use. Derby membership is always display-only and must never adjust forecast or simulator inputs.

---

### 6.1 `RivalryDefinitionV1`

Required fields:

```text
rivalry_id
unordered_team_pair
valid_from
valid_to
rivalry_type
geographic_scope
competition_scope
source_references
review_status
reviewed_by
reviewed_at
notes
```

Allowed `rivalry_type` values initially:

```text
SAME_CITY
REGIONAL
HISTORIC
CULTURAL_OR_POLITICAL
INSTITUTIONAL
```

Rules:

- geographic proximity may nominate a candidate but cannot automatically declare a derby;
- a pair may have more than one type;
- all entries need temporal validity because club identity, location, and rivalry relevance can change;
- friendly matches are excluded unless a research contract explicitly includes them;
- neutral venues and shared stadiums are stored separately from rivalry type;
- unreviewed candidates cannot become production features.
