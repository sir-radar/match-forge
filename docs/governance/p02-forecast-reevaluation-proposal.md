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

A second rehearsal with replay v2 (which also reconciles overdue fixtures from retained responses) on a fresh restore found **10,887 affected forecasts over 3,799 fixtures, 6,383 of them missing a result from the previous 120 days** (inventory SHA-256 `cc5f2da6afc33cf1a24d31326b9692f99b629411d7a103958ae3520f643fdad8`, [evidence](../evidence/p02-remediation-rehearsal-2-2026-11-11.json)). The table above is from the first rehearsal.

The per-forecast list (forecast ID, fixture ID, knowledge cutoff and the missing fixture IDs) is regenerated from the operating database after the runbook is applied. The rehearsal figures above are indicative until then. The rehearsal inventory hash is recorded in the [rehearsal evidence](../evidence/p02-remediation-rehearsal-2026-11-11.json).

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

## Option B approval package

This section is what the owner signs if Option B is chosen. Nothing in it is built or applied until the decision event exists.

**Decision event to record** (`docs/governance/decision-events/`, contract `OwnerDecisionRecordV1`):

- `decision_id`: `APPROVE_P02_FORECAST_REEVALUATION_OPTION_B_V1`
- `authorizes`: an additive migration for the annotation table below; populating it from the affected-forecast inventory regenerated on the operating database after the runbook; evaluation reports that show every metric with and without annotated forecasts.
- `explicitly_not_authorized`: editing, superseding, hiding, deleting or re-scoring any published forecast, artifact or read report; counterfactual reruns (Option C); model training, promotion or retirement; changing which forecasts are served.
- `requires`: `inventory_sha256` of the operating inventory, the runbook's preservation hashes before and after population, and the annotation count equal to the inventory count.

**Annotation storage.** A new append-only table, separate from forecasts:

| Column | Meaning |
| --- | --- |
| `forecast_id` | The published forecast (foreign key; the forecast row is not touched) |
| `annotation` | `P02-D-01` |
| `missing_fixture_ids` | Results the forecast's inputs lacked although their source was known before its cutoff |
| `missing_within_120_days` | Count used for the sensitivity split |
| `inventory_sha256`, `decision_id`, `recorded_at` | Provenance |

Rows are insert-only (same immutability trigger as read reports). Revoking the annotation means inserting a revocation row, not deleting.

**Evaluation reporting.** Every performance or comparison report over a period that contains annotated forecasts shows three figures side by side: all forecasts, forecasts without the annotation, and annotated forecasts only, each with its count. Reports for periods with no annotated forecasts are unchanged. The headline metric stays "all forecasts", so nothing published becomes better by exclusion.

**Preserved under Option B:** every historical forecast and its probabilities, hashes, artifacts and read reports; the order and timing of revisions; model governance (no promotion or retirement follows from the split).

## Approval placeholders

`owner: TBD; decision_id: TBD; signed_at: TBD; approved_option: TBD; inventory_sha256: TBD`. Do not mark this proposal approved until the owner records a decision event.
