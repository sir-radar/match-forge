from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from football.providers import (
    ProviderConfigV1,
    ProviderCredentialError,
    ProviderCredentialRefV1,
)


def test_credential_reference_contains_no_secret_and_config_is_canonical() -> None:
    credential = _credential()
    config = ProviderConfigV1(
        provider_id="totalcorner_api",
        base_url="https://api.totalcorner.com/v1/",
        enabled_resources=("fixtures", "odds"),
        sync_policy_ref="sync:totalcorner",
        runtime_policy_ref="runtime:totalcorner",
        credential_ref=credential,
    )

    assert "token-value" not in str(config.to_dict())
    credential_payload = cast(dict[str, object], config.to_dict()["credential_ref"])
    assert credential_payload["secret_reference"] == "secret://totalcorner/api"
    assert len(config.sha256) == 64


def test_credentials_reject_plaintext_or_mismatched_provider() -> None:
    with pytest.raises(ProviderCredentialError, match="non-secret URI"):
        ProviderCredentialRefV1("provider", "token-value", "api_token")
    with pytest.raises(ProviderCredentialError, match="does not match"):
        ProviderConfigV1(
            provider_id="provider",
            base_url="https://example.test/api",
            enabled_resources=("fixtures",),
            sync_policy_ref="sync:provider",
            runtime_policy_ref="runtime:provider",
            credential_ref=_credential(provider_id="other"),
        )


def test_credentials_require_safe_url_and_timezone_aware_expiry() -> None:
    with pytest.raises(ProviderCredentialError, match="HTTPS"):
        ProviderConfigV1(
            provider_id="provider",
            base_url="http://example.test/api",
            enabled_resources=("fixtures",),
            sync_policy_ref="sync:provider",
            runtime_policy_ref="runtime:provider",
        )
    with pytest.raises(ProviderCredentialError, match="timezone-aware"):
        _credential(expires_at=datetime(2026, 1, 1))


def _credential(
    *,
    provider_id: str = "totalcorner_api",
    expires_at: datetime | None = datetime(2027, 1, 1, tzinfo=UTC),
) -> ProviderCredentialRefV1:
    return ProviderCredentialRefV1(
        provider_id=provider_id,
        secret_reference="secret://totalcorner/api",
        credential_type="api_token",
        rotation_id="rotation-1",
        expires_at=expires_at,
    )
