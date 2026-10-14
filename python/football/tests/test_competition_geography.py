import pytest
from football.product.competition_geography import (
    canonical_geographic_scope,
    country_name,
    geography_rows,
)


@pytest.mark.parametrize(
    "provider,identifier,country,scope",
    [
        ("api_football", "39", "England", "England"),  # domestic league
        ("api_football", "45", "England", "England"),  # domestic cup
        ("api_football", "40", "England", "England"),  # lower division
        ("api_football", "850", "World", "International"),  # international qualifier
        ("api_football", "10", "World", "International"),  # national-team friendly
        ("api_football", "2", "World", "International"),  # continental clubs
        ("api_football", "667", "World", "International"),  # club friendly, any venue
        ("api_football", "friendly-tournament", "France", "France"),
        ("openfootball", "ar.1", "World", "Argentina"),  # legacy identity country
        ("openfootball", "uefa.cl", "World", "International"),
        ("openfootball", "cn.1", "World", "China"),
        ("football_data_uk", "CZE", "Czech Republic", "Czech-Republic"),
        ("football_data_uk", "SC1", "World", "Scotland"),
        ("football_data_uk", "SC2", "World", "Scotland"),
        ("football_data_uk", "SC3", "World", "Scotland"),
    ],
)
def test_competition_scope_preserves_domestic_and_international_semantics(
    provider: str, identifier: str, country: str, scope: str
) -> None:
    assert canonical_geographic_scope(provider, identifier, country) == scope


def test_missing_competition_country_requires_evidence() -> None:
    assert canonical_geographic_scope("fotmob", "47", None) is None
    assert canonical_geographic_scope("pitchapi", "l_Unknown", "Unknown") is None


def test_provider_country_codes_are_display_metadata_only() -> None:
    assert country_name("MAR") == "Morocco"
    assert country_name("IRN") == "Iran"
    assert country_name("ENG") == "England"
    assert country_name("INT") == "International"
    assert country_name("INT-2") == "International"
    assert country_name("UNKNOWN") is None
    assert country_name(None) is None


def test_fotmob_uses_exact_competition_id_and_retained_country_field() -> None:
    payload = {"leagues": [{"id": 943230, "primaryId": 42, "ccode": "INT"}]}
    assert geography_rows("fotmob", payload) == [("943230", "INT")]
    assert geography_rows("fotmob", {"details": {"id": 530, "country": "MAR"}}) == [("530", "MAR")]


def test_pitchapi_country_comes_from_catalogue_not_team_or_league_names() -> None:
    payload = {"data": {"leagues": [{"id": "l_0eg6C9", "country_code": "USA"}]}}
    assert geography_rows("pitchapi", payload) == [("l_0eg6C9", "USA")]
    assert (
        geography_rows(
            "pitchapi",
            {
                "data": {
                    "matches": [
                        {"league": {"id": "l_0eg6C9", "name": "MLS"}, "country_code": "USA"}
                    ]
                }
            },
        )
        == []
    )


def test_missing_or_malformed_metadata_does_not_invent_a_country() -> None:
    assert geography_rows("fotmob", {"leagues": [{"id": 47, "name": "Premier League"}]}) == []
    assert geography_rows("fotmob", {"leagues": [{"id": True, "ccode": "ENG"}]}) == []
    assert geography_rows("pitchapi", {"data": {"leagues": [None]}}) == []
