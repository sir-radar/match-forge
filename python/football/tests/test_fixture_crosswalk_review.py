from copy import deepcopy
from typing import Any

import pytest
from football.product.fixture_crosswalk_review import review_competition, review_teams


def pair() -> dict[str, Any]:
    context = {
        "country": "England",
        "season": "2026",
        "kickoff": "2026-10-17T14:00:00Z",
        "gender": "male",
        "division": 1,
        "team_variant": "senior",
        "home_name": "Home FC",
        "away_name": "Away FC",
        "finished": True,
        "score": [2, 1],
    }
    return {
        "source_verified": True,
        "target_verified": True,
        "target_admitted": True,
        "source": {**context, "home_id": "10", "away_id": "20"},
        "target": {**context, "home_id": "home", "away_id": "away", "competition_id": "league"},
    }


def metadata() -> dict[str, Any]:
    return {"requested_id": "47", "fotmob_competition_id": "47", "provider_name": "Premier League"}


@pytest.mark.parametrize("name", ["Premier League", "Cup", "League", "Championship"])
def test_generic_name_without_fixture_evidence_never_qualifies(name: str) -> None:
    assert (
        review_competition({**metadata(), "provider_name": name}, [])["classification"]
        == "INSUFFICIENT_EVIDENCE"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("country", "Ghana"),
        ("gender", "female"),
        ("division", 2),
        ("team_variant", "youth"),
        ("kickoff", "later"),
        ("season", "2024"),
        ("score", [1, 2]),
        ("away_name", "Other Club"),
    ],
)
def test_independent_conflict_blocks_both_competition_and_team(field: str, value: object) -> None:
    witness = pair()
    witness["target"][field] = value
    assert review_competition(metadata(), [witness])["classification"] == "CONTRADICTORY"
    assert all(row["classification"] == "CONTRADICTORY" for row in review_teams([witness]))


def test_verified_fixture_correspondence_is_a_proposal_and_is_deterministic() -> None:
    witness = pair()
    first = review_competition(metadata(), [witness])
    assert first == review_competition(metadata(), [deepcopy(witness)])
    assert first["classification"] == "QUALIFIED_EXPLICIT_CROSSWALK"
    assert first["canonical_candidate_id"] == "league"
    assert len(review_teams([witness])) == 2


def test_same_provider_id_cannot_propose_two_target_teams() -> None:
    first, second = pair(), pair()
    second["target"]["home_id"] = "other-home"
    assert review_teams([first, second])[0]["classification"] == "CONTRADICTORY"


@pytest.mark.parametrize("field", ["source_verified", "target_verified", "target_admitted"])
def test_source_integrity_and_target_admission_are_required(field: str) -> None:
    witness = pair()
    witness[field] = False
    assert review_competition(metadata(), [witness])["classification"] == "CONTRADICTORY"


def test_wrong_provider_registration_is_held() -> None:
    assert (
        review_competition({**metadata(), "requested_id": "55"}, [pair()])["classification"]
        == "WRONG_PROVIDER_REGISTRATION"
    )


def test_international_competition_does_not_select_a_participants_country() -> None:
    witness = pair()
    witness["source"]["country"] = witness["target"]["country"] = "International"
    assert (
        review_competition(metadata(), [witness])["classification"]
        == "QUALIFIED_EXPLICIT_CROSSWALK"
    )


def test_qualified_date_only_result_can_support_identity_but_not_a_different_day() -> None:
    witness = pair()
    witness["target"].update(kickoff="2026-10-17T00:00:00Z", kickoff_precision="DATE_ONLY")
    assert (
        review_competition(metadata(), [witness])["classification"]
        == "QUALIFIED_EXPLICIT_CROSSWALK"
    )
    witness["target"]["kickoff"] = "2026-10-18T00:00:00Z"
    assert review_competition(metadata(), [witness])["classification"] == "CONTRADICTORY"
    witness["target"].update(kickoff="2026-10-17T00:00:00Z", finished=False)
    assert review_competition(metadata(), [witness])["classification"] == "CONTRADICTORY"


def test_historical_name_change_needs_fixture_evidence_and_reserve_variant_stays_separate() -> None:
    witness = pair()
    witness["target"]["home_name"] = "Former Home"
    assert review_teams([witness])[0]["classification"] == "CONTRADICTORY"
    witness["target"].update(home_name="Home FC", team_variant="reserve")
    assert review_teams([witness])[0]["classification"] == "CONTRADICTORY"


def test_composite_catalogue_cannot_prove_a_crosswalk_to_one_division() -> None:
    result = review_competition(
        {
            **metadata(),
            "component_names": ["North", "South"],
            "target_competition_name": "U18 Premier League - South",
        },
        [pair()],
    )
    assert result["classification"] == "INSUFFICIENT_EVIDENCE"
    assert result["blocker"] == "COMPOSITE_COMPETITION_TARGET_IS_A_COMPONENT"


def test_group_catalogue_can_correspond_to_the_same_parent_competition() -> None:
    result = review_competition(
        {
            **metadata(),
            "component_names": ["Group A", "Group B"],
            "target_competition_name": "Premier League",
        },
        [pair()],
    )
    assert result["classification"] == "QUALIFIED_EXPLICIT_CROSSWALK"
