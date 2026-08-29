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
