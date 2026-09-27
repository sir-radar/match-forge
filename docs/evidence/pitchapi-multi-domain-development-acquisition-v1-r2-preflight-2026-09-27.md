# PitchAPI multi-domain acquisition revision 2 preflight

Revision 1 stopped after one catalog request because its implementation used
`DEU` for Germany. PitchAPI's retained catalog response identifies the exact
authorized Bundesliga as `Bundesliga / GER / l_1Isor4` and advertises both
2024/25 and 2025/26. No group is replaced or added.

The stopped revision remains immutable at
`.local/pitchapi-multi-domain-development-v1`. Its raw catalog SHA-256 is
`0d484d91290a7429da1c93ab5f00c52c69cb0e867fe15ef3aab8ad6ddda28744`.

Revision 2 uses a new root,
`.local/pitchapi-multi-domain-development-v1-r2`. It still expects 1,758 calls.
Because revision 1 consumed one task call, revision 2 has 35 retry calls and a
1,793-call local ceiling. The task-wide hard ceiling remains exactly 1,794.

All five development-only groups, storage boundaries, scientific firewalls,
and prohibited actions remain unchanged.
