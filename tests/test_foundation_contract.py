import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_language_toolchains_are_exactly_pinned() -> None:
    assert (PROJECT_ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.13.14"

    rust = tomllib.loads((PROJECT_ROOT / "rust-toolchain.toml").read_text(encoding="utf-8"))
    assert rust["toolchain"] == {
        "channel": "1.97.1-aarch64-apple-darwin",
        "components": ["clippy", "rustfmt"],
        "profile": "minimal",
    }

    go_mod = (PROJECT_ROOT / "go" / "api" / "go.mod").read_text(encoding="utf-8")
    assert "go 1.27\n" in go_mod
    assert "toolchain go1.27.0\n" in go_mod


def test_container_images_are_digest_pinned_and_loopback_only() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert (
        "postgres:18.6-bookworm@sha256:"
        "1c59e2c3c818eaa0f0628f695b36e7c9e362d6b219b36a54a32df645cbd7e1af"
    ) in compose
    assert (
        "redis:8.10.0-alpine3.23@sha256:"
        "978f0e01593e65eed801f2402944efcd936d43b5027e4908a7897baf88ed6241"
    ) in compose
    assert '"127.0.0.1:${POSTGRES_PORT:-55433}:5432"' in compose
    assert '"127.0.0.1:${REDIS_PORT:-56379}:6379"' in compose


def test_gate_a_migration_is_not_a_production_migration() -> None:
    production_migration = (
        PROJECT_ROOT / "infrastructure" / "migrations" / "202608290001_gate_a_contract.sql"
    )
    prototype_migration = (
        PROJECT_ROOT
        / "experiments"
        / "sprint1_roundtrip"
        / "migrations"
        / "202608290001_gate_a_contract.sql"
    )

    assert not production_migration.exists()
    assert prototype_migration.is_file()
