from __future__ import annotations

from typing import Any

from football.product.identity_audit import audit_report


class _Cursor:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, params: object) -> None:
        assert "bool_or" in query
        assert params == ("explicit_crosswalk", "manual")

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._rows


class _Connection:
    def __init__(self, result_sets: list[list[tuple[object, ...]]]) -> None:
        self._result_sets = iter(result_sets)

    def cursor(self) -> _Cursor:
        return _Cursor(next(self._result_sets))


def test_identity_audit_passes_without_unsafe_shared_ids() -> None:
    report = audit_report(_Connection([[], []]))  # type: ignore[arg-type]

    assert report == {
        "contract": "ProviderIdentityAuditV1",
        "status": "PASS",
        "unsafe_shared_identity_count": 0,
        "findings": [],
    }


def test_identity_audit_reports_unreviewed_cross_provider_mapping() -> None:
    connection: Any = _Connection(
        [
            [],
            [
                (
                    "10000000-0000-4000-8000-000000000001",
                    ["api_football", "football_data_uk"],
                    ["deterministic"],
                    2,
                )
            ],
        ]
    )

    report = audit_report(connection)

    assert report["status"] == "FAIL"
    assert report["unsafe_shared_identity_count"] == 1
    assert report["findings"] == [
        {
            "entity_type": "team",
            "matchforge_id": "10000000-0000-4000-8000-000000000001",
            "providers": ["api_football", "football_data_uk"],
            "mapping_methods": ["deterministic"],
            "mapping_count": 2,
        }
    ]
