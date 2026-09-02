import pytest
from football.contracts import CompetitionRulesError, CompetitionRulesV1


def test_competition_rules_distinguish_league_regulation_semantics() -> None:
    rules = _rules()

    assert rules.to_dict()["competition_format"] == "LEAGUE"
    assert rules.to_dict()["outcome_scope"] == "REGULATION_TIME"
    assert len(rules.sha256) == 64


def test_competition_rules_support_knockout_extra_time_and_shootout() -> None:
    rules = _rules(
        competition_format="KNOCKOUT",
        tie_structure="TWO_LEG",
        outcome_scope="INCLUDING_SHOOTOUT",
        extra_time_policy="POSSIBLE",
        shootout_policy="POSSIBLE",
        neutral_venue_policy="ALLOWED",
    )

    assert rules.tie_structure == "TWO_LEG"
    assert rules.shootout_policy == "POSSIBLE"


def test_competition_rules_reject_duplicate_sources_and_unknown_format() -> None:
    with pytest.raises(CompetitionRulesError, match="source references"):
        _rules(source_refs=("catalog", "catalog"))
    with pytest.raises(CompetitionRulesError, match="format"):
        _rules(competition_format="CUP")


def _rules(**overrides: object) -> CompetitionRulesV1:
    values: dict[str, object] = {
        "rules_id": "rules-epl-v1",
        "competition_ref": "competition-epl",
        "competition_format": "LEAGUE",
        "tie_structure": "ROUND_ROBIN",
        "outcome_scope": "REGULATION_TIME",
        "extra_time_policy": "NEVER",
        "shootout_policy": "NEVER",
        "neutral_venue_policy": "NOT_APPLICABLE",
        "policy_version": "competition-rules-v1",
        "source_refs": ("competition-catalog-v1",),
    }
    values.update(overrides)
    return CompetitionRulesV1(**values)  # type: ignore[arg-type]
