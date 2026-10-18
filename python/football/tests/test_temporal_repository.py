import uuid
from datetime import datetime
from typing import Any, cast

import pytest
from football.temporal.repository import PointInTimeRepository
from psycopg import Connection


class ConnectionNotUsed:
    pass


def test_point_in_time_query_rejects_naive_cutoff_before_database_access() -> None:
    connection = cast(Connection[Any], ConnectionNotUsed())
    repository = PointInTimeRepository(connection)

    with pytest.raises(ValueError, match="knowledge_cutoff must include a timezone"):
        repository.player_observation_at(
            player_id=uuid.uuid4(),
            provider_id=uuid.uuid4(),
            knowledge_cutoff=datetime(2026, 1, 1),
        )


@pytest.mark.parametrize("field", ["knowledge_cutoff", "football_cutoff", "valid_at"])
def test_resource_observation_query_rejects_naive_times_before_database_access(field: str) -> None:
    from datetime import UTC

    repository = PointInTimeRepository(cast(Connection[Any], ConnectionNotUsed()))
    times = {"knowledge_cutoff": datetime(2026, 1, 1, tzinfo=UTC)}
    times[field] = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match=f"{field} must include a timezone"):
        repository.resource_observation_ids_at(
            "LineupObservationV2",
            uuid.uuid4(),
            times["knowledge_cutoff"],
            football_cutoff=times.get("football_cutoff"),
            valid_at=times.get("valid_at"),
        )
