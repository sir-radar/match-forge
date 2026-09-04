from __future__ import annotations

from pathlib import Path

from football.contracts.source import sha256_bytes
from football.providers.football_data_uk import (
    FootballDataUkSourceResourceError,
    FootballDataUkSourceResourceV1,
)
from football.storage.raw import ImmutableFileConflict, ImmutableFileStore, ImmutableWrite


class FootballDataUkRawStoreV1:
    """Immutable raw-byte store for frozen Football-Data Phase 1B resources."""

    def __init__(self, data_root: Path) -> None:
        self._files = ImmutableFileStore(data_root)

    def publish(
        self,
        receipt: FootballDataUkSourceResourceV1,
        payload: bytes,
    ) -> ImmutableWrite:
        if len(payload) != receipt.raw_byte_size or sha256_bytes(payload) != receipt.raw_sha256:
            raise FootballDataUkSourceResourceError(
                "payload does not match source receipt byte size and SHA-256"
            )
        try:
            return self._files.publish(self.relative_path(receipt), payload)
        except ImmutableFileConflict as error:
            raise FootballDataUkSourceResourceError(
                "immutable raw bytes conflict with source receipt"
            ) from error

    def relative_path(self, receipt: FootballDataUkSourceResourceV1) -> str:
        source_path_digest = sha256_bytes(receipt.source_path.encode("utf-8"))
        filename = receipt.source_path.rsplit("/", maxsplit=1)[-1]
        return (
            f"raw/provider={receipt.provider_id}/source_path_sha256={source_path_digest}/"
            f"sha256={receipt.raw_sha256}/{filename}"
        )
