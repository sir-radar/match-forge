"""Experimental database selection fails before publication or provider side effects."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from football.observations.cli import main as observation_main
from football.providers.normalization.cli import main as normalization_main
from football.storage import experimental


def test_no_explicit_experimental_target_never_connects_or_launches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect, launch = Mock(), Mock()
    monkeypatch.setattr("football.storage.experimental.psycopg.connect", connect)
    monkeypatch.setattr("football.storage.experimental.subprocess.run", launch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://operating/football")
    with pytest.raises(SystemExit):
        experimental.main(["--", "python", "provider-acquisition.py"])
    connect.assert_not_called()
    launch.assert_not_called()


@pytest.mark.parametrize("key", ["PGSERVICE", "PGHOSTADDR", "PGDATABASE", "PGOPTIONS"])
def test_redirecting_environment_fails_closed(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    connect = Mock()
    monkeypatch.setattr("football.storage.experimental.psycopg.connect", connect)
    monkeypatch.setenv(key, "untrusted")
    with (
        pytest.raises(experimental.IsolationError, match="connection environment"),
        experimental.experimental_connection(
            "postgresql://test@127.0.0.1:5432/shadow", "postgresql://test@127.0.0.1:5432/operating"
        ),
    ):
        pytest.fail("redirected target was accepted")
    connect.assert_not_called()


@pytest.mark.parametrize(
    "target",
    [
        "",
        "dbname=shadow",
        "service=shadow",
        "postgresql://test@host1,host2:5432/shadow",
        "host=127.0.0.1 port=5432 user=test dbname=shadow "
        "options='-c matchforge.database_role=experimental'",
    ],
)
def test_ambiguous_target_is_rejected_before_connection(
    monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    connect = Mock()
    monkeypatch.setattr("football.storage.experimental.psycopg.connect", connect)
    with (
        pytest.raises(experimental.IsolationError),
        experimental.experimental_connection(target, "postgresql://test@127.0.0.1:5432/operating"),
    ):
        pytest.fail("ambiguous target was accepted")
    connect.assert_not_called()


def test_shadow_publication_clis_cannot_inherit_operating_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect = Mock()
    monkeypatch.setattr("football.storage.experimental.psycopg.connect", connect)
    monkeypatch.setenv("DATABASE_URL", "postgresql://operating/football")
    with pytest.raises(SystemExit):
        normalization_main(
            [
                "--source-resource-id",
                "00000000-0000-0000-0000-000000000001",
                "--resource",
                "results",
                "--data-root",
                str(tmp_path),
                "--artifact-root",
                str(tmp_path),
                "--persist",
            ]
        )
    with pytest.raises(SystemExit):
        observation_main(["store", str(tmp_path / "absent.json"), "--data-root", str(tmp_path)])
    connect.assert_not_called()
    assert list(tmp_path.iterdir()) == []
