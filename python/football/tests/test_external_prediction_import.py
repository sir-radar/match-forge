import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from football.product.external_predictions import (
    ImportedPrediction,
    parse_import,
    prediction_revision_sha256,
    unique_fixture_id,
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


def test_fixture_mapping_requires_one_exact_normalized_match() -> None:
    row = prediction(home_team="Arsenal", away_team="Chelsea")

    assert unique_fixture_id([("fixture-1", "Arsenal FC", "Chelsea FC")], row) == "fixture-1"
    assert unique_fixture_id([], row) is None
    assert (
        unique_fixture_id(
            [
                ("fixture-1", "Arsenal FC", "Chelsea FC"),
                ("fixture-2", "Arsenal", "Chelsea"),
            ],
            row,
        )
        is None
    )
