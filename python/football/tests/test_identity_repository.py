from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from football.identity.repository import IdentityRepository
from football.ingestion.resolution import ResolutionSubjectV1
from psycopg import Connection


@pytest.mark.parametrize("field", ["knowledge_cutoff", "valid_at"])
def test_identity_times_require_timezones_before_database_access(field: str) -> None:
    times = {
        "knowledge_cutoff": datetime(2026, 1, 1, tzinfo=UTC),
        "valid_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    times[field] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match=f"{field} must include a timezone"):
        IdentityRepository(cast(Connection[Any], object())).mapping_at(
            "team",
            uuid4(),
            "native",
            valid_at=times["valid_at"],
            knowledge_cutoff=times["knowledge_cutoff"],
        )


@pytest.mark.parametrize(
    ("subject", "native", "scope"),
    [
        ("manager", "native", None),
        ("team", "", None),
        ("season", "native", None),
        ("season", "native", ""),
        ("team", "native", "competition"),
    ],
)
def test_identity_queries_reject_unavailable_namespaces_or_ambiguous_scope(
    subject: str, native: str, scope: str | None
) -> None:
    with pytest.raises(ValueError):
        IdentityRepository(cast(Connection[Any], object())).mapping_at(
            cast(ResolutionSubjectV1, subject),
            uuid4(),
            native,
            provider_competition_id=scope,
            valid_at=datetime(2026, 1, 1, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_admission_query_rejects_naive_knowledge_before_database_access() -> None:
    with pytest.raises(ValueError, match="knowledge_cutoff must include a timezone"):
        IdentityRepository(cast(Connection[Any], object())).admitted_identity_at(
            "team", uuid4(), datetime(2026, 1, 1)
        )
