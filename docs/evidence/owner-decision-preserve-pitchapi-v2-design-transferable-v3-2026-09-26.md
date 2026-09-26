# Preserve PitchAPI V2 and design transferable V3

Decision ID: `PRESERVE_PITCHAPI_V2_AND_DESIGN_TRANSFERABLE_V3_V1`

PitchAPI V2 remains frozen and unexecuted with disposition
`BLOCKED_PRE_EXECUTION_MODEL_NON_TRANSFERABILITY`. Its development artifacts
contain fitted parameters for 18 teams; the evaluation manifests identify 40
teams, with 24 lacking fitted parameters. This is an applicability failure, not
an evaluation-performance failure.

No evaluation outcome was loaded, no evaluation was executed, and the previous
execution authorization remains unused. Only manifest and canonical team
identity structure exposed the mismatch.

The owner authorized design and freeze work for
`PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V3`. V3 may change model applicability
and team-state construction but may not adapt to evaluation performance. The
PitchAPI snapshot and StatsBomb `EVALUATION_V2` remain unchanged.
