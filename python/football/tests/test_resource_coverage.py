from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from football.coverage.resources import (
    CanonicalCoverage,
    CanonicalCoverageScope,
    CoverageError,
    CoverageMetrics,
    ProviderCoverage,
)
from football.providers.resource_capabilities import ResourceScope

NOW = datetime(2026, 10, 18, tzinfo=UTC)
PROVIDER = ResourceScope(
    provider="fotmob", resource_type="results", competition="47", season="2025"
)
CANONICAL = CanonicalCoverageScope(
    competition_id=UUID(int=10), season_id=UUID(int=11), resource_type="results"
)


def test_partial_provider_and_complete_canonical_coverage_can_coexist() -> None:
    provider = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=frozenset(("one", "two")),
        observed_units=frozenset(("one",)),
        qualified_units=frozenset(("one",)),
        evidence_refs=("eligible-input",),
    )
    canonical = CanonicalCoverage(
        scope=CANONICAL,
        knowledge_cutoff=NOW,
        expected_units=frozenset((UUID(int=1), UUID(int=2))),
        qualified_support=frozenset(((UUID(int=1), "fotmob"), (UUID(int=2), "api_football"))),
        evidence_refs=("eligible-input",),
    )
    assert provider.metrics.status == "PARTIAL" and provider.metrics.coverage_ratio == 0.5
    assert canonical.metrics.status == "COMPLETE" and canonical.metrics.coverage_ratio == 1
    assert canonical.supporting_providers == ("api_football", "fotmob")


def test_canonical_fixtures_are_counted_once_across_providers_and_retries() -> None:
    item = CanonicalCoverage(
        scope=CANONICAL,
        knowledge_cutoff=NOW,
        expected_units=frozenset((UUID(int=1),)),
        qualified_support=(
            (UUID(int=1), "fotmob"),
            (UUID(int=1), "fotmob"),
            (UUID(int=1), "api_football"),
        ),
        evidence_refs=("eligible-input",),
    )
    assert item.metrics.qualified == 1 and item.metrics.coverage_ratio == 1
    assert len(item.qualified_support) == 2


@pytest.mark.parametrize("expected", [None, frozenset()])
def test_unknown_or_empty_expectations_never_claim_complete_coverage(
    expected: frozenset[str] | None,
) -> None:
    item = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=expected,
        observed_units=frozenset(),
        qualified_units=frozenset(),
        evidence_refs=("input",),
    )
    assert item.metrics.status == "UNKNOWN" and item.metrics.coverage_ratio is None


def test_raw_observations_do_not_become_qualified_coverage() -> None:
    item = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=frozenset(("one",)),
        observed_units=frozenset(("one",)),
        qualified_units=frozenset(),
        evidence_refs=("input",),
    )
    assert item.observed == 1 and item.metrics.qualified == 0
    assert item.metrics.coverage_ratio == 0 and item.metrics.status == "PARTIAL"


def test_qualification_requires_observation_and_a_consistent_expected_universe() -> None:
    item = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=frozenset(("one",)),
        observed_units=frozenset(("one",)),
        qualified_units=frozenset(("one",)),
        evidence_refs=("input",),
    )
    with pytest.raises(CoverageError, match="observed"):
        replace(item, observed_units=frozenset())
    with pytest.raises(CoverageError, match="expected"):
        replace(item, expected_units=frozenset(("different",)))
    with pytest.raises(CoverageError, match="timezone"):
        replace(item, knowledge_cutoff=NOW.replace(tzinfo=None))


def test_input_order_does_not_change_snapshot_bytes_or_identity() -> None:
    item = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=("two", "one"),
        observed_units=("one", "two", "one"),
        qualified_units=("one", "two"),
        evidence_refs=("input",),
    )
    other = replace(item, expected_units=("one", "two"), qualified_units=("two", "one"))
    assert item.to_bytes() == other.to_bytes() and item.report_id == other.report_id


def test_snapshot_copies_mutable_unit_inputs() -> None:
    observed = {"one"}
    item = ProviderCoverage(
        scope=PROVIDER,
        knowledge_cutoff=NOW,
        expected_units=("one", "two"),
        observed_units=observed,
        qualified_units=(),
        evidence_refs=("input",),
    )
    before = item.to_bytes()
    observed.add("two")
    assert item.observed == 1 and item.to_bytes() == before


def test_equal_counts_with_different_canonical_ids_cannot_claim_complete() -> None:
    with pytest.raises(CoverageError, match="expected"):
        CanonicalCoverage(
            scope=CANONICAL,
            knowledge_cutoff=NOW,
            expected_units=(UUID(int=1),),
            qualified_support=((UUID(int=2), "fotmob"),),
            evidence_refs=("input",),
        )


@pytest.mark.parametrize(
    ("expected", "qualified"), [(None, -1), (-1, 0), (1, 2), (True, 0), (1, False)]
)
def test_invalid_counts_cannot_construct_coverage_metrics(expected: Any, qualified: Any) -> None:
    with pytest.raises(CoverageError):
        CoverageMetrics(expected, qualified)
