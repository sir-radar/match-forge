from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import psycopg
import pytest
from football.identity.repository import IdentityRepository
from psycopg import sql
from psycopg.errors import RaiseException
from test_canonical_storage import _source_lineage

VALID_AT = datetime(2026, 10, 16, tzinfo=UTC)
SPECS = {
    "competition": ("competition_provider_mappings", "competition_id", "provider_competition_id"),
    "season": ("season_provider_mappings", "season_id", "provider_season_id"),
    "team": ("team_provider_mappings", "team_id", "provider_team_id"),
    "player": ("player_provider_mappings", "player_id", "provider_player_id"),
    "match": ("match_provider_mappings", "match_id", "provider_match_id"),
}


@pytest.fixture
def connection() -> Iterator[psycopg.Connection[Any]]:
    with (
        psycopg.connect(os.environ["TEST_DATABASE_URL"]) as database,
        database.transaction(force_rollback=True),
    ):
        yield database


def _mapping(
    connection: psycopg.Connection[Any],
    subject: str,
    suffix: str = "one",
    *,
    source_acquired_at: datetime | None = None,
) -> dict[str, Any]:
    provider, snapshot, _ = _source_lineage(connection, "identity_" + subject + "_" + suffix)
    if source_acquired_at is not None:
        connection.execute(
            "UPDATE football.source_snapshots SET acquired_at=%s WHERE id=%s",
            (source_acquired_at, snapshot),
        )
    competition = connection.execute(
        "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
    ).fetchone()[0]
    season = connection.execute(
        "INSERT INTO football.seasons(competition_id) VALUES (%s) RETURNING id", (competition,)
    ).fetchone()[0]
    if subject == "competition":
        canonical = competition
    elif subject == "season":
        canonical = season
    elif subject == "match":
        canonical = connection.execute(
            "INSERT INTO football.matches(competition_id,season_id) VALUES (%s,%s) RETURNING id",
            (competition, season),
        ).fetchone()[0]
    else:
        table = "teams" if subject == "team" else "players"
        canonical = connection.execute(
            sql.SQL("INSERT INTO football.{} DEFAULT VALUES RETURNING id").format(
                sql.Identifier(table)
            )
        ).fetchone()[0]
    table, canonical_column, native_column = SPECS[subject]
    columns = [
        canonical_column,
        "provider_id",
        native_column,
        "first_seen_at",
        "last_seen_at",
        "mapping_method",
        "mapping_confidence",
        "source_snapshot_id",
    ]
    values = [canonical, provider, "native-one", VALID_AT, VALID_AT, "deterministic", 1.0, snapshot]
    if subject == "season":
        columns.append("provider_competition_id")
        values.append("native-competition")
    before = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    mapping = connection.execute(
        sql.SQL("INSERT INTO football.{} ({}) VALUES ({}) RETURNING id").format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in values),
        ),
        values,
    ).fetchone()[0]
    return {
        "subject_type": subject,
        "provider_id": provider,
        "provider_entity_id": "native-one",
        "provider_competition_id": "native-competition" if subject == "season" else None,
        "canonical_id": canonical,
        "mapping_id": mapping,
        "source_snapshot_id": snapshot,
        "before": before,
    }


def _read(connection: psycopg.Connection[Any], mapping: dict[str, Any], cutoff: datetime):
    return IdentityRepository(connection).mapping_at(
        mapping["subject_type"],
        mapping["provider_id"],
        mapping["provider_entity_id"],
        provider_competition_id=mapping["provider_competition_id"],
        valid_at=VALID_AT,
        knowledge_cutoff=cutoff,
    )


def _latest(connection: psycopg.Connection[Any], mapping: dict[str, Any]) -> datetime:
    return connection.execute(
        "SELECT max(known_at) FROM football.provider_mapping_history "
        "WHERE subject_type=%s AND mapping_id=%s",
        (mapping["subject_type"], mapping["mapping_id"]),
    ).fetchone()[0]


@pytest.mark.parametrize("subject", SPECS)
def test_existing_identity_namespaces_have_traceable_historical_mapping_reads(connection, subject):
    mapping = _mapping(connection, subject)
    assert _read(connection, mapping, mapping["before"]) == ()
    rows = _read(connection, mapping, _latest(connection, mapping))
    assert len(rows) == 1
    assert rows[0].canonical_id == mapping["canonical_id"]
    assert rows[0].mapping_id == mapping["mapping_id"]
    assert rows[0].source_snapshot_id == mapping["source_snapshot_id"]


def test_backdated_validity_change_does_not_rewrite_prior_mapping_knowledge(connection):
    mapping = _mapping(connection, "team")
    cutoff = _latest(connection, mapping)
    original = _read(connection, mapping, cutoff)
    connection.execute(
        "UPDATE football.team_provider_mappings SET valid_to=%s WHERE id=%s",
        (VALID_AT, mapping["mapping_id"]),
    )
    assert _read(connection, mapping, cutoff) == original
    assert _read(connection, mapping, _latest(connection, mapping)) == ()


def test_native_relabel_uses_latest_mapping_state_before_matching_the_native_key(connection):
    mapping = _mapping(connection, "team")
    cutoff = _latest(connection, mapping)
    connection.execute(
        "UPDATE football.team_provider_mappings SET provider_team_id='native-two' WHERE id=%s",
        (mapping["mapping_id"],),
    )
    later = _latest(connection, mapping)
    assert len(_read(connection, mapping, cutoff)) == 1
    assert _read(connection, mapping, later) == ()
    changed = {**mapping, "provider_entity_id": "native-two"}
    assert _read(connection, changed, cutoff) == ()
    assert len(_read(connection, changed, later)) == 1


def test_mapping_deletion_is_recorded_without_losing_earlier_identity(connection):
    mapping = _mapping(connection, "player")
    cutoff = _latest(connection, mapping)
    original = _read(connection, mapping, cutoff)
    connection.execute(
        "DELETE FROM football.player_provider_mappings WHERE id=%s", (mapping["mapping_id"],)
    )
    assert _read(connection, mapping, cutoff) == original
    assert _read(connection, mapping, _latest(connection, mapping)) == ()


def test_last_seen_touch_does_not_create_an_identity_change(connection):
    mapping = _mapping(connection, "team")
    before = connection.execute(
        "SELECT count(*) FROM football.provider_mapping_history"
    ).fetchone()[0]
    connection.execute(
        "UPDATE football.team_provider_mappings SET last_seen_at=clock_timestamp() WHERE id=%s",
        (mapping["mapping_id"],),
    )
    assert (
        connection.execute("SELECT count(*) FROM football.provider_mapping_history").fetchone()[0]
        == before
    )


def test_mapping_history_is_append_only(connection):
    _mapping(connection, "team")
    for statement in (
        "UPDATE football.provider_mapping_history SET provider_entity_id='changed'",
        "DELETE FROM football.provider_mapping_history",
        "TRUNCATE football.provider_mapping_history",
    ):
        with pytest.raises(RaiseException, match="immutable"), connection.transaction():
            connection.execute(statement)


def test_original_mapping_identifiers_remain_immutable(connection):
    mapping = _mapping(connection, "team")
    with pytest.raises(RaiseException, match="identifiers are immutable"), connection.transaction():
        connection.execute(
            "UPDATE football.team_provider_mappings SET id=uuidv7() WHERE id=%s",
            (mapping["mapping_id"],),
        )


def test_mapping_truncation_cannot_bypass_recorded_identity_changes(connection):
    _mapping(connection, "competition")
    with pytest.raises(RaiseException, match="recorded row changes"), connection.transaction():
        connection.execute("TRUNCATE football.competition_provider_mappings CASCADE")


def test_rollback_removes_mapping_and_its_history_together(connection):
    before = connection.execute(
        "SELECT count(*) FROM football.provider_mapping_history"
    ).fetchone()[0]
    with connection.transaction(force_rollback=True):
        _mapping(connection, "team")
        assert (
            connection.execute("SELECT count(*) FROM football.provider_mapping_history").fetchone()[
                0
            ]
            == before + 1
        )
    assert (
        connection.execute("SELECT count(*) FROM football.provider_mapping_history").fetchone()[0]
        == before
    )


def test_same_native_season_is_scoped_to_the_provider_competition(connection):
    mapping = _mapping(connection, "season")
    repository = IdentityRepository(connection)
    with pytest.raises(ValueError, match="competition"):
        repository.mapping_at(
            "season",
            mapping["provider_id"],
            "native-one",
            valid_at=VALID_AT,
            knowledge_cutoff=_latest(connection, mapping),
        )
    wrong = {**mapping, "provider_competition_id": "another-competition"}
    assert _read(connection, wrong, _latest(connection, mapping)) == ()
    competition = connection.execute(
        "INSERT INTO football.competitions DEFAULT VALUES RETURNING id"
    ).fetchone()[0]
    season = connection.execute(
        "INSERT INTO football.seasons(competition_id) VALUES (%s) RETURNING id", (competition,)
    ).fetchone()[0]
    connection.execute(
        """INSERT INTO football.season_provider_mappings(
            season_id,provider_id,provider_competition_id,provider_season_id,
            first_seen_at,last_seen_at,mapping_method,mapping_confidence,source_snapshot_id)
           VALUES (%s,%s,'another-competition','native-one',%s,%s,'deterministic',1,%s)""",
        (season, mapping["provider_id"], VALID_AT, VALID_AT, mapping["source_snapshot_id"]),
    )
    cutoff = connection.execute("SELECT clock_timestamp()").fetchone()[0]
    assert _read(connection, mapping, cutoff)[0].canonical_id == mapping["canonical_id"]
    assert _read(connection, wrong, cutoff)[0].canonical_id == season


def test_future_mapping_clock_cannot_be_backdated_or_resurrect_an_older_mapping_state(connection):
    mapping = _mapping(connection, "team")
    future = connection.execute("SELECT clock_timestamp()+interval '1 day'").fetchone()[0]
    connection.execute(
        "UPDATE football.team_provider_mappings SET first_seen_at=%s,last_seen_at=%s WHERE id=%s",
        (future, future, mapping["mapping_id"]),
    )
    connection.execute(
        "UPDATE football.team_provider_mappings SET first_seen_at=%s WHERE id=%s",
        (VALID_AT, mapping["mapping_id"]),
    )
    assert _latest(connection, mapping) >= future
    assert len(_read(connection, mapping, future)) == 1
    known = _read(connection, mapping, future)[0]
    assert known.first_seen_at == VALID_AT


def test_mapping_knowledge_cannot_precede_its_source_snapshot_clock(connection):
    from datetime import timedelta

    future = connection.execute("SELECT clock_timestamp()+interval '1 day'").fetchone()[0]
    mapping = _mapping(connection, "team", source_acquired_at=future)
    assert _latest(connection, mapping) == future
    assert _read(connection, mapping, future - timedelta(microseconds=1)) == ()
    assert len(_read(connection, mapping, future)) == 1


def test_canonical_retarget_preserves_the_original_mapping_and_identity_ids_in_history(connection):
    mapping = _mapping(connection, "team")
    cutoff = _latest(connection, mapping)
    target = connection.execute(
        "INSERT INTO football.teams DEFAULT VALUES RETURNING id"
    ).fetchone()[0]
    connection.execute(
        "UPDATE football.team_provider_mappings SET team_id=%s WHERE id=%s",
        (target, mapping["mapping_id"]),
    )
    assert _read(connection, mapping, cutoff)[0].canonical_id == mapping["canonical_id"]
    current = _read(connection, mapping, _latest(connection, mapping))[0]
    assert current.canonical_id == target and current.mapping_id == mapping["mapping_id"]


def test_mapping_validity_start_is_inclusive_and_future_start_is_unavailable(connection):
    from datetime import timedelta

    mapping = _mapping(connection, "team")
    connection.execute(
        "UPDATE football.team_provider_mappings SET valid_from=%s WHERE id=%s",
        (VALID_AT, mapping["mapping_id"]),
    )
    cutoff = _latest(connection, mapping)
    repository = IdentityRepository(connection)
    assert (
        repository.mapping_at(
            "team",
            mapping["provider_id"],
            "native-one",
            valid_at=VALID_AT - timedelta(microseconds=1),
            knowledge_cutoff=cutoff,
        )
        == ()
    )
    assert len(_read(connection, mapping, cutoff)) == 1


def test_mapping_confidence_does_not_create_an_identity_admission(connection):
    mapping = _mapping(connection, "team")
    assert len(_read(connection, mapping, _latest(connection, mapping))) == 1
    assert (
        IdentityRepository(connection).admitted_identity_at(
            "team", mapping["mapping_id"], _latest(connection, mapping)
        )
        is None
    )


@pytest.mark.parametrize("subject", ["team", "competition"])
def test_identity_boundary_preserves_r2_admission_and_revocation_cutoffs(
    connection, tmp_path, subject
):
    from football.product.identity_admission import admit_provider_mappings
    from test_product_identity_admission import _cutoff, _history

    _history(connection, tmp_path)
    before = _cutoff(connection)
    admit_provider_mappings(connection, tmp_path, "football_data_uk")
    admitted = _cutoff(connection)
    mapping, canonical = connection.execute(
        "SELECT mapping_id,canonical_id FROM football.product_identity_admissions "
        "WHERE entity_type=%s AND disposition IN ('ORIGIN_ANCHOR','CROSSWALK') LIMIT 1",
        (subject,),
    ).fetchone()
    repository = IdentityRepository(connection)
    assert repository.admitted_identity_at(subject, mapping, before) is None
    assert repository.admitted_identity_at(subject, mapping, admitted) == canonical
    connection.execute(
        """INSERT INTO football.product_identity_admissions(
            entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
            disposition,reason,source_snapshot_id,source_observed_at,evidence,evidence_sha256)
           SELECT entity_type,mapping_id,canonical_id,provider_code,provider_entity_id,
                  'REVOKED','operator_revocation',source_snapshot_id,source_observed_at,
                  evidence,evidence_sha256 FROM football.product_identity_admissions
           WHERE mapping_id=%s ORDER BY decided_at DESC,decision_id DESC LIMIT 1""",
        (mapping,),
    )
    assert repository.admitted_identity_at(subject, mapping, _cutoff(connection)) is None
    assert repository.admitted_identity_at(subject, mapping, admitted) == canonical
