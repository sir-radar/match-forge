# PitchAPI V2 final alias reconciliation

Status: `PASS`

The complete frozen PitchAPI inventory was compared with every retained
StatsBomb development, protected, candidate and excluded-product dataset.
PitchAPI covers Bundesliga 2021/22–2023/24 and Ligue 1 2022/23. The StatsBomb
inventory covers La Liga 2015/16, Premier League 2015/16, Serie A 2015/16 and
Liga F 2023/24. The competition-season sets are disjoint.

Results:

- 1,298 PitchAPI match aliases map one-to-one to 1,298 MatchForge match IDs;
- 42 PitchAPI team aliases map one-to-one to 42 MatchForge team IDs;
- zero PitchAPI internal match overlap;
- zero governed competition-season overlap with the retained StatsBomb data;
- zero exact MatchForge ID collision across providers;
- zero protected or development/evaluation fixture overlap;
- zero unresolved or ambiguous aliases; and
- zero fixture exclusions.

The exact-ID result is supporting evidence only. PitchAPI UUIDv5 allocations
are provider-namespaced, so zero UUID intersection does not prove different
real-world fixtures. The PASS rests on the disjoint governed competition-season
scopes. Any future StatsBomb Bundesliga 2023/24 or Ligue 1 2022/23 data is
overlapping by scope and requires a new reconciliation before use.

The machine-readable report records every dataset, competition/season ID,
manifest hash, MatchForge match-ID set hash, PitchAPI alias hash and target-ID
set hash. No snapshot file was changed.
