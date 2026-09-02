from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from football.contracts.source import PROVIDER_PATTERN, canonical_json_bytes

CredentialTypeV1 = Literal["api_key", "api_token", "oauth2_client", "basic_auth"]
_CREDENTIAL_TYPES = frozenset(("api_key", "api_token", "oauth2_client", "basic_auth"))
_REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s=?#]+$")


class ProviderCredentialError(ValueError):
    """A provider credential reference or configuration violates its contract."""


@dataclass(frozen=True, slots=True)
class ProviderCredentialRefV1:
    provider_id: str
    secret_reference: str
    credential_type: CredentialTypeV1
    rotation_id: str | None = None
    expires_at: datetime | None = None
    contract: str = "ProviderCredentialRefV1"

    def __post_init__(self) -> None:
        if self.contract != "ProviderCredentialRefV1":
            raise ProviderCredentialError("unsupported provider credential contract")
        if not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise ProviderCredentialError("provider_id must use lowercase snake_case")
        if not _REFERENCE_PATTERN.fullmatch(self.secret_reference):
            raise ProviderCredentialError("secret reference must be a non-secret URI")
        if self.credential_type not in _CREDENTIAL_TYPES:
            raise ProviderCredentialError("credential type is unsupported")
        if self.rotation_id is not None and not self.rotation_id:
            raise ProviderCredentialError("rotation_id must not be empty")
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ProviderCredentialError("credential expiry must be timezone-aware")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "secret_reference": self.secret_reference,
            "credential_type": self.credential_type,
            "rotation_id": self.rotation_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass(frozen=True, slots=True)
class ProviderConfigV1:
    provider_id: str
    base_url: str
    enabled_resources: tuple[str, ...]
    sync_policy_ref: str
    runtime_policy_ref: str
    credential_ref: ProviderCredentialRefV1 | None = None
    contract: str = "ProviderConfigV1"

    def __post_init__(self) -> None:
        if self.contract != "ProviderConfigV1":
            raise ProviderCredentialError("unsupported provider config contract")
        if not PROVIDER_PATTERN.fullmatch(self.provider_id):
            raise ProviderCredentialError("provider_id must use lowercase snake_case")
        _validate_https_url(self.base_url)
        if not self.enabled_resources or len(self.enabled_resources) != len(
            set(self.enabled_resources)
        ):
            raise ProviderCredentialError("enabled resources must be non-empty and unique")
        if any(not resource for resource in self.enabled_resources):
            raise ProviderCredentialError("enabled resources must not be empty")
        if not self.sync_policy_ref or not self.runtime_policy_ref:
            raise ProviderCredentialError("sync and runtime policy references are required")
        if self.credential_ref is not None and self.credential_ref.provider_id != self.provider_id:
            raise ProviderCredentialError("credential provider does not match provider config")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "provider_id": self.provider_id,
            "base_url": self.base_url,
            "enabled_resources": list(self.enabled_resources),
            "sync_policy_ref": self.sync_policy_ref,
            "runtime_policy_ref": self.runtime_policy_ref,
            "credential_ref": self.credential_ref.to_dict() if self.credential_ref else None,
        }


def _validate_https_url(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderCredentialError("provider base_url must be HTTPS without credentials")
