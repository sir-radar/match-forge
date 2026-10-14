from dataclasses import replace

from football.product.domain import stable_id
from football.product.identity_admission import _json_identifiers
from football.product.identity_trust import MappingEvidence, qualify_mapping


def _origin() -> MappingEvidence:
    return MappingEvidence(
        "team",
        stable_id("team", "api_football", "42"),
        "api_football",
        "42",
        "deterministic",
        1,
        "England",
        True,
        True,
    )


def test_provider_origin_requires_exact_algorithm_and_retained_identifier() -> None:
    evidence = _origin()
    assert qualify_mapping(evidence)[0] == "ORIGIN_ANCHOR"
    assert (
        qualify_mapping(replace(evidence, canonical_id=stable_id("team", "fotmob", "42")))[0]
        == "CONTRADICTORY"
    )
    assert qualify_mapping(replace(evidence, source_verified=False))[0] == "UNRESOLVED"
    assert qualify_mapping(replace(evidence, source_identifier_verified=False))[0] == "UNRESOLVED"
    assert qualify_mapping(replace(evidence, confidence=0.99))[0] == "UNRESOLVED"


def test_cross_provider_equivalence_requires_crosswalk_and_context() -> None:
    evidence = replace(
        _origin(), provider="fotmob", provider_id="9825", method="explicit_crosswalk"
    )
    assert qualify_mapping(evidence)[0] == "UNRESOLVED"
    verified = replace(
        evidence, crosswalk_target=evidence.canonical_id, crosswalk_context_verified=True
    )
    assert qualify_mapping(verified)[0] == "CROSSWALK"
    assert (
        qualify_mapping(replace(verified, canonical_id=stable_id("team", "api_football", "40")))[0]
        == "CONTRADICTORY"
    )
    assert (
        qualify_mapping(replace(verified, method="manual", manual_evidence_verified=False))[0]
        == "UNRESOLVED"
    )
    assert (
        qualify_mapping(replace(verified, method="manual", manual_evidence_verified=True))[0]
        == "CROSSWALK"
    )


def test_bulk_origin_retains_provider_and_country_scope() -> None:
    origin = replace(
        _origin(),
        provider="openfootball",
        provider_id="Home FC",
        canonical_id=stable_id("team", "openfootball", "Home FC", "England"),
    )
    assert qualify_mapping(origin)[0] == "ORIGIN_ANCHOR"
    assert qualify_mapping(replace(origin, country="Scotland"))[0] == "CONTRADICTORY"
    assert qualify_mapping(replace(origin, country=None))[0] == "UNRESOLVED"


def test_fotmob_league_details_prove_competition_id_only_in_league_resources() -> None:
    payload = {"details": {"id": 47, "name": "Premier League", "country": "ENG"}}
    assert _json_identifiers("fotmob", "competition", payload, "league-47-2026/2027") == {"47"}
    assert _json_identifiers("fotmob", "competition", payload, "match-47") == set()
    assert _json_identifiers("fotmob", "team", payload, "league-47-2026/2027") == set()
