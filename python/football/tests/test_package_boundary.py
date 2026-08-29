from importlib import import_module

import football


def test_production_package_exposes_expected_boundaries() -> None:
    assert football.__version__ == "0.1.0"
    for module in (
        "cli",
        "contracts",
        "datasets",
        "ingestion",
        "normalization",
        "providers",
        "storage",
        "temporal",
        "validation",
    ):
        assert import_module(f"football.{module}") is not None
