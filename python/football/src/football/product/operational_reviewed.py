"""Reviewed mapping actions for the operational provider sync."""

from __future__ import annotations

from datetime import UTC
from typing import Any, cast
from uuid import UUID

from football.product.domain import (
    sha256_json,
)
from football.product.identity_admission import (
    RetainedIdentityVerifier,
    admit_provider_mappings,
    verify_source_identifier,
)
from football.product.operational_identity import OperationalIdentityMixin
from football.product.operational_support import (
    FixtureObservation,
)
from football.providers.pitchapi import (
    PitchApiFixture,
)
from football.storage.locks import IDENTITY_ADMISSION_LOCK, acquire_locks


class OperationalReviewedMappingMixin(OperationalIdentityMixin):
    """Preview and apply owner-reviewed fixture mappings."""

    def preview_reviewed_mapping(
        self,
        provider_match_id: str,
        fixture_id: UUID,
        *,
        source_snapshot_id: UUID | None = None,
        verifier: RetainedIdentityVerifier | None = None,
    ) -> dict[str, Any]:
        """Qualify the exact same retained inputs as apply without publishing a decision."""
        source, candidate, _, verifier = self._prepare_reviewed_mapping(
            provider_match_id, fixture_id, source_snapshot_id, verifier=verifier
        )
        return {
            "provider": self.provider_code,
            "provider_match_id": provider_match_id,
            "fixture_id": str(fixture_id),
            "source_snapshot_id": str(source[16]),
            "input_sha256": sha256_json([list(map(str, source)), list(map(str, candidate))]),
            "source_bytes_verified": verifier.source_bytes_verified,
        }

    def _prepare_reviewed_mapping(
        self,
        provider_match_id: str,
        fixture_id: UUID,
        source_snapshot_id: UUID | None,
        *,
        verifier: RetainedIdentityVerifier | None = None,
    ) -> tuple[tuple[Any, ...], tuple[Any, ...], PitchApiFixture, RetainedIdentityVerifier]:
        source, candidate = self._reviewed_mapping_inputs(
            provider_match_id, fixture_id, source_snapshot_id
        )
        verifier = verifier or RetainedIdentityVerifier(self.data_root)
        row = PitchApiFixture(
            provider_match_id=provider_match_id,
            provider_competition_id=source[0],
            provider_home_team_id=source[2],
            provider_away_team_id=source[4],
            home_team_name=source[3],
            away_team_name=source[5],
            kickoff_at=source[6],
            status=source[7],
            provider_status=source[8] or "",
            home_score=source[9],
            away_score=source[10],
            minute=source[11],
            added_time=source[12],
            period=source[13],
            source_updated_at=source[14],
            observed_at=source[15],
            provider_competition_name=source[1],
            result_score_basis=source[17],
        )
        snapshot_id = cast(UUID, source[16])
        self._validate_reviewed_context(row, candidate)
        for entity_type, identifier in (
            ("competition", row.provider_competition_id),
            ("team", row.provider_home_team_id),
            ("team", row.provider_away_team_id),
        ):
            if (
                verify_source_identifier(
                    self.connection,
                    self.data_root,
                    snapshot_id,
                    self.provider_code,
                    entity_type,
                    identifier,
                    None,
                    verifier,
                )
                is None
            ):
                raise ValueError("reviewed mapping requires verified retained provider identifiers")
        return source, candidate, row, verifier

    def apply_reviewed_mapping(
        self,
        provider_match_id: str,
        fixture_id: UUID,
        *,
        source_snapshot_id: UUID | None = None,
        competition_only: bool = False,
        verifier: RetainedIdentityVerifier | None = None,
    ) -> None:
        """Apply an explicit operator-reviewed fixture mapping using stored evidence."""
        source, candidate, row, verifier = self._prepare_reviewed_mapping(
            provider_match_id, fixture_id, source_snapshot_id, verifier=verifier
        )
        verifier.seal()
        snapshot_id = cast(UUID, source[16])
        acquire_locks(self.connection, (IDENTITY_ADMISSION_LOCK,))
        if self._reviewed_mapping_inputs(provider_match_id, fixture_id, source_snapshot_id) != (
            source,
            candidate,
        ):
            raise ValueError("reviewed mapping inputs changed; prepare again before locking")
        members = self._retained_fixture_members(row)
        self._persist_deterministic_mapping(
            row,
            snapshot_id,
            candidate,
            mapping_method="manual",
            competition_only=competition_only,
        )
        review = self._record_mapping_decision(
            row,
            snapshot_id,
            fixture_id,
            "MANUAL_ACCEPTED",
            "operator explicitly accepted mapping",
            {
                "reviewed_fixture_id": str(fixture_id),
                "competition_only": competition_only,
            },
        )
        admit_provider_mappings(
            self.connection,
            self.data_root,
            self.provider_code,
            snapshot_id,
            entity_types=("competition",) if competition_only else ("competition", "team"),
            verifier=verifier,
        )
        if competition_only:
            return
        for member in members:
            self._resolve_reviewed_member(member, candidate, row, snapshot_id, review)
        self._update_canonical_fixture(row, fixture_id, snapshot_id)
        self._insert_qualified_history(row, fixture_id, snapshot_id)

    def _reviewed_mapping_inputs(
        self, provider_match_id: str, fixture_id: UUID, source_snapshot_id: UUID | None
    ) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT provider_competition_id, provider_competition_name,
                          provider_home_team_id, provider_home_team_name,
                          provider_away_team_id, provider_away_team_name,
                          kickoff_at, canonical_status, provider_status,
                          home_score, away_score, match_minute, added_time, period,
                          source_updated_at, observed_at, source_snapshot_id,
                          result_score_basis, canonical_fixture_id
                     FROM football.product_provider_fixture_observations
                    WHERE provider_code = %s AND provider_match_id = %s
                      AND (%s::uuid IS NULL OR source_snapshot_id=%s)
                    ORDER BY observed_at DESC, observation_id DESC LIMIT 1""",
                (self.provider_code, provider_match_id, source_snapshot_id, source_snapshot_id),
            )
            source = cursor.fetchone()
            if source is None or any(source[index] is None for index in (0, 1, 2, 3, 4, 5)):
                raise ValueError("stored provider identity evidence is incomplete")
            cursor.execute(
                """SELECT fixture.fixture_id, fixture.competition_id,
                          fixture.home_team_id, fixture.away_team_id,
                          competition.name, home.name, away.name,
                          fixture.status, fixture.home_score, fixture.away_score,
                          fixture.kickoff_at,
                          fixture.identity_status,
                          COALESCE((SELECT source_kickoff_precision
                            FROM football.product_team_match_history h
                            WHERE h.fixture_id=fixture.fixture_id),'EXACT')
                     FROM football.product_effective_fixtures fixture
                     JOIN football.product_competitions competition
                       ON competition.competition_id = fixture.competition_id
                     JOIN football.product_teams home ON home.team_id = fixture.home_team_id
                     JOIN football.product_teams away ON away.team_id = fixture.away_team_id
                    WHERE fixture.fixture_id = %s""",
                (fixture_id,),
            )
            candidate = cursor.fetchone()
            if candidate is None:
                raise ValueError("reviewed canonical fixture does not exist")
            if candidate[11] != "VERIFIED":
                raise ValueError("reviewed target must be a verified canonical fixture")
        return source, candidate

    def _validate_reviewed_context(
        self,
        row: FixtureObservation,
        candidate: tuple[Any, ...],
    ) -> None:
        date_score_match = (
            candidate[12] == "DATE_ONLY"
            and row.status == candidate[7] == "FINISHED"
            and row.kickoff_at.astimezone(UTC).date() == candidate[10].astimezone(UTC).date()
            and (row.home_score, row.away_score) == (candidate[8], candidate[9])
            and row.result_score_basis == "REGULATION_90"
        )
        if not date_score_match and abs(row.kickoff_at - candidate[10]) > self.kickoff_tolerance:
            raise ValueError("reviewed fixture kickoff contradicts retained provider context")
        if (
            row.status == candidate[7] == "FINISHED"
            and candidate[8] is not None
            and (candidate[8], candidate[9]) != (row.home_score, row.away_score)
        ):
            raise ValueError("reviewed fixture result contradicts retained provider context")
