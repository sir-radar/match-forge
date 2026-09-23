from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid5

from football.forecasting.dataset import (
    ForecastMatchContextV1,
    WalkForwardDatasetSpecV1,
    build_walk_forward_target_plan,
)
from football.validation.pitchapi_contingency import (
    CorpusRole,
    EvaluationV2CorpusGroupV1,
    GateStatus,
    PitchApiSourceSeriesEvidenceV1,
    qualify_pitchapi_source_series,
    validate_evaluation_v2_corpus_firewall,
)

NAMESPACE = UUID("bbfaedc2-cbf4-4f0a-8733-f8b7d0e0b693")


def _ids(scope: str, count: int) -> tuple[UUID, ...]:
    return tuple(uuid5(NAMESPACE, f"{scope}:{index}") for index in range(count))


def _round_robin_contexts(
    scope: str, team_count: int
) -> tuple[UUID, UUID, tuple[ForecastMatchContextV1, ...]]:
    competition_id = uuid5(NAMESPACE, f"competition:{scope}")
    season_id = uuid5(NAMESPACE, f"season:{scope}")
    teams = [uuid5(NAMESPACE, f"team:{scope}:{index}") for index in range(team_count)]
    rotation = list(teams)
    first_leg: list[tuple[UUID, UUID]] = []
    contexts: list[ForecastMatchContextV1] = []
    kickoff = datetime(2023, 8, 1, 15, tzinfo=UTC)
    for round_index in range(team_count - 1):
        round_pairs = [(rotation[index], rotation[-index - 1]) for index in range(team_count // 2)]
        first_leg.extend(round_pairs)
        for pair_index, (home, away) in enumerate(round_pairs):
            contexts.append(
                ForecastMatchContextV1(
                    match_id=uuid5(NAMESPACE, f"match:{scope}:1:{round_index}:{pair_index}"),
                    competition_id=competition_id,
                    season_id=season_id,
                    kickoff_at=kickoff + timedelta(days=7 * round_index),
                    home_team_id=home,
                    away_team_id=away,
                )
            )
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    for round_index in range(team_count - 1):
        for pair_index in range(team_count // 2):
            home, away = first_leg[round_index * (team_count // 2) + pair_index]
            contexts.append(
                ForecastMatchContextV1(
                    match_id=uuid5(NAMESPACE, f"match:{scope}:2:{round_index}:{pair_index}"),
                    competition_id=competition_id,
                    season_id=season_id,
                    kickoff_at=kickoff + timedelta(days=7 * (team_count - 1 + round_index)),
                    home_team_id=away,
                    away_team_id=home,
                )
            )
    return competition_id, season_id, tuple(contexts)


def _target_count(scope: str, team_count: int, minimum_competition_history: int) -> int:
    competition_id, season_id, contexts = _round_robin_contexts(scope, team_count)
    spec = WalkForwardDatasetSpecV1(
        dataset_version_id=uuid5(NAMESPACE, f"dataset:{scope}"),
        source_snapshot_id=uuid5(NAMESPACE, f"source:{scope}"),
        feature_set_version="synthetic-pitchapi-contingency-v1",
        knowledge_cutoff=datetime(2026, 9, 23, tzinfo=UTC),
        knowledge_mode="retrospective-fixed-snapshot-v1",
        quality_policy_sha256="0" * 64,
        minimum_team_history=10,
        minimum_competition_history=minimum_competition_history,
    )
    return build_walk_forward_target_plan(spec, competition_id, season_id, contexts).target_count


def _series(scope: str, **changes: object) -> PitchApiSourceSeriesEvidenceV1:
    values: dict[str, object] = {
        "scope_key": scope,
        "upstream_supplier": "supplier",
        "model_name": "model",
        "model_version": "v1",
        "model_build": "build-2026-01",
        "field_semantics": "pre-shot probability; unit interval",
        "penalty_treatment": "provider model value retained",
        "export_cohort_id": "cohort-1",
        "rebuild_backfill_policy_ref": "evidence/rebuild-v1",
        "correction_policy_ref": "evidence/corrections-v1",
        "identifier_policy_ref": "evidence/identifiers-v1",
        "knowledge_mode_compatibility_ref": "evidence/retrospective-v1",
        "attestation_ref": "evidence/provider-letter-v1",
        "attestation_sha256": "a" * 64,
        "snapshot_revision": f"snapshot-{scope}",
        "snapshot_sha256": "b" * 64,
        "acquired_at": datetime(2026, 9, 23, tzinfo=UTC),
        "prior_versions_retainable": True,
    }
    values.update(changes)
    return PitchApiSourceSeriesEvidenceV1(**values)  # type: ignore[arg-type]


def _group(
    scope: str,
    role: str,
    competition: str,
    season: str,
    matches: int,
    targets: int,
    *,
    series: str = "c" * 64,
    point_in_time_status: str = "PASS",
) -> EvaluationV2CorpusGroupV1:
    match_ids = _ids(scope, matches)
    return EvaluationV2CorpusGroupV1(
        scope_key=scope,
        role=cast(CorpusRole, role),
        competition_ref=competition,
        season_ref=season,
        source_snapshot_id=uuid5(NAMESPACE, f"snapshot:{scope}"),
        source_snapshot_sha256="d" * 64,
        source_series_sha256=series,
        target_plan_sha256="e" * 64,
        cutoff_evidence_sha256="f" * 64,
        match_ids=match_ids,
        target_ids=match_ids[-targets:],
        point_in_time_status=cast(GateStatus, point_in_time_status),
    )


def _passing_groups() -> tuple[EvaluationV2CorpusGroupV1, ...]:
    return (
        _group("development", "development", "development-league", "2021/2022", 306, 198),
        _group("bundesliga", "evaluation", "bundesliga", "2023/2024", 306, 198),
        _group("ligue1-a", "evaluation", "ligue1", "2022/2023", 380, 280),
        _group("ligue1-b", "evaluation", "ligue1", "2021/2022", 380, 280),
    )


def test_source_series_requires_attested_fields_not_equal_free_form_labels() -> None:
    incomplete = (_series("bundesliga", upstream_supplier=None), _series("ligue1"))

    report = qualify_pitchapi_source_series(incomplete, ("bundesliga", "ligue1"))

    assert report.status == "UNPROVED"
    assert "MISSING_UPSTREAM_SUPPLIER:bundesliga" in report.findings
    assert report.series_identity_sha256 is None

    blank = qualify_pitchapi_source_series(
        (_series("bundesliga", model_name="  "), _series("ligue1")),
        ("bundesliga", "ligue1"),
    )
    assert "MISSING_MODEL_NAME:bundesliga" in blank.findings


def test_source_series_rejects_model_or_rebuild_mismatch() -> None:
    report = qualify_pitchapi_source_series(
        (_series("bundesliga"), _series("ligue1", model_build="build-2026-02")),
        ("bundesliga", "ligue1"),
    )

    assert report.status == "FAIL"
    assert report.findings == ("MIXED_XG_SERIES",)


def test_source_series_hash_is_scope_and_snapshot_order_independent() -> None:
    first = qualify_pitchapi_source_series(
        (_series("bundesliga"), _series("ligue1")),
        ("bundesliga", "ligue1"),
    )
    second = qualify_pitchapi_source_series(
        (
            _series("ligue1", snapshot_sha256="9" * 64),
            _series("bundesliga", snapshot_sha256="8" * 64),
        ),
        ("ligue1", "bundesliga"),
    )

    assert first.status == second.status == "PASS"
    assert first.series_identity_sha256 == second.series_identity_sha256
    assert first.to_dict()["contract"] == "PitchApiSeriesGateReportV1"


def test_corpus_firewall_passes_only_complete_independent_same_series_scope() -> None:
    report = validate_evaluation_v2_corpus_firewall(
        _passing_groups(),
        protected_match_ids=frozenset(_ids("protected-epl", 380)),
        protected_scope_refs=frozenset({("premier-league", "2015/2016")}),
    )

    assert report.status == "PASS"
    assert report.evaluation_group_count == 3
    assert report.evaluation_competition_count == 2
    assert report.evaluation_season_count == 3
    assert report.evaluation_target_count == 758
    assert report.findings == ()
    assert report.to_dict()["corpus_sha256"] == report.corpus_sha256
    assert report.to_dict()["firewall_sha256"] == report.firewall_sha256


def test_corpus_firewall_rejects_role_series_fixture_and_protected_intersections() -> None:
    groups = list(_passing_groups())
    shared = groups[1].match_ids[0]
    groups[2] = replace(
        groups[2],
        source_series_sha256="1" * 64,
        match_ids=(shared, *groups[2].match_ids[1:]),
        target_ids=(shared, *groups[2].target_ids[1:]),
    )

    report = validate_evaluation_v2_corpus_firewall(
        tuple(groups),
        protected_match_ids=frozenset({shared}),
        protected_scope_refs=frozenset({("ligue1", "2021/2022")}),
    )

    assert report.status == "FAIL"
    assert {
        "CROSS_GROUP_MATCH_ID_INTERSECTION",
        "PROTECTED_MATCH_ID_INTERSECTION",
        "PROTECTED_SCOPE_INCLUDED",
        "SOURCE_SERIES_INTERSECTION_FAILED",
    } <= set(report.findings)


def test_corpus_firewall_blocks_unproved_point_in_time_evidence() -> None:
    groups = list(_passing_groups())
    source = groups[1]
    groups[1] = EvaluationV2CorpusGroupV1(
        scope_key=source.scope_key,
        role=source.role,
        competition_ref=source.competition_ref,
        season_ref=source.season_ref,
        source_snapshot_id=source.source_snapshot_id,
        source_snapshot_sha256=source.source_snapshot_sha256,
        source_series_sha256=source.source_series_sha256,
        target_plan_sha256=source.target_plan_sha256,
        cutoff_evidence_sha256=source.cutoff_evidence_sha256,
        match_ids=source.match_ids,
        target_ids=source.target_ids,
        point_in_time_status="UNPROVED",
    )

    report = validate_evaluation_v2_corpus_firewall(
        tuple(groups), protected_match_ids=frozenset(), protected_scope_refs=frozenset()
    )

    assert report.status == "UNPROVED"
    assert "POINT_IN_TIME_UNPROVED:bundesliga" in report.findings


def test_corpus_firewall_rejects_development_competition_reuse_and_low_targets() -> None:
    groups = list(_passing_groups())
    groups[0] = replace(groups[0], competition_ref="bundesliga")
    groups[3] = replace(groups[3], target_ids=groups[3].target_ids[:1])

    report = validate_evaluation_v2_corpus_firewall(
        tuple(groups), protected_match_ids=frozenset(), protected_scope_refs=frozenset()
    )

    assert report.status == "FAIL"
    assert "DEVELOPMENT_EVALUATION_COMPETITION_INTERSECTION" in report.findings
    assert "EVALUATION_TARGET_COUNT_BELOW_MINIMUM" in report.findings


def test_corpus_hash_is_order_independent_and_binds_roles_and_membership() -> None:
    groups = _passing_groups()
    first = validate_evaluation_v2_corpus_firewall(
        groups, protected_match_ids=frozenset(), protected_scope_refs=frozenset()
    )
    reordered = validate_evaluation_v2_corpus_firewall(
        tuple(reversed(groups)), protected_match_ids=frozenset(), protected_scope_refs=frozenset()
    )

    assert first.corpus_sha256 == reordered.corpus_sha256
    assert first.firewall_sha256 == reordered.firewall_sha256

    different_protected_manifest = validate_evaluation_v2_corpus_firewall(
        groups,
        protected_match_ids=frozenset({uuid5(NAMESPACE, "another-protected-match")}),
        protected_scope_refs=frozenset(),
    )
    assert first.corpus_sha256 == different_protected_manifest.corpus_sha256
    assert first.firewall_sha256 != different_protected_manifest.firewall_sha256


def test_one_immutable_export_snapshot_may_cover_multiple_groups() -> None:
    groups = _passing_groups()
    shared_snapshot = groups[0].source_snapshot_id
    shared = tuple(replace(group, source_snapshot_id=shared_snapshot) for group in groups)

    report = validate_evaluation_v2_corpus_firewall(
        shared, protected_match_ids=frozenset(), protected_scope_refs=frozenset()
    )

    assert report.status == "PASS"


def test_pitchapi_provisional_target_counts_expose_competition_history_ambiguity() -> None:
    assert _target_count("bundesliga", 18, 1) == 216
    assert _target_count("ligue1", 20, 1) == 280
    assert _target_count("bundesliga", 18, 100) == 198
    assert _target_count("ligue1", 20, 100) == 280
