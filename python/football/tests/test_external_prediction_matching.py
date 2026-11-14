from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid5

import pytest
from football.product.external_match_context import (
    competition_context,
    competition_relation,
    country_key,
    match_name,
    name_form,
)
from football.product.external_prediction_matching import (
    CandidateFixture,
    SourcePrediction,
    date_relation,
    decide,
)

COUNTRIES = frozenset(
    country_key(name)
    for name in ("England", "Spain", "Germany", "Wales", "World", "Czech-Republic", "Turkey")
)
DAY = date(2026, 10, 17)


def source(home: str = "Everton", away: str = "Chelsea", **changes: object) -> SourcePrediction:
    values: dict[str, object] = {
        "source_code": "matchoutlook",
        "prediction_date": DAY,
        "competition": "England Premier League",
        "home_team": home,
        "away_team": away,
    }
    values.update(changes)
    return SourcePrediction(**values)  # type: ignore[arg-type]


def fixture(
    home: str = "Everton",
    away: str = "Chelsea",
    *,
    kickoff: datetime = datetime(2026, 10, 17, 14, tzinfo=UTC),
    competition: str = "Premier League",
    country: str = "England",
    kind: str = "LEAGUE",
    division: int | None = 1,
    key: str | None = None,
    effective: str | None = None,
    resolution: str | None = None,
    identity: str = "VERIFIED",
    earlier: tuple[datetime, ...] = (),
) -> CandidateFixture:
    fixture_id = uuid5(UUID(int=0), key or f"{home}-{away}-{kickoff}-{competition}")
    return CandidateFixture(
        fixture_id=fixture_id,
        kickoff_at=kickoff,
        home_names=(home,),
        away_names=(away,),
        competition_name=competition,
        competition_country=country,
        competition_type=kind,
        division=division,
        identity_status=identity,
        effective_fixture_id=uuid5(UUID(int=0), effective) if effective else fixture_id,
        resolution_status=resolution,
        earlier_kickoffs=earlier,
    )


def test_unique_fixture_matches_without_native_id() -> None:
    target = fixture()
    decision = decide(source(), [target, fixture("Arsenal", "Leeds")], COUNTRIES)
    assert (decision.classification, decision.reason) == ("CONTEXTUAL_MATCH", "UNIQUE_SAME_DAY")
    assert decision.fixture_id == target.fixture_id
    evidence = decision.evidence(source())
    assert evidence["policy_version"] == "EXTERNAL_PREDICTION_CONTEXTUAL_MATCHING_V1"
    assert evidence["candidates"][0]["home_rule"] == "EXACT"


@pytest.mark.parametrize(
    ("printed", "catalogue", "rule"),
    [
        ("Atl. Madrid", "Atletico Madrid", "VARIANT"),
        ("Sheffield Wednesd..", "Sheffield Wednesday", "VARIANT"),
        ("Ipswich", "Ipswich Town", "VARIANT"),
        ("1. FC Köln", "FC Koln", "EXACT"),
        ("AEK Athens", "AEK Athens FC", "EXACT"),
        ("Czechia", "Czech Republic", "EXACT"),
        ("Türkiye", "Turkey", "EXACT"),
        ("Man Utd", "Man United", "EXACT"),
        ("Inter", "Internazionale", "EXACT"),
        ("Madrid", "Atletico Madrid", None),
        ("Real Madrid", "Atletico Madrid", None),
        ("Dinamo B.", "Dinamo Zagreb", None),
    ],
)
def test_team_name_variants(printed: str, catalogue: str, rule: str | None) -> None:
    assert match_name(name_form(printed), name_form(catalogue)) == rule


@pytest.mark.parametrize(
    ("printed", "catalogue"),
    [
        ("Torreense W", "Torreense"),
        ("Arsenal", "Arsenal Women"),
        ("Ukraine U19", "Ukraine"),
        ("Israel Under -19", "Israel U21"),
        ("Barcelona B", "Barcelona"),
        ("Jong Ajax", "Ajax"),
        ("Sunderland U21", "Sunderland"),
    ],
)
def test_women_youth_and_reserve_sides_never_match_another_side(
    printed: str, catalogue: str
) -> None:
    assert match_name(name_form(printed), name_form(catalogue)) is None


def test_age_marker_spellings_agree() -> None:
    assert match_name(name_form("Israel Under -19"), name_form("Israel U19")) == "EXACT"
    assert match_name(name_form("Torreense W"), name_form("Torreense Women")) == "EXACT"


def test_same_name_in_another_country_is_a_competition_conflict() -> None:
    english = fixture("Rangers", "Celtic", competition="Premiership", country="Scotland")
    decision = decide(
        source("Rangers", "Celtic", competition="England Premier League"), [english], COUNTRIES
    )
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "COMPETITION_MISMATCH")


def test_cup_and_league_games_between_the_same_teams_are_separated() -> None:
    league = fixture(competition="Premier League", kind="LEAGUE")
    cup = fixture(
        competition="EFL Cup",
        kind="CUP",
        kickoff=datetime(2026, 10, 17, 19, tzinfo=UTC),
        division=None,
    )
    decision = decide(source(competition="England EFL Cup"), [league, cup], COUNTRIES)
    # The league fixture conflicts with the cup label; the remaining twin still needs review.
    assert decision.classification == "NEEDS_REVIEW"
    assert decision.reason == "MULTIPLE_CANDIDATES"


def test_reversed_orientation_needs_review() -> None:
    decision = decide(source("Chelsea", "Everton"), [fixture()], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "HOME_AWAY_REVERSED")


def test_publication_date_and_midnight_kickoffs() -> None:
    late = fixture(kickoff=datetime(2026, 10, 18, 1, 30, tzinfo=UTC))
    assert date_relation(source(), late) == "MIDNIGHT_ADJACENT"
    next_day = fixture(kickoff=datetime(2026, 10, 18, 15, tzinfo=UTC))
    decision = decide(source(), [next_day], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "DATE_OFFSET")


def test_r2bet_day_uses_its_published_utc_plus_one_day() -> None:
    # 23:30 UTC on the 16th is 00:30 on the 17th in Lagos.
    kickoff = datetime(2026, 10, 16, 23, 30, tzinfo=UTC)
    assert date_relation(source(source_code="r2bet"), fixture(kickoff=kickoff)) == "SAME_DAY"
    assert date_relation(source(source_code="tips1960"), fixture(kickoff=kickoff)) == "SAME_DAY"
    assert date_relation(
        source(source_code="r2bet", prediction_date=date(2026, 10, 16)), fixture(kickoff=kickoff)
    ) == ("MIDNIGHT_ADJACENT")


def test_rescheduled_fixture_needs_review() -> None:
    moved = fixture(
        kickoff=datetime(2026, 11, 7, 14, tzinfo=UTC),
        earlier=(datetime(2026, 10, 17, 14, tzinfo=UTC),),
    )
    decision = decide(source(), [moved], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "RESCHEDULED_KICKOFF")


def test_exact_source_kickoff_and_contradictory_kickoff() -> None:
    kickoff = datetime(2026, 10, 17, 14, tzinfo=UTC)
    assert date_relation(source(source_kickoff_at=kickoff), fixture()) == "EXACT_KICKOFF"
    wrong = source(source_kickoff_at=kickoff + timedelta(hours=3))
    decision = decide(wrong, [fixture()], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "KICKOFF_MISMATCH")


def test_two_plausible_fixtures_need_review() -> None:
    first = fixture(key="a")
    twin = fixture(key="b", kickoff=datetime(2026, 10, 17, 18, tzinfo=UTC))
    decision = decide(source(), [first, twin], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "MULTIPLE_CANDIDATES")
    assert len(decision.candidates) == 2


def test_resolved_duplicates_count_as_one_fixture() -> None:
    first = fixture(key="a", effective="real")
    twin = fixture(key="b", effective="real", resolution="DUPLICATE_RESOLVED")
    decision = decide(source(), [first, twin], COUNTRIES)
    assert decision.classification == "CONTEXTUAL_MATCH"
    assert decision.fixture_id == uuid5(UUID(int=0), "real")


def test_unresolved_duplicate_blocks_automatic_match() -> None:
    quarantined = fixture(resolution="AMBIGUOUS_QUARANTINED")
    decision = decide(source(), [quarantined], COUNTRIES)
    assert decision.reason == "CANONICAL_IDENTITY_UNRESOLVED"


def test_missing_competition_requires_exact_names() -> None:
    target = fixture("Atletico Madrid", "Sevilla", competition="La Liga", country="Spain")
    exact = decide(source("Atletico Madrid", "Sevilla", competition="N/A"), [target], COUNTRIES)
    assert exact.classification == "CONTEXTUAL_MATCH"
    variant = decide(source("Atl. Madrid", "Sevilla", competition="N/A"), [target], COUNTRIES)
    assert (variant.classification, variant.reason) == ("NEEDS_REVIEW", "WEAK_CORROBORATION")
    labelled = decide(
        source("Atl. Madrid", "Sevilla", competition="ESP La Liga"), [target], COUNTRIES
    )
    assert labelled.classification == "CONTEXTUAL_MATCH"


def test_contradictory_source_evidence_needs_review() -> None:
    decision = decide(source(conflicting_evidence=True), [fixture()], COUNTRIES)
    assert (decision.classification, decision.reason) == (
        "NEEDS_REVIEW",
        "SOURCE_EVIDENCE_CONFLICT",
    )


@pytest.mark.parametrize(
    ("fixtures", "reason"),
    [
        ([], "NO_FIXTURES_FOR_DATE"),
        ([fixture("Arsenal", "Leeds")], "NO_CORRESPONDING_FIXTURE"),
        (
            [fixture("Everton", "Leeds", kickoff=datetime(2026, 10, 18, 15, tzinfo=UTC))],
            "ONE_TEAM_ONLY",
        ),
    ],
)
def test_unmatched_reasons(fixtures: list[CandidateFixture], reason: str) -> None:
    decision = decide(source(), fixtures, COUNTRIES)
    assert (decision.classification, decision.reason) == ("UNMATCHED", reason)


def test_missing_source_team_text() -> None:
    assert decide(source(home="--"), [fixture()], COUNTRIES).reason == "SOURCE_CONTEXT_MISSING"


@pytest.mark.parametrize(
    ("label", "name", "country", "kind", "division", "relation"),
    [
        ("SUI D1", "Super League", "Switzerland", "LEAGUE", 1, "COMPATIBLE"),
        ("SUI D1", "Super League", "Germany", "LEAGUE", 1, "CONFLICT"),
        ("GER D2", "2. Bundesliga", "Germany", "LEAGUE", 2, "COMPATIBLE"),
        ("GER D2", "Bundesliga", "Germany", "LEAGUE", 1, "CONFLICT"),
        ("ESP Copa del Rey", "Copa del Rey", "Spain", "CUP", None, "MATCH"),
        ("ESP Copa del Rey", "La Liga", "Spain", "LEAGUE", 1, "CONFLICT"),
        ("World", "UEFA Champions League", "World", "CUP", None, "COMPATIBLE"),
        ("England", "UEFA Champions League", "World", "CUP", None, "CONFLICT"),
        ("UEFA Nations League", "UEFA Nations League", "World", "CUP", None, "MATCH"),
        ("UEFA Nations League", "Premier League", "England", "LEAGUE", 1, "CONFLICT"),
        ("Premier League", "Premiership", "Wales", "LEAGUE", 1, "UNKNOWN"),
        ("N/A", "Premier League", "England", "LEAGUE", 1, "UNKNOWN"),
        ("Czech-Republic", "1. Liga", "Czech Republic", "LEAGUE", 1, "COMPATIBLE"),
    ],
)
def test_competition_relation(
    label: str, name: str, country: str, kind: str, division: int | None, relation: str
) -> None:
    context = competition_context(label, COUNTRIES | {country_key("Switzerland")})
    assert (
        competition_relation(
            context, name=name, country=country, competition_type=kind, division=division
        )
        == relation
    )


def test_one_exact_team_on_the_day_needs_review_not_a_match() -> None:
    decision = decide(source(), [fixture("Everton", "Leeds")], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "OPPONENT_UNCONFIRMED")
    assert decision.fixture_id is None


def test_provisional_copy_at_the_same_kickoff_uses_the_verified_record() -> None:
    verified = fixture(key="verified")
    copy = fixture(key="copy", identity="PROVISIONAL", competition="Premier League")
    quarantined = fixture(key="q", identity="PROVISIONAL", resolution="AMBIGUOUS_QUARANTINED")
    decision = decide(source(), [copy, verified, quarantined], COUNTRIES)
    assert (decision.classification, decision.reason) == (
        "CONTEXTUAL_MATCH",
        "UNIQUE_VERIFIED_TWIN",
    )
    assert decision.fixture_id == verified.fixture_id


@pytest.mark.parametrize(
    "rival",
    [
        fixture(key="second", identity="VERIFIED"),
        fixture(
            key="moved", identity="PROVISIONAL", kickoff=datetime(2026, 10, 17, 18, tzinfo=UTC)
        ),
    ],
)
def test_two_verified_or_moved_twins_need_review(rival: CandidateFixture) -> None:
    decision = decide(source(), [fixture(key="verified"), rival], COUNTRIES)
    assert (decision.classification, decision.reason) == ("NEEDS_REVIEW", "MULTIPLE_CANDIDATES")
