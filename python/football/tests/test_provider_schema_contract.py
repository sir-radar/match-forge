from __future__ import annotations

import pytest
from football.providers import ProviderResourceContractV1, ProviderSchemaContractError


def test_schema_contract_accepts_additive_fields_and_surfaces_unknown_enums() -> None:
    contract = _contract()

    additive = contract.inspect({"id": "m1", "state": "scheduled", "new_field": 1})
    assert additive.status == "accepted"
    assert additive.unknown_additive_fields == ("new_field",)

    enum = contract.inspect({"id": "m1", "state": "postponed"})
    assert enum.status == "accepted_with_warnings"
    assert enum.unknown_enum_fields == ("state",)


def test_schema_contract_quarantines_missing_required_or_unsupported_version() -> None:
    contract = _contract()

    missing = contract.inspect({"state": "scheduled"})
    assert missing.status == "quarantine"
    assert missing.missing_required_fields == ("id",)
    version = contract.inspect({"id": "m1", "schema_version": "v2"})
    assert version.status == "quarantine"


def test_schema_contract_rejects_duplicate_fields_and_enum_values() -> None:
    with pytest.raises(ProviderSchemaContractError, match="required fields must be unique"):
        _contract(required_fields=("id", "id"))
    with pytest.raises(ProviderSchemaContractError, match="enum values must be unique"):
        _contract(enum_fields={"state": ("scheduled", "scheduled")})


def _contract(
    *,
    required_fields: tuple[str, ...] = ("id",),
    enum_fields: dict[str, tuple[str, ...]] | None = None,
) -> ProviderResourceContractV1:
    return ProviderResourceContractV1(
        provider_id="provider",
        resource="fixtures",
        schema_version="v1",
        adapter_version="provider-v1",
        parser_version="parser-v1",
        normalizer_version="normalizer-v1",
        required_fields=required_fields,
        optional_fields=("state",),
        enum_fields=enum_fields or {"state": ("scheduled", "finished")},
    )
