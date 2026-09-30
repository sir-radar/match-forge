# MVP research pause and resume point

Status: `MODEL_RESEARCH_PAUSED_FOR_MVP`

The owner paused H2H model research, further H2H data acquisition, V6, Dixon-Coles, new xG models, calibration experiments, StatsBomb evaluation, player models, xT, VAEP, advanced simulation research, confirmation experiments, and all new forecasting experiments on 29 September 2026. None of the prior evidence or results was changed.

## Latest result

`MATCHFORGE_FIREWALL_SAFE_H2H_HISTORY_EXTENSION_V1` completed as `H2H_DEVELOPMENT_HISTORY_QUALIFIED`. The qualified snapshot is `MATCHFORGE_H2H_DEVELOPMENT_HISTORY_QUALIFIED_V1`, ID `fcb43dd0-5910-55c0-8922-4c1c1e77246a`, SHA-256 `be0b5fb6a0dcc097649d5bfd413cda59b3cafcaaa3188c80fa63f2c13c1e9352`.

The result has 791 targets with at least two prior H2H meetings and 642 with at least three. The chronology and firewall checks passed. Two Mallorca–Girona targets remain quarantined under the frozen pair-completeness rule. No H2H model was fitted or evaluated, no confirmation data was used, and no V6 work occurred.

Evidence: `docs/evidence/matchforge-firewall-safe-h2h-history-extension-v1-result-2026-09-28.json` and its Markdown report.

## Branch, PR, and data

- Relevant branch: `ft/firewall-safe-h2h-history-extension`
- Merged PR: `#131`
- Merge commit: `cea534e`
- Latest useful dataset: the immutable qualified H2H snapshot identified above; its history manifest SHA-256 is `90f9e5343aa1e07ccc2df721d39e4deaee99295615046f806cdadda101c656c4`.

## Exact next step

Do nothing until a new owner decision explicitly resumes research. If resumed, the next bounded step is to authorize or decline `MATCHFORGE_H2H_INCREMENTAL_SIGNAL_RESEARCH_V1`. Authorization must preserve its prepared package, frozen H2H design, development-only scope, point-in-time rules, spent/protected-target firewall, and the existing prohibition on confirmation, promotion, and V6.
