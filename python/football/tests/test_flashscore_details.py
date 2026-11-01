from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from football.contracts.observations import ObservationProvenance, ObservationTime
from football.providers.normalization.common import NormalizationContext, NormalizationResult
from football.providers.normalization.pipeline import normalize_resource


def normalize(resource: str, feed: str, *, key: str | None = None) -> NormalizationResult:
    raw = feed.encode()
    uid = UUID(int=1)
    now = datetime(2026, 11, 1, tzinfo=UTC)
    prefix = {"events": "sui", "lineups": "li", "summary": "sur"}[resource]
    context = NormalizationContext(
        provenance=ObservationProvenance(
            "flashscore", None, uid, uid, hashlib.sha256(raw).hexdigest()
        ),
        time=ObservationTime(observed_at=now, acquired_at=now, known_at=now),
        resource_key=key if key is not None else f"df_{prefix}_1_match001",
        fixture_native_id="match001",
    )
    result = normalize_resource(context, resource, raw)
    assert result == normalize_resource(context, resource, raw)
    return result


def test_event_roles_and_own_goal_team_are_not_guessed() -> None:
    result = normalize(
        "events",
        "AC÷2nd Half¬~III÷goal001¬IA÷2¬IB÷64'¬IE÷4¬IM÷player01¬~"
        "III÷sub0001¬IA÷1¬IB÷66'¬IE÷6¬IM÷leaving1¬IE÷7¬IM÷coming01¬~",
    )
    rows = [o.to_dict() for o in result.observations if o.CONTRACT == "EventObservationV2"]
    assert len(rows) == 2 and rows[0]["own_goal"] is True and rows[0]["team"] is None
    actor = rows[1]["player"]
    assert isinstance(actor, dict) and actor["provider_native_id"] == "leaving1"
    assert all(o.time.event_time is None for o in result.observations)


def test_missed_penalty_and_shootout_do_not_become_ordinary_goals() -> None:
    result = normalize(
        "events",
        "AC÷1st Half¬~III÷miss001¬IA÷1¬IB÷16'¬IE÷5¬IM÷player01¬IE÷11¬IM÷player01¬~"
        "AC÷Penalties¬~III÷shoot01¬IA÷1¬IB÷90'¬IE÷10¬IM÷player01¬~",
    )
    assert not any(o.CONTRACT == "EventObservationV2" for o in result.observations)
    assert any(f.rule_code == "MF_NORM_EVENT_ACTOR_TYPE_UNSUPPORTED" for f in result.findings)
    assert any(f.rule_code == "MF_NORM_PERIOD_UNSUPPORTED" for f in result.findings)


def test_lineup_roles_preserve_uncertainty_and_coaches_are_not_players() -> None:
    result = normalize(
        "lineups",
        "LB÷Starting Lineups¬LGT÷1¬LGK÷1¬LC÷1¬~LP÷start001¬LI÷Starter¬LG÷1¬LD÷1-4-3-3¬~"
        "LB÷Substitutes¬LGT÷1¬LGK÷2¬LC÷1¬~LP÷bench001¬LI÷Bench¬LG÷1¬~"
        "LB÷Coaches¬LGT÷4¬LC÷1¬~LP÷coach001¬LI÷Coach¬LG÷2¬~",
    )
    assert sum(o.CONTRACT == "PlayerObservationV2" for o in result.observations) == 2
    assert sum(o.CONTRACT == "CoachObservationV2" for o in result.observations) == 1
    row = next(o.to_dict() for o in result.observations if o.CONTRACT == "LineupObservationV2")
    assert row["lineup_mode"] == "UNKNOWN" and row["formation"] == "1-4-3-3"
    assert not any(
        o.CONTRACT in ("FormationObservationV2", "PlayerStatisticObservationV2")
        for o in result.observations
    )


def test_reported_period_scores_and_referee_keep_unknown_basis_and_identity() -> None:
    result = normalize(
        "summary", "AC÷3¬BA÷1¬BB÷0¬~BC÷0¬BD÷1¬~MIT÷REF¬MIV÷Referee Name¬MIT÷VEN¬MIV÷Venue Name¬~"
    )
    rows = [o.to_dict() for o in result.observations if o.CONTRACT == "PeriodScoreObservationV3"]
    assert (
        len(rows) == 2 and rows[0]["period"] == "FIRST_HALF" and rows[1]["period"] == "SECOND_HALF"
    )
    assert all(row["score_basis"] == "UNKNOWN" for row in rows)
    referee = next(o.to_dict() for o in result.observations if o.CONTRACT == "RefereeObservationV3")
    ref = referee["referee"]
    assert isinstance(ref, dict) and ref["provider_native_id"] is None


@pytest.mark.parametrize(
    "feed",
    [
        "AC÷1st Half¬~III÷event001¬IA÷1¬IB÷45+4'¬ID÷3¬IE÷1¬IM÷player01¬~",
        "AC÷1st Half¬~III÷event001¬IA÷1¬IB÷future-format¬IE÷1¬IM÷player01¬~",
        "AC÷1st Half¬~III÷event001¬IA÷1¬IB÷30'¬IE÷1¬IM÷player01¬IM÷other001¬~",
    ],
)
def test_invalid_event_clock_or_actor_identity_is_held(feed: str) -> None:
    result = normalize("events", feed)
    assert any(f.severity == "QUARANTINE" for f in result.findings)
    assert not any(o.CONTRACT == "EventObservationV2" for o in result.observations)


def test_explicit_added_time_and_goal_actor_do_not_select_assistant() -> None:
    result = normalize(
        "events", "AC÷1st Half¬~III÷event001¬IA÷1¬IB÷45+4'¬ID÷4¬IE÷3¬IM÷scorer01¬IE÷8¬IM÷assist01¬~"
    )
    event = next(o.to_dict() for o in result.observations if o.CONTRACT == "EventObservationV2")
    actor = event["player"]
    assert isinstance(actor, dict) and actor["provider_native_id"] == "scorer01"
    assert event["minute"] == 45 and event["added_time"] == 4


def test_duplicate_lineup_player_does_not_create_two_members() -> None:
    result = normalize(
        "lineups",
        "LB÷Starting Lineups¬LGT÷1¬LGK÷1¬LC÷1¬~LP÷player01¬LI÷Player¬LG÷1¬~"
        "LB÷Substitutes¬LGT÷1¬LGK÷2¬LC÷1¬~LP÷player01¬LI÷Player¬LG÷1¬~",
    )
    assert any(f.severity == "QUARANTINE" for f in result.findings)


@pytest.mark.parametrize("label,valid", [("Goalkeeper", True), ("Other", False)])
def test_observed_goalkeeper_type_requires_its_explicit_source_label(
    label: str, valid: bool
) -> None:
    result = normalize(
        "lineups", f"LB÷Starting Lineups¬LGT÷1¬LGK÷1¬LC÷1¬~LP÷keeper01¬LI÷Keeper¬LG÷3¬LS÷{label}¬~"
    )
    assert any(o.CONTRACT == "PlayerObservationV2" for o in result.observations) == valid
    assert any(f.severity == "QUARANTINE" for f in result.findings) != valid


@pytest.mark.parametrize("feed", ["AC÷3¬BA÷1¬~", "AC÷1¬BA÷1¬BB÷0¬~", "AC÷3¬BA÷1¬BB÷0¬BA÷2¬~"])
def test_incomplete_conflicting_or_unfinished_period_counts_are_held(feed: str) -> None:
    result = normalize("summary", feed)
    assert any(f.severity == "QUARANTINE" for f in result.findings)
    assert not any(o.CONTRACT == "PeriodScoreObservationV3" for o in result.observations)


@pytest.mark.parametrize(
    "resource,key,feed",
    [
        ("events", "df_li_1_match001", "AC÷1st Half¬~III÷event001¬IA÷1¬IB÷30'¬IE÷3¬IM÷player01¬~"),
        (
            "lineups",
            "df_sui_1_match001",
            "LB÷Starting Lineups¬LGT÷1¬LGK÷1¬LC÷1¬~LP÷player01¬LI÷Player¬LG÷1¬~",
        ),
        ("summary", "df_st_1_match001", "AC÷3¬BA÷1¬BB÷0¬~"),
    ],
)
def test_registered_feed_family_must_agree_with_resource(
    resource: str, key: str, feed: str
) -> None:
    result = normalize(resource, feed, key=key)
    assert not result.observations
    assert any(f.rule_code == "MF_NORM_RESOURCE_INVALID" for f in result.findings)
