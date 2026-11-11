# P02 forecast re-evaluation proposal

**Status: PROPOSED / NOT APPROVED.** This file is input for the owner. It does not authorize changing, superseding, hiding or re-scoring any published forecast, and it does not authorize model training, promotion or a new evaluation run. See [current state](../status/current-state.md) for what is authorized.

## Why

Before the P02 fix, results stored by the dated fixture request never reached team history (defect D-01). Forecasts issued in that period used team history that lacked some results the system already held. Each forecast is still a correct record of what the system knew and published at its knowledge cutoff. The question is whether, and how, to measure what those gaps cost.

## Inventory

Computed on the restored rehearsal copy after re-qualification ([runbook](../operations/runbooks/p02-history-requalification.md)) with `integrity_audit.affected_forecasts`. A forecast counts as affected when a result admitted by the re-qualification has a source observation at or before the forecast's knowledge cutoff, kicked off before the forecast's fixture and involved one of its teams.

| Measure | Count |
| --- | --- |
| Forecasts affected | 10,307 of 18,224 (all `MVP_FORECAST`) |
| Fixtures affected | 3,712 |
| Fixtures already finished | 1,686 (1,655 with a `REGULATION_90` result that can settle) |
| Fixtures not yet kicked off on 11 November 2026 | 1,935 |
| Forecasts missing a result from the previous 120 days | 6,017 |
| Forecasts missing 1 / 2 / 3 / 4–5 / 6 or more results | 4,650 / 2,874 / 1,195 / 938 / 650 |

The per-forecast list (forecast ID, fixture ID, knowledge cutoff and the missing fixture IDs) is regenerated from the operating database after the runbook is applied. The rehearsal figures above are indicative until then.

## Rules that hold under every option

1. No published forecast, artifact, hash or read report is edited, deleted or hidden. They stay retrievable exactly as published.
2. A new forecast for an upcoming fixture is a new append-only record with its own knowledge cutoff, issued by the normal refresh. It is not a correction of the earlier record. This already happens without a decision: once the runbook is applied, the scheduled `refresh-forecasts` sees a changed history window for upcoming `SCHEDULED` fixtures and publishes a revision with reason `BASELINE_HISTORY_CHANGED` (`sync_forecasts.py`). Stopping that would need the refresh to be paused, which this proposal does not recommend.
3. Any recomputation of a past forecast is a counterfactual research artifact, labelled as such, stored apart from published forecasts and never served as a forecast.
4. Results of any comparison go to the evaluation record, not into model promotion, unless a separate owner decision says otherwise.

## Options

| Option | What happens | Cost | Risk |
| --- | --- | --- | --- |
| A. Record only | Attach the inventory to the evidence record. Upcoming fixtures get revisions through the existing refresh (rule 2). | Lowest | Evaluations that include these forecasts cannot separate the data defect from model error. |
| B. Record and annotate (recommended) | Option A, plus an `affected_by: P02-D-01` annotation, stored apart from the forecasts, that evaluation reports use to show results with and without the affected forecasts. | Low | The size of the effect stays unknown. |
| C. B plus counterfactual measurement | Option B, plus a frozen, pre-registered comparison on the 1,655 settleable fixtures: rerun the same model version at the same cutoffs with corrected history, then compare log loss and Brier score with the published forecasts. | Medium; needs a pre-registration and an evaluation run | Must not be read as a model change or as permission to promote. |

## Decision requested

Choose A, B or C, and for C name the pre-registration owner. Until a decision event exists, the system keeps doing what it does today: published forecasts stay unchanged, and upcoming fixtures get new forecasts only through the existing refresh schedule. Of the 1,935 upcoming affected fixtures on 11 November, those still `SCHEDULED` when the runbook is applied will get revisions; the rest will settle with their earlier forecast.

## Approval placeholders

`owner: TBD; decision_id: TBD; signed_at: TBD; approved_option: TBD; inventory_sha256: TBD`. Do not mark this proposal approved until the owner records a decision event.
