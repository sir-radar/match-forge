# PitchAPI multi-domain acquisition revision 3 preflight

Revision 2 stopped after the exact Bundesliga 2024/25 manifest contained one
provider-labelled `awarded` fixture. The existing MatchForge validator correctly
rejects non-finished fixtures. Revision 3 quarantines every non-`finished`
fixture before shot acquisition, target construction, and history updates. It
does not silently treat an awarded result as an ordinary played match.

The nominal season count must still equal the frozen group count. Every retained
fixture still passes the existing manifest validator. Quarantined fixture counts
and statuses are reported by group. This is an explicit provider-semantics
exclusion, not a substitute group.

Revisions 1 and 2 used three requests in total. Revision 3 keeps the 1,758-call
maximum expected plan, reduces the retry allowance to 33, and has a 1,791-call
local ceiling. The task-wide hard ceiling remains exactly 1,794.

The output root is a new immutable revision at
`.local/pitchapi-multi-domain-development-v1-r3`. All five groups, scientific
firewalls, storage limits, and prohibited actions remain unchanged.
