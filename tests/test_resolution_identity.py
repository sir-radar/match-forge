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
