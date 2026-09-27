# PitchAPI V5 calibration post-hoc diagnosis

`PITCHAPI_V5_CALIBRATION_POSTHOC_RESEARCH_V1` is descriptive research. It does not change V5, fit calibration parameters, select a model, authorize promotion, or authorize another evaluation.

V5 produced favorable proper-score deltas but failed 14 frozen calibration gates: six intercept and eight slope failures. Failures covered home, draw, and away probabilities. Eight of nine challenger calibration slopes exceeded one; the main descriptive pattern is probabilities that are too compressed. The Bundesliga 2022/23 draw fit is a noisy exception with a negative slope and large uncertainty.

All six failed intercepts were positive. Their size and the slope differences varied by competition. npxG distributions differed significantly for every domain pair, while FastBreak, FreeKick, FromCorner, RegularPlay, and SetPiece showed significant situation-level differences in at least one comparison. These observations support a scale-mismatch hypothesis but do not establish that npxG scale or any shot situation caused the calibration failures.

A bounded successor research hypothesis is justified. Existing development data are exactly the 216-target Bundesliga 2021/22 population bound by development manifest `be4251a4f53307bae0895c856b5a9ffdf21cdd64da9f0610c8273924d4bef62e`. It can support global-calibration feasibility with chronological out-of-sample and leave-team-out checks, but it cannot admit a hierarchical or cross-domain calibrator. Additional development domains would require separate authorization. Evidence is insufficient to choose global, hierarchical, or feature-redesign treatment. No successor model is admitted.
