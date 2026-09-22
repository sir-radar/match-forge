# Phase 3A Evaluation V2 source-candidate screen — 2026-09-22

## Result

All three acquisition candidates named in approved Decision 2 fail the
owner's men-only product-scope rule. None is admitted to Evaluation V2. This
is an early screen, not a full data qualification or an evaluation result.
The machine-readable record is
[Phase3AEvaluationV2SourceCandidateScreenV1](phase3a-evaluation-v2-source-candidate-screen-2026-09-22.json).

| Candidate | Provider IDs | Pinned match-list SHA-256 | Matches | Available dataset | Disposition |
| --- | --- | --- | ---: | --- | --- |
| Liga F 2023/24 | `182/281` | `ea93b27a4d1101ba62792c88b5770bdacd904cefdf38671382698f5c2298628a` | 240 | `f5cb2724-6400-540d-aa12-44ba25f27369` | `FAIL_PRODUCT_SCOPE` |
| Frauen Bundesliga 2023/24 | `135/281` | `78d01ecb20035bb8bbd94001065ec0f92ea747cb053b4aafca8b1051be12a7d3` | 132 | none registered in reviewed local evidence | `FAIL_PRODUCT_SCOPE` |
| NWSL 2023 | `49/107` | `75e333e1b196e60f62de86338eed82232bb1432e3f6bf7bafe867c9fdf8392b9` | 137 | none registered in reviewed local evidence | `FAIL_PRODUCT_SCOPE` |

The pinned StatsBomb source Git SHA is
`4b73468fc5b0f1950f9f66fada70ad3a4f9327cb`. All three verified local
match lists mark the home-team gender as `female` on every match. The retained
[outcome-blind catalog screen](dcv3-independent-low-score-local-replication-corpus-selection-retry-2026-09-09.md)
classified Liga F and Frauen Bundesliga as structurally complete. The NWSL
match list mixes 132 regular-season fixtures and five playoff fixtures; its
whole-scope structural classification is partial. These match-list facts do
not prove Decision 2's full coverage, xG, or point-in-time requirements.

For Liga F, [retained isolated recovery](statsbomb-liga-f-isolated-exact-source-recovery-2026-09-11.md)
recorded source snapshot `01a089cc-db5f-7f42-bf7a-419f8eaec2d8`, dataset
version `f5cb2724-6400-540d-aa12-44ba25f27369`, and dataset manifest
SHA-256 `f54fa768cb893cec099c8735135dcea2c495adb215f5bf3c398e7c531ee256f1`.
Its 138 prior-route structural targets are **not** an Evaluation V2 eligible
target count: that route used a different frozen policy and failed its own
140-target gate. No earlier Liga F result has been promoted to this route.

For Frauen Bundesliga and NWSL, exact source-snapshot IDs, dataset-version
IDs, and dataset-manifest hashes were not available in the reviewed local
evidence. For all three candidates, Decision 2 xG coverage, quarantine,
lifecycle, kickoff, prior-history, exact eligible-target, and exact protected
and development-source intersection checks were **not run** after the
product-scope failure. The earlier catalog screen's provider-level zero
protected overlap is not a substitute for exact target-manifest intersection.
No protected EPL source, target, or outcome was opened, and no evaluation
outcome or model forecast was accessed.

## Remaining source work

The same retained pinned catalog has one structurally complete, unprotected,
non-development men's group for review: StatsBomb Serie A 2015/16 (`12/27`),
380 match-list entries, match-list SHA-256
`613cd3cc70699ba613cb1b3c27b4c8a01b0b5fa28415e09c928d020208905c7a`.
It is a catalog candidate only; exact acquisition, xG, point-in-time, target,
and firewall qualification have not passed. Ligue 1 2015/16 (`7/27`) has 377
matches and is only near-complete in the retained structural screen. Other
men's seasons in that 37-scope catalog are below the 120-match floor or
partial. After excluding protected EPL and development La Liga, this pinned
catalog alone cannot supply the frozen three independent groups spanning two
seasons. No alternative men's source has been approved or qualified.

Next: qualify new independent men's sources under
[Decision 2](owner-decision-approve-phase3a-evaluation-v2-corpus-policy-2026-09-21.md)
and the owner product-scope decision. Exact corpus membership, 500 eligible
scored targets, and all hashes remain unresolved. This screen does not alter
Sprint 2 `FAIL`, published forecasts, existing baselines, the required later
Rust simulation route, or any authorization gate.
