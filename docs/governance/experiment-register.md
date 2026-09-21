# Registered experiment ledger — proposed control

**A register entry is not an authorization, result, promotion or release.** The tracked owner decision grants narrow Phase 3A research permission, but the repository does not yet record an experiment ID or a complete frozen hypothesis and run contract for that work.

## Required per-experiment fields

| Field | Required meaning |
| --- | --- |
| `experiment_id`, `family`, `hypothesis`, `status`, `owner` | Unique bounded research claim and accountable reviewer. |
| `authorization_decision_id`, `scope`, `expiry` | Explicit exact authorization, or `NOT_AUTHORIZED`. |
| `corpus_id/hash`, `firewall_id`, `policy_id/hash` | Immutable sample and access policy. |
| `cutoff`, `feature_set_id`, `data_tier`, `model/calibrator IDs` | Eligibility and lineage. |
| `reference`, `challenger`, `ablation`, `tuning_budget` | Exactly what differs and how selected. |
| `metrics`, `segments`, `thresholds`, `CI/paired method`, `stop/fail rules` | Pre-registered decision method; no after-the-fact changes. |
| `code/build/seed IDs`, `resource_budget`, `artifact IDs`, `evidence hashes` | Reproducibility and cost. |
| `observed_results`, `decision_event_id`, `capability_id` | Append-only actual evidence and separate enablement pointer. |

Allowed lifecycle: `DRAFT → AUTHORIZED → FROZEN → RUNNING → EVALUATED → DECIDED`; blocked/failed routes retain their own immutable terminal state. No automated `DECIDED → PRODUCTION_ENABLED` shortcut.

## Initial reconciliation queue (not invented experiment entries)

| Research item | Recorded permission | Action |
| --- | --- | --- |
| Single bounded Phase 3A minimal xG hypothesis | Verified **research-only** event dated 20 Sep 2026 | Define and register the experiment ID, exact hypothesis, tier, and outputs; avoid duplicate authorization. |
| Evaluation V2 design and pre-registration | Design only | Draft separate frozen policy/corpus and request authoritative-run decision afterwards. |
| Wider xG/xGA, H2H, tags, lineups, context, ensembles | Not collectively authorized by that event | Register individually and request scope-specific decisions. |
| Minimal Rust engine/simulation evidence | Not authorized by that event | Use [separate proposal](simulation-authorization-proposal.md). |
| Protected Sprint 2 failures and 280 targets | Closed/blocked | Leave untouched; do not import targets. |

## Decision and audit

Attach actual metrics, adverse segments, inconclusive results, tests and cost without rewriting the hypothesis. Outcomes include retain, reject, defer and terminal fail; a promotable candidate still needs distinct predictive and production decisions. A future route cannot inherit approval from an unrelated experiment or combine several failed families without a fresh registered hypothesis and authorized independent evaluation.
