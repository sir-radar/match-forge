import hashlib
import io
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from football.product.football_data_uk import ArchiveLimits, csv_members


def archive(
    entries: list[tuple[str | zipfile.ZipInfo, bytes]], compression: int = zipfile.ZIP_STORED
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as target:
        for name, data in entries:
            target.writestr(name, data)
    return output.getvalue()


def test_valid_csv_archive_preserves_bytes_and_names() -> None:
    raw = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG\nE0,01/01/2020,Home,Away,1,0\n"
    assert list(csv_members(archive([("E0.csv", raw)]))) == [("E0.csv", raw)]


@pytest.mark.parametrize(
    "name", ["../outside.csv", "/outside.csv", "C:\\outside.csv", "folder/../../bad.csv"]
)
def test_archive_path_traversal_fails_closed(name: str) -> None:
    with pytest.raises(ValueError, match="unsafe archive member path"):
        csv_members(archive([(name, b"safe")]))


def test_archive_symlinks_and_unsupported_compression_are_rejected() -> None:
    link = zipfile.ZipInfo("link.csv")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError, match="link/type"):
        csv_members(archive([(link, b"../outside")]))
    with pytest.raises(ValueError, match="unsupported"):
        csv_members(archive([("data.csv", b"safe")], zipfile.ZIP_LZMA))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("compressed_bytes", 10, "compressed size"),
        ("extracted_bytes", 6, "total expansion"),
        ("entries", 1, "entry limit"),
        ("file_bytes", 3, "member size"),
    ],
)
def test_explicit_archive_size_and_count_bounds(field: str, value: int, message: str) -> None:
    limits = replace(ArchiveLimits(), **{field: value})
    with pytest.raises(ValueError, match=message):
        csv_members(archive([("a.csv", b"1234"), ("b.csv", b"5678")]), limits=limits)


def test_decompression_bomb_and_duplicate_members_are_rejected() -> None:
    with pytest.raises(ValueError, match="ratio|expansion"):
        csv_members(archive([("bomb.csv", b"0" * 100000)], zipfile.ZIP_DEFLATED))
    with pytest.raises(ValueError, match="duplicate"):
        csv_members(archive([("data.csv", b"1"), ("DATA.csv", b"2")]))


def test_archive_duration_and_malformed_input_are_bounded() -> None:
    with pytest.raises(ValueError, match="deadline"):
        csv_members(
            archive([("data.csv", b"valid")]),
            limits=replace(ArchiveLimits(), extraction_seconds=1e-9),
        )
    with pytest.raises(zipfile.BadZipFile):
        csv_members(b"not a ZIP")


def test_configured_archive_limits_reject_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCHFORGE_ARCHIVE_FILE_BYTES", "-1")
    with pytest.raises(ValueError, match="positive integers"):
        ArchiveLimits.from_env()
    with pytest.raises(ValueError, match="finite"):
        replace(ArchiveLimits(), ratio=float("inf"))


def test_retained_supported_archive_bytes_remain_compatible() -> None:
    # Optional retained evidence is verified locally; deterministic tests above run everywhere.
    root = Path(".local/football-data/football_data_uk")
    for path in root.rglob("*.zip"):
        payload = path.read_bytes()
        assert hashlib.sha256(payload).hexdigest() == path.stem
        expected: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(io.BytesIO(payload)) as source:
            for member in sorted(source.infolist(), key=lambda item: item.filename):
                if member.filename.casefold().endswith(".csv") and not member.is_dir():
                    expected.append((member.filename, source.read(member)))
        assert list(csv_members(payload, limits=ArchiveLimits())) == expected
