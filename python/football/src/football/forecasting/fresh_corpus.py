"""Outcome-blind identity reconciliation and fresh-corpus qualification."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid5

PITCHAPI_NAMESPACE = UUID("f5f4c644-05a4-4b79-b968-e765ed659da0")


class IdentityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"


class ConfidenceClass(StrEnum):
    EXACT_PROVIDER_ID = "EXACT_PROVIDER_ID"
    STRONG_MULTI_ATTRIBUTE = "STRONG_MULTI_ATTRIBUTE"
    MANUAL_VERIFIED = "MANUAL_VERIFIED"
    INSUFFICIENT = "INSUFFICIENT"


class QualificationError(RuntimeError):
    """Base error for fail-closed qualification."""


class DuplicateFixtureError(QualificationError):
    """Raised when two retained IDs describe the same real fixture."""


@dataclass(frozen=True)
class FixtureIdentity:
    fixture_id: str
    kickoff_at: datetime
    competition_id: str
    competition_name: str
    country_code: str
    season: str
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    source_provider: str
    source_fixture_id: str
    source_snapshot_id: str
    division: int | None = None


@dataclass(frozen=True)
class SourceFixture:
    provider_fixture_id: str
    canonical_provider_fixture_id: str
    kickoff_at: datetime
    competition_name: str
    country_code: str
    season: str
    home_provider_team_id: str
    away_provider_team_id: str
    home_team_name: str
    away_team_name: str
    source_snapshot_ref: str


@dataclass(frozen=True)
class ProviderTeam:
    provider_team_id: str
    provider_team_name: str
    country_code: str
    competition_name: str
    season: str


@dataclass(frozen=True)
class TeamIdentityCrosswalk:
    crosswalk_id: str
    source_provider: str
    source_team_id: str
    canonical_team_id: str
    source_team_name: str
    canonical_team_name: str
    country_code: str
    evidence_type: str
    evidence_refs: tuple[str, ...]
    confidence_class: str
    first_verified_at: str
    last_verified_at: str
    status: str
    version: int


@dataclass(frozen=True)
class ProviderMapping:
    mapping_id: str
    provider_code: str
    provider_team_id: str
    provider_team_name: str
    canonical_team_id: str
    canonical_team_name: str
    country_code: str
    source_snapshot_id: str
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_model_id: str
    artifact_sha256: str
    artifact_team_id: str
    artifact_team_name: str
    provider_team_id: str
    training_competition: str
    training_season: str
    training_cutoff: str


@dataclass(frozen=True)
class HistoryMembership:
    team_id: str
    competition_id: str
    season: str
    division: int | None
    kickoff_at: datetime


@dataclass(frozen=True)
class QualifiedTarget:
    fixture: FixtureIdentity
    home_artifact_state: str
    away_artifact_state: str
    home_history_state: str
    away_history_state: str
    home_promotion_state: str
    away_promotion_state: str
    target_category: str
    split: str = "UNASSIGNED"
    identity_crosswalk_refs: tuple[str, ...] = ()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def semantic_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def pitchapi_team_id(provider_team_id: str) -> str:
    return str(uuid5(PITCHAPI_NAMESPACE, f"pitchapi:team:{provider_team_id}"))


def pitchapi_fixture_id(provider_fixture_id: str) -> str:
    return str(uuid5(PITCHAPI_NAMESPACE, f"pitchapi:match:{provider_fixture_id}"))


def reconcile_by_fixture_participation(
    source_teams: Sequence[ProviderTeam],
    source_fixtures: Sequence[SourceFixture],
    retained_fixtures: Sequence[FixtureIdentity],
    *,
    verified_at: str,
) -> tuple[TeamIdentityCrosswalk, ...]:
    """Map teams only when full season fixture signatures identify one candidate."""
    source_signatures = _source_signatures(source_fixtures)
    retained_signatures = _retained_signatures(retained_fixtures)
    retained_names = _retained_team_names(retained_fixtures)
    retained_contexts = _retained_team_contexts(retained_fixtures)
    output: list[TeamIdentityCrosswalk] = []
    for team in sorted(source_teams, key=lambda item: item.provider_team_id):
        signature = source_signatures.get(team.provider_team_id, ())
        expected_context = (team.country_code, team.competition_name, team.season)
        candidates = [
            team_id
            for team_id, value in retained_signatures.items()
            if value == signature and retained_contexts.get(team_id) == {expected_context}
        ]
        status = IdentityStatus.UNRESOLVED
        confidence = ConfidenceClass.INSUFFICIENT
        canonical_id = ""
        canonical_name = ""
        if len(candidates) == 1 and signature:
            canonical_id = candidates[0]
            canonical_name = retained_names[canonical_id]
            status = IdentityStatus.VERIFIED
            confidence = ConfidenceClass.STRONG_MULTI_ATTRIBUTE
        elif len(candidates) > 1:
            status = IdentityStatus.AMBIGUOUS
        evidence_refs = (
            f"competition:{team.competition_name}",
            f"season:{team.season}",
            f"fixture-date-participation-sha256:{semantic_sha256(signature)}",
            f"fixture-observations:{len(signature)}",
        )
        crosswalk_seed = {
            "source_provider": "pitchapi",
            "source_team_id": team.provider_team_id,
            "canonical_team_id": canonical_id,
            "evidence_refs": evidence_refs,
            "status": status.value,
            "version": 1,
        }
        output.append(
            TeamIdentityCrosswalk(
                crosswalk_id=f"team-crosswalk:{semantic_sha256(crosswalk_seed)}",
                source_provider="pitchapi",
                source_team_id=team.provider_team_id,
                canonical_team_id=canonical_id,
                source_team_name=team.provider_team_name,
                canonical_team_name=canonical_name,
                country_code=team.country_code,
                evidence_type="SEASON_FIXTURE_PARTICIPATION",
                evidence_refs=evidence_refs,
                confidence_class=confidence.value,
                first_verified_at=verified_at,
                last_verified_at=verified_at,
                status=status.value,
                version=1,
            )
        )
    return tuple(output)


def direct_provider_crosswalk(mapping: ProviderMapping) -> TeamIdentityCrosswalk:
    evidence_refs = (
        f"football.team_provider_mappings:{mapping.mapping_id}",
        f"source_snapshot:{mapping.source_snapshot_id}",
    )
    seed = {
        "source_provider": mapping.provider_code,
        "source_team_id": mapping.provider_team_id,
        "canonical_team_id": mapping.canonical_team_id,
        "evidence_refs": evidence_refs,
        "status": IdentityStatus.VERIFIED.value,
        "version": 1,
    }
    return TeamIdentityCrosswalk(
        crosswalk_id=f"team-crosswalk:{semantic_sha256(seed)}",
        source_provider=mapping.provider_code,
        source_team_id=mapping.provider_team_id,
        canonical_team_id=mapping.canonical_team_id,
        source_team_name=mapping.provider_team_name,
        canonical_team_name=mapping.canonical_team_name,
        country_code=mapping.country_code,
        evidence_type="EXISTING_PROVIDER_MAPPING",
        evidence_refs=evidence_refs,
        confidence_class=ConfidenceClass.EXACT_PROVIDER_ID.value,
        first_verified_at=mapping.first_seen_at.astimezone(UTC).isoformat(),
        last_verified_at=mapping.last_seen_at.astimezone(UTC).isoformat(),
        status=IdentityStatus.VERIFIED.value,
        version=1,
    )


def reconcile_source_fixtures(
    source_fixtures: Sequence[SourceFixture],
    retained_fixtures: Sequence[FixtureIdentity],
    crosswalk: Sequence[TeamIdentityCrosswalk],
) -> dict[str, str]:
    team_ids = {
        row.source_team_id: row.canonical_team_id
        for row in crosswalk
        if row.status == IdentityStatus.VERIFIED and row.canonical_team_id
    }
    retained: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for retained_row in retained_fixtures:
        key = (
            retained_row.kickoff_at.date().isoformat(),
            retained_row.home_team_id,
            retained_row.away_team_id,
        )
        retained[key].append(retained_row.fixture_id)
    result: dict[str, str] = {}
    for source_row in source_fixtures:
        home_id = team_ids.get(source_row.home_provider_team_id)
        away_id = team_ids.get(source_row.away_provider_team_id)
        if home_id is None or away_id is None:
            continue
        key = (source_row.kickoff_at.date().isoformat(), home_id, away_id)
        candidates = retained.get(key, [])
        if len(candidates) == 1:
            result[source_row.canonical_provider_fixture_id] = candidates[0]
    return result


def reject_real_fixture_duplicates(
    fixtures: Iterable[FixtureIdentity],
) -> tuple[FixtureIdentity, ...]:
    by_real_fixture: dict[tuple[str, datetime, str, str], FixtureIdentity] = {}
    identity_by_id: dict[str, tuple[str, datetime, str, str]] = {}
    for row in fixtures:
        key = (row.competition_id, row.kickoff_at, row.home_team_id, row.away_team_id)
        existing_key = identity_by_id.setdefault(row.fixture_id, key)
        if existing_key != key:
            raise DuplicateFixtureError(f"fixture ID has conflicting rows: {row.fixture_id}")
        existing = by_real_fixture.get(key)
        if existing is not None and existing.fixture_id != row.fixture_id:
            raise DuplicateFixtureError(
                f"real fixture has multiple canonical IDs: {existing.fixture_id}, {row.fixture_id}"
            )
        if existing is None or _fixture_source_key(row) < _fixture_source_key(existing):
            by_real_fixture[key] = row
    return tuple(sorted(by_real_fixture.values(), key=lambda row: (row.kickoff_at, row.fixture_id)))


def apply_firewall(
    fixtures: Sequence[FixtureIdentity],
    forbidden_canonical_fixture_ids: frozenset[str],
) -> tuple[FixtureIdentity, ...]:
    return tuple(row for row in fixtures if row.fixture_id not in forbidden_canonical_fixture_ids)


def history_state(
    team_id: str,
    competition_id: str,
    kickoff_at: datetime,
    history: Mapping[str, Sequence[HistoryMembership]],
) -> str:
    rows = history.get(team_id, ())
    prior_count = bisect_left([row.kickoff_at for row in rows], kickoff_at)
    if prior_count == 0:
        return "ZERO_HISTORY"
    same_competition = sum(row.competition_id == competition_id for row in rows[:prior_count])
    if same_competition == 0:
        return "TRANSFER_HISTORY"
    if same_competition < 10:
        return "PARTIAL_HISTORY"
    return "ESTABLISHED_HISTORY"


def promotion_state(
    team_id: str,
    target_season: str,
    target_division: int | None,
    memberships: Sequence[HistoryMembership],
) -> str:
    if target_division is None:
        return "PROMOTION_STATUS_UNKNOWN"
    previous = _previous_season(target_season)
    prior_divisions = {
        row.division
        for row in memberships
        if row.team_id == team_id and row.season == previous and row.division is not None
    }
    if len(prior_divisions) != 1:
        return "PROMOTION_STATUS_UNKNOWN"
    prior_division = next(iter(prior_divisions))
    return "PROMOTED_TEAM" if prior_division > target_division else "NOT_PROMOTED"


def classify_targets(
    fixtures: Sequence[FixtureIdentity],
    artifact_team_ids: frozenset[str],
    history: Mapping[str, Sequence[HistoryMembership]],
    crosswalk_refs: Mapping[tuple[str, str], str],
) -> tuple[QualifiedTarget, ...]:
    output: list[QualifiedTarget] = []
    for row in fixtures:
        home_fitted = row.home_team_id in artifact_team_ids
        away_fitted = row.away_team_id in artifact_team_ids
        category = _target_category(home_fitted, away_fitted)
        refs = tuple(
            crosswalk_refs[key]
            for key in (
                (row.source_provider, row.home_team_id),
                (row.source_provider, row.away_team_id),
            )
            if key in crosswalk_refs
        )
        output.append(
            QualifiedTarget(
                fixture=row,
                home_artifact_state="FITTED" if home_fitted else "UNSEEN_TEAM",
                away_artifact_state="FITTED" if away_fitted else "UNSEEN_TEAM",
                home_history_state=history_state(
                    row.home_team_id, row.competition_id, row.kickoff_at, history
                ),
                away_history_state=history_state(
                    row.away_team_id, row.competition_id, row.kickoff_at, history
                ),
                home_promotion_state=promotion_state(
                    row.home_team_id,
                    row.season,
                    row.division,
                    history.get(row.home_team_id, ()),
                ),
                away_promotion_state=promotion_state(
                    row.away_team_id,
                    row.season,
                    row.division,
                    history.get(row.away_team_id, ()),
                ),
                target_category=category,
                identity_crosswalk_refs=refs,
            )
        )
    return tuple(output)


def chronological_split(targets: Sequence[QualifiedTarget]) -> tuple[QualifiedTarget, ...]:
    ordered = sorted(targets, key=lambda row: (row.fixture.kickoff_at, row.fixture.fixture_id))
    batches: list[list[QualifiedTarget]] = []
    for row in ordered:
        if not batches or batches[-1][0].fixture.kickoff_at != row.fixture.kickoff_at:
            batches.append([])
        batches[-1].append(row)
    total = len(ordered)
    train_floor = total * 0.60
    validation_floor = total * 0.80
    cumulative = 0
    output: list[QualifiedTarget] = []
    for batch in batches:
        cumulative += len(batch)
        split = "TRAIN"
        if cumulative > train_floor:
            split = "VALIDATION"
        if cumulative > validation_floor:
            split = "DEVELOPMENT_HOLDOUT"
        output.extend(replace(row, split=split) for row in batch)
    return tuple(output)


def target_manifest_row(target: QualifiedTarget) -> dict[str, object]:
    row = target.fixture
    return {
        "fixture_id": row.fixture_id,
        "kickoff_at": row.kickoff_at.astimezone(UTC).isoformat(),
        "competition_id": row.competition_id,
        "competition_name": row.competition_name,
        "country_code": row.country_code,
        "season": row.season,
        "division": row.division,
        "home_team_id": row.home_team_id,
        "away_team_id": row.away_team_id,
        "home_artifact_state": target.home_artifact_state,
        "away_artifact_state": target.away_artifact_state,
        "home_history_state": target.home_history_state,
        "away_history_state": target.away_history_state,
        "home_promotion_state": target.home_promotion_state,
        "away_promotion_state": target.away_promotion_state,
        "target_category": target.target_category,
        "split": target.split,
        "source_provider": row.source_provider,
        "source_fixture_id": row.source_fixture_id,
        "source_snapshot": row.source_snapshot_id,
        "identity_crosswalk_refs": list(target.identity_crosswalk_refs),
    }


def crosswalk_manifest_row(row: TeamIdentityCrosswalk) -> dict[str, object]:
    value = asdict(row)
    value["evidence_refs"] = list(row.evidence_refs)
    return value


def _source_signatures(
    fixtures: Sequence[SourceFixture],
) -> dict[str, tuple[tuple[str, str], ...]]:
    values: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in fixtures:
        stamp = row.kickoff_at.astimezone(UTC).date().isoformat()
        values[row.home_provider_team_id].append((stamp, "HOME"))
        values[row.away_provider_team_id].append((stamp, "AWAY"))
    return {key: tuple(sorted(rows)) for key, rows in values.items()}


def _retained_signatures(
    fixtures: Sequence[FixtureIdentity],
) -> dict[str, tuple[tuple[str, str], ...]]:
    values: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in fixtures:
        stamp = row.kickoff_at.astimezone(UTC).date().isoformat()
        values[row.home_team_id].append((stamp, "HOME"))
        values[row.away_team_id].append((stamp, "AWAY"))
    return {key: tuple(sorted(rows)) for key, rows in values.items()}


def _retained_team_names(fixtures: Sequence[FixtureIdentity]) -> dict[str, str]:
    names: dict[str, str] = {}
    for row in fixtures:
        names[row.home_team_id] = row.home_team_name
        names[row.away_team_id] = row.away_team_name
    return names


def _retained_team_contexts(
    fixtures: Sequence[FixtureIdentity],
) -> dict[str, set[tuple[str, str, str]]]:
    contexts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    for row in fixtures:
        context = (row.country_code, row.competition_name, row.season)
        contexts[row.home_team_id].add(context)
        contexts[row.away_team_id].add(context)
    return contexts


def _target_category(home_fitted: bool, away_fitted: bool) -> str:
    if home_fitted and away_fitted:
        return "NATIVE_FITTED"
    if not home_fitted and not away_fitted:
        return "COLD_START_BOTH"
    return "COLD_START_AWAY" if home_fitted else "COLD_START_HOME"


def _fixture_source_key(row: FixtureIdentity) -> tuple[str, str, str]:
    return row.source_provider, row.source_fixture_id, row.source_snapshot_id


def _previous_season(value: str) -> str:
    parts = value.split("/")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return ""
    start = int(parts[0]) - 1
    return f"{start}/{start + 1}"
