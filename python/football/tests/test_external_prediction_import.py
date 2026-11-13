import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from football.product.external_predictions import (
    ImportedPrediction,
    parse_import,
    prediction_revision_sha256,
)


def prediction(
    *,
    original_date_text: str = "Today, 30 September",
    home_team: str = "Arsenal FC",
    away_team: str = "Chelsea FC",
    selection: str = "HOME_WIN",
) -> ImportedPrediction:
    return ImportedPrediction(
        source_page="https://example.test/picks",
        prediction_date=date(2026, 9, 30),
        original_date_text=original_date_text,
        competition="Premier League",
        home_team=home_team,
        away_team=away_team,
        market="ONE_X_TWO",
        selection=selection,
    )


def test_import_parser_normalizes_market_and_preserves_date_text(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_page": "https://example.test/picks",
                    "prediction_date": "2026-09-30",
                    "original_date_text": "Today, 30 September",
                    "competition": "Premier League",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "selection": "1X",
                }
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_import(path)

    assert rows[0].market == "DOUBLE_CHANCE"
    assert rows[0].selection == "HOME_OR_DRAW"
    assert rows[0].original_date_text == "Today, 30 September"


def test_import_parser_rejects_unsupported_market(tmp_path: Path) -> None:
    path = tmp_path / "predictions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source_page": "https://example.test/picks",
                    "prediction_date": "2026-09-30",
                    "original_date_text": "30/09",
                    "competition": "Premier League",
                    "home_team": "Arsenal",
                    "away_team": "Chelsea",
                    "selection": "First goalscorer",
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported external selection"):
        parse_import(path)


def test_import_parser_normalizes_kickoff_and_requires_complete_provider_identity(
    tmp_path: Path,
) -> None:
    base = {
        "source_page": "https://example.test/picks",
        "prediction_date": "2026-09-30",
        "original_date_text": "30/09",
        "competition": "Premier League",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "selection": "1",
        "kickoff_at": "2026-10-01T00:30:00+01:00",
        "source_timezone": "Africa/Lagos",
        "provider_code": "pitchapi",
        "provider_fixture_id": "m_B8x2K9",
    }
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps([base]), encoding="utf-8")
    row = parse_import(path)[0]
    assert row.kickoff_at == datetime(2026, 9, 30, 23, 30, tzinfo=UTC)
    assert row.source_timezone == "Africa/Lagos"

    del base["provider_fixture_id"]
    path.write_text(json.dumps([base]), encoding="utf-8")
    with pytest.raises(ValueError, match="supplied together"):
        parse_import(path)


def test_revision_identity_preserves_source_date_text_and_changed_selection() -> None:
    original = prediction()
    digest = prediction_revision_sha256("tips1960", original)

    assert prediction_revision_sha256("tips1960", original) == digest
    assert prediction_revision_sha256("r2bet", original) != digest
    assert (
        prediction_revision_sha256("tips1960", prediction(original_date_text="30/09/2026"))
        != digest
    )
    assert prediction_revision_sha256("tips1960", prediction(selection="DRAW")) != digest


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("https://api.pitchapi.dev/v1/matches/m_B8x2K9", ("pitchapi", "m_B8x2K9")),
        ("https://api.football-data.org/v4/matches/330299", ("football_data_org", "330299")),
        ("https://www.fotmob.com/matches/home-vs-away/abc#12345", ("fotmob", "12345")),
        ("https://api.pitchapi.dev.invalid/v1/matches/m_B8x2K9", None),
        ("https://r2bet.com/index.php/match-details/123-free/home-vs-away", None),
    ],
)
def test_fixture_reference_requires_a_known_provider_namespace(
    reference: str, expected: tuple[str, str] | None
) -> None:
    from football.product.external_predictions import provider_fixture_reference

    assert provider_fixture_reference(reference) == expected
