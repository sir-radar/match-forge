from football.product.competition_geography import country_name, geography_rows


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
