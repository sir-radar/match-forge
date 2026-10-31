"""Read contracts reject unsafe pagination and misleading migration readiness."""

from pathlib import Path

import pytest
from football.product.resolution_center import validate_query
from football.product.resolution_migration import STAGES, migration_report


@pytest.mark.parametrize("value", [0, -1, 1, 25, 101, True, "25"])
def test_invalid_page_size_is_rejected(value):
    with pytest.raises(ValueError):
        validate_query({"page_size": value})


def test_only_supported_filters_are_accepted():
    validate_query({"page": 1, "page_size": 100, "q": "team"})
    with pytest.raises(ValueError):
        validate_query({"force": True})
    with pytest.raises(ValueError):
        validate_query({"provider": "x" * 257})


def test_tracked_parity_never_promotes_bounded_warnings_to_full_readiness():
    report = migration_report(Path("."))
    assert report["status"] == "BLOCKED" and report["production_cutover"] is False
    assert len(report["stages"]) == len(STAGES) == 13
    assert all(
        stage["current_route"] == "LEGACY" and not stage["v2_ready"] for stage in report["stages"]
    )
    assert report["exceptions"]["generic_elo_conflicts"] == 59
    assert report["exceptions"]["insufficient_history_targets"] == 327


def test_bulk_raw_verification_accepts_relative_roots_without_weakening_hash_checks(
    tmp_path, monkeypatch
):
    import hashlib
    from uuid import uuid4

    from football.integrity import verify_raw_resource_file

    monkeypatch.chdir(tmp_path)
    payload = b"retained test resource"
    path = Path("data/raw/provider=statsbomb_open_data/snapshot=revision/resource.json")
    path.parent.mkdir(parents=True)
    path.write_bytes(payload)
    arguments = (
        Path("data"),
        uuid4(),
        "statsbomb_open_data",
        "revision",
        "resource.json",
        hashlib.sha256(payload).hexdigest(),
        len(payload),
    )
    assert verify_raw_resource_file(*arguments).status == "PASS"
    path.write_bytes(b"tampered")
    assert verify_raw_resource_file(*arguments).status == "CHECKSUM_MISMATCH"
    path.unlink()
    assert verify_raw_resource_file(*arguments).status == "MISSING"


def test_football_data_uk_recovery_uses_content_addressed_native_path(tmp_path):
    import hashlib

    from football.product.resolution_data import resource_files

    payload = b"Date,HomeTeam,AwayTeam\n31/10/2026,Home,Away\n"
    digest = hashlib.sha256(payload).hexdigest()
    row = (
        "football_data_uk",
        "source-manifest.json",
        "b" * 64,
        "fixture-source",
        "revision",
        None,
        "resource",
        "mmz4281/2627/E0.csv",
        digest,
        len(payload),
    )
    registered = resource_files(tmp_path, row)
    assert len(registered) == 1
    assert registered[0]["path"].startswith("raw/provider=football_data_uk/source_path_sha256=")
    assert registered[0]["path"].endswith(f"/sha256={digest}/E0.csv")
    assert registered[0]["sha256"] == digest
