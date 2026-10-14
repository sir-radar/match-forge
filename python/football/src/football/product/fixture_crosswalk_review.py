"""Propose crosswalks from verified fixture correspondence; never admit candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from football.product.domain import normalize_team_name


def correspondence_blocker(pair: dict[str, Any]) -> str | None:
    """Names locate candidates; independent fixture context establishes correspondence."""
    if not pair["source_verified"] or not pair["target_verified"]:
        return "RETAINED_SOURCE_EVIDENCE_REQUIRED"
    if not pair["target_admitted"]:
        return "TARGET_IDENTITY_NOT_ADMITTED"
    comparisons = (
        ("country", "COMPETITION_COUNTRY_CONFLICT"),
        ("season", "SEASON_CONFLICT"),
        ("gender", "GENDER_CONFLICT"),
        ("division", "DIVISION_CONFLICT"),
        ("team_variant", "TEAM_VARIANT_CONFLICT"),
    )
    for field, reason in comparisons:
        source, target = pair["source"].get(field), pair["target"].get(field)
        if source is not None and target is not None and source != target:
            return reason
    if any(
        pair[scope].get(field) is None
        for scope in ("source", "target")
        for field in ("country", "season", "kickoff")
    ):
        return "COMPLETE_FIXTURE_CONTEXT_REQUIRED"
    if not _matching_kickoff(pair):
        return "KICKOFF_CONFLICT"
    for side in ("home", "away"):
        if candidate_name(pair["source"][side + "_name"]) != candidate_name(
            pair["target"][side + "_name"]
        ):
            return "HOME_AWAY_OR_OPPONENT_CONFLICT"
    if (
        pair["source"].get("finished")
        and pair["target"].get("finished")
        and pair["source"].get("score") != pair["target"].get("score")
    ):
        return "RESULT_CONFLICT"
    return None


def candidate_name(name: str) -> str:
    """Ignore club designators only for locating independently verified fixture candidates."""
    return " ".join(
        token
        for token in normalize_team_name(name).split()
        if token not in {"sd", "rc", "cd", "ud", "de", "del", "du", "di", "futbol"}
    )


def _matching_kickoff(pair: dict[str, Any]) -> bool:
    source, target = pair["source"], pair["target"]
    if source["kickoff"] == target["kickoff"]:
        return True
    if (
        target.get("kickoff_precision") != "DATE_ONLY"
        or not source.get("finished")
        or not target.get("finished")
        or source.get("score") != target.get("score")
    ):
        return False
    left = datetime.fromisoformat(source["kickoff"])
    right = datetime.fromisoformat(target["kickoff"])
    return (
        left.tzinfo is not None
        and right.tzinfo is not None
        and (left.astimezone(UTC).date() == right.astimezone(UTC).date())
    )


def review_competition(metadata: dict[str, Any], pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """A unique exact fixture correspondence can support an explicit operator review."""
    result = {
        **metadata,
        "classification": "INSUFFICIENT_EVIDENCE",
        "confidence": "LOW",
        "blocker": "NO_INDEPENDENT_RETAINED_FIXTURE_CORRESPONDENCE",
        "evidence": list(pairs),
    }
    if str(metadata["requested_id"]) != str(metadata["fotmob_competition_id"]):
        result.update(classification="WRONG_PROVIDER_REGISTRATION", blocker="PROVIDER_ID_MISMATCH")
        return result
    if not pairs:
        return result
    blockers = {reason for pair in pairs if (reason := correspondence_blocker(pair))}
    if blockers:
        result.update(classification="CONTRADICTORY", blocker=";".join(sorted(blockers)))
        return result
    targets = {pair["target"]["competition_id"] for pair in pairs}
    if len(targets) != 1:
        result.update(classification="AMBIGUOUS", blocker="MULTIPLE_CANONICAL_COMPETITIONS")
        return result
    result.update(
        canonical_candidate_id=next(iter(targets)),
        classification="QUALIFIED_EXPLICIT_CROSSWALK",
        confidence="HIGH",
        blocker=None,
        fixture_overlap={"exact_retained_correspondences": len(pairs)},
    )
    return result


def review_teams(
    pairs: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep every native provider ID and hold conflicting proposed equivalences."""
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for pair in pairs:
        for side in ("home", "away"):
            groups[str(pair["source"][side + "_id"])].append((side, pair))
    results = []
    for identifier, witnesses in sorted(groups.items()):
        targets = {pair["target"][side + "_id"] for side, pair in witnesses}
        blockers = {reason for _, pair in witnesses if (reason := correspondence_blocker(pair))}
        results.append(
            {
                "fotmob_team_id": identifier,
                "provider_names": sorted(
                    {pair["source"][side + "_name"] for side, pair in witnesses}
                ),
                "canonical_candidates": sorted(targets),
                "classification": "QUALIFIED_EXPLICIT_CROSSWALK"
                if len(targets) == 1 and not blockers
                else "CONTRADICTORY",
                "blocker": ";".join(sorted(blockers))
                if blockers
                else "MULTIPLE_CANONICAL_TEAMS"
                if len(targets) != 1
                else None,
                "fixture_evidence": [pair for _, pair in witnesses],
            }
        )
    return results
