# Owner decision: authorize PitchAPI snapshot V1 acquisition — 2026-09-24

```text
Decision ID: AUTHORIZE_PITCHAPI_SNAPSHOT_V1_CONTROLLED_ACQUISITION_V1
Status:      APPROVED
Recorded at: 2026-09-24T11:03:36Z
Owner:       repository owner / sir-radar
```

## Approved

- freeze Bundesliga 2021/22 as development;
- freeze Bundesliga 2022/23, Bundesliga 2023/24, and Ligue 1 2022/23 as evaluation;
- retain `TEAM_PRIOR_APPEARANCES >= 10` and no competition-history target floor;
- freeze the observational compatibility policy in the pre-acquisition review;
- create and retain immutable `PITCHAPI_SNAPSHOT_V1` plus one verified backup;
- use only the approved season-manifest and match-shot endpoint templates;
- allow 1,302 base requests, 27 retry attempts, and 1,329 total attempts;
- allow 500 MiB expected storage and a 6 GiB hard ceiling;
- perform validation, exact target reconciliation, compatibility assessment,
  and corpus/firewall readiness preparation.

The ten attempts left from earlier authority remain separate. Request, scope,
time, and storage ceilings cannot increase automatically. Monetary spend is
not authorized.

## Not approved

Model fitting, challenger training, final corpus admission, preregistration
completion, Rust execution, evaluation execution/reporting, production use,
promotion, added API scope, provider contact, spending, and any StatsBomb
`EVALUATION_V2` change remain prohibited.

Source: repository-owner authorization supplied on 24 September 2026. Full
controls and thresholds:
`docs/evidence/pitchapi-pre-acquisition-owner-review-2026-09-24.md`.
