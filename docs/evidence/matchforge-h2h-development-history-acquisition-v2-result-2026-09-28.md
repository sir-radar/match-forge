# MatchForge H2H development-history acquisition V2 result

## Classification

`PROVIDER_DATA_INCOMPLETE`

La Liga 2023/24 remained excluded as `EXCLUDED_FROM_H2H_DEVELOPMENT_HISTORY_V2_PROVIDER_INCOMPLETE`. V1 remains permanently `ACQUISITION_FAILED` with `FULL_SEASON_MATCH_COUNT_MISMATCH`; its 766-file inventory still hashes to `ca156d2f2852551a31d6ba30a04e8e17c5ae2f41a570d0536456e67d323392a3`.

Premier League 2023/24 was independently verified and reused as `REUSED_VERIFIED_V1_RESOURCES`. Serie A 2023/24 returned exactly 380 finished fixtures and acquired 380 shot resources: 9,724 shots, 9,569 valid npxG shots, 131 penalties excluded, and 24 own goals excluded.

## Coverage

The initial three-domain package reached 568 targets with 2+ meetings and 392 with 3+ meetings. All three required competitions passed their 150-target domain floor, but the global 2+ floor was 32 short.

The bounded Premier League 2022/23 extension was mathematically capable of closing the gap, returned exactly 380 fixtures, and acquired 380 shot resources. It raised coverage to:

| Coverage | Targets |
|---|---:|
| Exactly 0 | 201 |
| 1+ | 1,069 |
| 2+ | 593 |
| 3+ | 457 |
| 5+ | 1 |

Per-competition 2+/3+ coverage is Bundesliga 169/120, Premier League 224/201, and Serie A 200/136. All domain floors pass. The global 3+ floor passes by 157; the global 2+ floor remains 7 short.

The remaining Serie A 2022/23 extension could theoretically close that gap, so acquisition proceeded. PitchAPI returned 381 finished fixtures, including the 2023-06-11 relegation playoff, against the frozen exact 380-fixture requirement. The run stopped before requesting any Serie A 2022/23 shot resource.

## Snapshot, backup, and firewall

Two intermediate snapshots were sealed but remain unqualified:

- initial snapshot `db9aca21-c3f0-505c-990e-e48ae070b85c`, SHA-256 `d5364a43c7e4a1f3376bdb001412111b51801a953c28b6dd7c213cc4e4559e9c`;
- Premier League extension snapshot `396a05b9-e577-53d0-9859-a2c6904b2e02`, SHA-256 `207272f01abcbb2c3c98588ca2353e3e296ea9020dd619f2d8aa20e05b6ec1b1`.

Their backup inventory checks passed. The completed-package firewall passed with zero protected intersections, strict prior kickoff, and same-kickoff sealing. No qualified V2 snapshot or final backup was created after the Serie A manifest mismatch.

No H2H model was fitted or evaluated. No V6 work occurred. H2H research remains unsupported.

## Owner boundary

The next owner decision is whether to authorize Bundesliga 2023/24 as a bounded same-league extension. Its theoretical 2+ capacity is sufficient to close the remaining seven-target gap, but acquisition requires separate explicit authorization. No further acquisition is currently authorized.
