# PitchAPI V5 calibration successor decision package

## Status

`PROPOSED — OWNER AUTHORIZATION REQUIRED`

V5 remains `REFERENCE_RETAINED`. The current challenger is `EVALUATED_REJECTED_CALIBRATION`. Its predictive scores were better than the reference, but 14 frozen calibration gates failed.

## Exact research hypothesis

The transferable npxG challenger contains useful ranking signal, but outcome- and domain-dependent logit scale and level mismatch compresses its raw 1X2 probabilities. Calibration with shrinkage, trained only on prior out-of-sample development predictions, may improve held-out calibration without losing proper-score gains.

## Proposed development-only route

The currently available development population is exactly Bundesliga 2021/22: 216 targets under development manifest `be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e`. Generate chronological out-of-sample raw forecasts before fitting any calibrator. This population can support global-calibration feasibility and leave-team-out checks. It cannot support leave-domain-out validation or admit a hierarchical/domain-specific calibrator.

For raw 1X2 probabilities `p`, the proposed global vector-scaling candidate is:

```text
q = softmax(a + b ⊙ log(p))
```

with one identified reference component and shrinkage of `a` toward `0` and `b` toward `1`. A future partially pooled candidate, only if separately authorized multi-domain development data exist, is:

```text
q_d = softmax(a + u_d + (b + v_d) ⊙ log(p))
```

with zero-centred domain effects `u_d` and `v_d` under precommitted shrinkage. Both forms preserve a normalized three-outcome distribution. Raw probabilities remain unchanged and separately identifiable.

Compare:

1. unchanged raw probabilities;
2. one domain-independent shrinkage calibrator;
3. one partially pooled outcome/domain calibrator.

Preserve raw probabilities. Fit calibration from prior out-of-sample predictions only. Use chronological folds, same-kickoff isolation, and leave-team-out checks. Leave-domain-out validation and the partially pooled candidate remain blocked until separately authorized non-V5 development domains exist.

Do not use V5 outcomes to fit parameters, select a calibrator, tune shrinkage, set thresholds, or admit a candidate. V5 may support post-hoc interpretation only.

## Candidate admission boundary

No successor candidate is currently admitted. Proposed admission requires finite, converged fits and the existing V5 inequalities on held-out development predictions:

- primary macro joint-score log-loss delta at most `-0.01`, with bootstrap upper bound below `0`;
- secondary macro interval upper bounds no greater than `0.02` for 1X2 log loss, `0.01` for Brier, `0.01` for RPS, and `0.02` for total-goal CRPS;
- every domain joint-score log-loss interval upper bound no greater than `0.05`;
- for every outcome/domain, challenger-minus-reference absolute intercept error no greater than `0.05` and absolute slope-distance-from-one difference no greater than `0.1`.

Before implementation, an owner decision must also freeze:

- whether research is restricted to the existing Bundesliga 2021/22 manifest or separately authorized development domains are added;
- mathematical forms and regularization;
- chronological fold and same-kickoff rules;
- leave-team-out and leave-domain-out procedures;
- calibration and proper-score admission criteria;
- deterministic artifact identity and reproduction rules;
- an untouched confirmation-population requirement.

## Untouched confirmation proposal

`PITCHAPI_CONFIRMATION_EVALUATION_V1` should use competition-seasons not used for V5 model selection or the proposed development work. It should include more than one competition and, where feasible, more than one season, unseen teams, the same transferable forecast contract, and calibration requirements at least as strict as V5.

Before outcomes are inspected, freeze source snapshots, identity mapping, target membership, point-in-time rules, same-kickoff batching, reference and challenger artifacts, metrics, uncertainty procedure, calibration gates, aggregation, Rust parity rules, success criteria, and immutable evidence schemas. Data acquisition and execution require separate owner decisions.

## Next owner decision

Authorize or reject preparation and implementation of the development-only calibration comparison above. Authorization would not permit V5 reuse for fitting or model selection, confirmation-data acquisition, authoritative confirmation execution, promotion, or V6.
