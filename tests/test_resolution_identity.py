"""Resolution review never upgrades name resemblance into identity proof."""

import pytest
from football.product.domain import normalize_team_name
from football.product.resolution_identity import review_status


def test_verified_requires_both_admission_and_current_qualification():
    assert review_status("CROSSWALK", True, True) == "VERIFIED"
    assert review_status("CROSSWALK", False, True) == "NEEDS_REVIEW"
    assert review_status("UNRESOLVED", True, True) == "BLOCKED"
    assert review_status("REVOKED", False, True) == "BLOCKED"
    assert review_status("CONTRADICTORY", False, True) == "CONTRADICTORY"
    assert review_status("UNRESOLVED", False, False) == "UNRESOLVED"


def test_aliases_keep_category_markers_and_use_existing_normalization():
    assert normalize_team_name("Manchester Utd FC") == "manchester united"
    assert normalize_team_name("Chelsea Women") != normalize_team_name("Chelsea")
    assert normalize_team_name("Chelsea U21") != normalize_team_name("Chelsea")
    assert normalize_team_name("Chelsea B") != normalize_team_name("Chelsea")


@pytest.mark.parametrize("disposition", ["ORIGIN_ANCHOR", "CROSSWALK"])
@pytest.mark.parametrize("has_candidates", [False, True])
def test_qualified_mapping_still_needs_a_trusted_admission(disposition, has_candidates):
    assert review_status(disposition, False, has_candidates) == "NEEDS_REVIEW"
    assert review_status(disposition, True, has_candidates) == "VERIFIED"


def test_missing_source_evidence_is_blocked_even_with_a_name_candidate():
    assert (
        review_status("UNRESOLVED", False, True, "RETAINED_SOURCE_EVIDENCE_REQUIRED") == "BLOCKED"
    )


@pytest.mark.parametrize("kind", ["team", "competition"])
@pytest.mark.parametrize("method", ["provider_native", "deterministic"])
def test_statsbomb_native_surrogate_is_never_an_admitted_origin(kind, method):
    from uuid import UUID

    from football.product.identity_trust import MappingEvidence, origin_id, qualify_mapping

    legacy = UUID("01a051db-5a79-70bd-82d2-b457afa0ae99")
    evidence = MappingEvidence(
        kind, legacy, "statsbomb_open_data", "1", method, 1.0, "England", True, True
    )
    assert origin_id(kind, "statsbomb_open_data", "1", "England") is None
    disposition, reason = qualify_mapping(evidence)
    assert disposition == "UNRESOLVED"
    assert reason == (
        "UNSUPPORTED_ORIGIN_ALGORITHM" if method == "deterministic" else "REVIEW_EVIDENCE_REQUIRED"
    )
