# Model artifact and promotion governance

## Immutable identities

A fit execution is separate from fitted state. `ModelFitSpecV1` binds model family, algorithm and
configuration checksums, point-in-time scope, Git commit, dependency lock, and random seed.
Equivalent fit specifications converge on one registered artifact even when competing callers
supply different UUIDs.

Canonical model state uses JSON, never pickle. Each artifact has:

- Physical file checksum and byte size.
- Logical canonical-state checksum.
- Schema, algorithm, serializer, and loader versions.
- Python runtime compatibility declaration.
- Feature-contract compatibility declaration.
- Dataset, source, feature, football-time, knowledge-time, knowledge-mode, and quality lineage.

Loaders verify manifest bytes, state bytes, schema support, serializer support, compatibility, and
logical identity before returning state. Dixon-Coles and corner round-trip tests compare predictions
before and after serialization.

## Forecast identity

Forecasts bind canonical match ID, prediction cutoff, point-in-time scope, label-free context
checksum, exact primary artifact IDs, optional calibrator artifact ID, probability contract,
output version, and payload checksum. Raw and calibrated variants are distinct. Semantic retries
converge on one registered forecast even when caller UUIDs differ.

## Evaluation and promotion

Evaluation reports are canonical immutable JSON registered in PostgreSQL with policy version,
dataset/source lineage, target set, checksum, completion time, and `PASS`,
`PASS_WITH_WARNINGS`, or `FAIL` status.

Promotion events are append-only. Approval requires a non-failed evaluation. Baseline approval
cannot target a calibration artifact; calibration approval requires one. Retirements remain explicit
events. Mutable labels never replace artifact UUIDs inside historical forecasts.
