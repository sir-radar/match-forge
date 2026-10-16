"""Immutable observation artifact registration; never canonical identity admission."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

from football.contracts.observation_schema import observation_schema, observation_schema_sha256
from football.contracts.observations import Observation, ObservationError, observation_from_bytes
from football.storage.raw import ImmutableFileStore


class ObservationArtifactStore:
    def __init__(self, connection: Connection[Any], root: Path) -> None:
        self.connection = connection
        self.files = ImmutableFileStore(root)

    def publish(self, observation: Observation) -> UUID:
        """Identical retries converge; failed DB writes can leave safe orphan files."""
        digest = observation.sha256
        relative = f"observations/v1/{observation.CONTRACT}/{digest}.json"
        self.files.publish(relative, observation.to_bytes())
        schema_hash = observation_schema_sha256()
        self._register_contract(observation, schema_hash)
        provenance, versions, time = observation.provenance, observation.versions, observation.time
        provider = self.connection.execute(
            "SELECT id FROM football.providers WHERE code=%s", (provenance.provider,)
        ).fetchone()
        if provider is None:
            raise ObservationError("observation provider is not registered")
        values = (
            observation.observation_id,
            observation.CONTRACT,
            versions.observation_contract_version,
            schema_hash,
            provider[0],
            provenance.provider_native_id,
            provenance.source_record_key,
            provenance.source_snapshot_id,
            provenance.source_resource_id,
            provenance.source_sha256,
            versions.provider_schema_version,
            versions.adapter_version,
            versions.normalizer_version,
            versions.resolution_version,
            time.observed_at,
            time.acquired_at,
            time.known_at,
            time.event_time,
            time.provider_updated_at,
            time.valid_from,
            time.valid_to,
            relative,
            digest,
        )
        self.connection.execute(
            """INSERT INTO football.resource_observation_artifacts (
                observation_id,contract_name,observation_contract_version,schema_sha256,
                provider_id,provider_native_id,source_record_key,source_snapshot_id,
                source_resource_id,source_sha256,provider_schema_version,adapter_version,
                normalizer_version,resolution_version,observed_at,acquired_at,known_at,
                event_time,provider_updated_at,valid_from,valid_to,artifact_path,artifact_sha256)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (observation_id) DO NOTHING""",
            values,
        )
        return observation.observation_id

    def _register_contract(self, observation: Observation, schema_hash: str) -> None:
        key = (observation.CONTRACT, observation.versions.observation_contract_version)
        self.connection.execute(
            """INSERT INTO football.observation_contract_schemas (
                contract_name,observation_contract_version,schema_sha256,schema_document)
               VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (*key, schema_hash, Jsonb(observation_schema())),
        )
        row = self.connection.execute(
            """SELECT schema_sha256 FROM football.observation_contract_schemas
               WHERE contract_name=%s AND observation_contract_version=%s""",
            key,
        ).fetchone()
        if row != (schema_hash,):
            raise ObservationError("registered observation contract version has different bytes")

    def load(self, observation_id: UUID) -> Observation:
        row = self.connection.execute(
            """SELECT artifact_path,artifact_sha256 FROM football.resource_observation_artifacts
               WHERE observation_id=%s""",
            (observation_id,),
        ).fetchone()
        if row is None:
            raise ObservationError("observation artifact is not registered")
        path = self.files.path_for(row[0])
        if path.is_symlink():
            raise ObservationError("observation artifact must not be a symlink")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != row[1]:
            raise ObservationError("observation artifact checksum mismatch")
        result = observation_from_bytes(payload)
        if result.observation_id != observation_id:
            raise ObservationError("observation artifact identity mismatch")
        return result
