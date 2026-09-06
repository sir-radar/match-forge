# Phase 1B/2B gate checksum correction

Status: reviewed on 2026-09-06

This is an immutable correction record. It preserves the earlier gate record
and corrects only its stated SHA-256 value.

## Corrected claim

[`phase1b2b-gate-2026-09-06-outcome-scope.md`](phase1b2b-gate-2026-09-06-outcome-scope.md)
states SHA-256
`a0e7215fc68aff86e82aa65de65036377814e8419ba79ba0c4e7cefa16f18af8` for
[`phase1b2b-gate-2026-09-06-outcome-scope.json`](phase1b2b-gate-2026-09-06-outcome-scope.json).
That claim is incorrect.

The exact committed JSON bytes are from commit
`31a91d3d77d5018fe0a2fc3546510c8d06304fa3`, blob
`962c57e24941705c5bbab13eb4cf92537dd195a2`. Their SHA-256 is:

`a70084ece1f32d462e50c5e8227124d592df75a7a9fcea82b444e46a55ff1da2`

Reproduce it with:

```text
git show 31a91d3d77d5018fe0a2fc3546510c8d06304fa3:docs/evidence/phase1b2b-gate-2026-09-06-outcome-scope.json | shasum -a 256
```

[`phase1b2b-gate-2026-09-06-outcome-scope-checksum-correction.json`](phase1b2b-gate-2026-09-06-outcome-scope-checksum-correction.json)
records this correction with the original gate execution commit
`30bd41a4d13c95fa0a7dd5391080d48e62a953d7` and dependency-lock SHA-256
`d14def6539f213b2af3011975062ed3e1e0bba2d86e8064803bd3d86d0a39e4e`.

## Result

The checksum discrepancy does not change executed gate inputs or results:

```text
Phase 1B = PASS
Phase 2B = PASS
combined Phase 1B/2B gate = PASS

Sprint 2 = FAIL
RETAIN_FAIL_AND_STOP = preserved
Phase 3 = BLOCKED
```

The earlier evidence remains unchanged. This record supersedes only its
incorrect checksum claim.
