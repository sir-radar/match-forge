"""Season qualification for the operational provider sync."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any, cast
from uuid import UUID

from football.product.domain import (
    stable_id,
)
from football.product.identity_admission import (
    fixture_identity_blockers,
)
from football.product.identity_crosswalks import OPERATIONAL_COMPETITION_CROSSWALKS
from football.product.operational_store import OperationalStoreMixin
from football.product.operational_support import (
    FixtureObservation,
    SyncCounts,
)


class OperationalSeasonMixin(OperationalStoreMixin):
    """Qualify provider season labels against verified crosswalks."""

    def _season_qualification(
        self, snapshot: UUID, rows: Sequence[FixtureObservation], counts: SyncCounts
    ) -> dict[str, object]:
        if not rows:
            return {"status": "ADVERTISED_BUT_UNUSABLE", "qualified_results": 0}
        registered = self.connection.execute(
            """SELECT clock_timestamp() FROM football.source_snapshots s
               JOIN football.providers p ON p.id=s.provider_id
               WHERE s.id=%s AND s.status='validated' AND p.code=%s""",
            (snapshot, self.provider_code),
        ).fetchone()
        if registered is None:
            return {
                "status": "BLOCKED_IDENTITY",
                "qualified_results": 0,
                "reason": "RETAINED_SOURCE_EVIDENCE_REQUIRED",
            }
        results = [row for row in rows if row.status == "FINISHED"]
        # Identical retained facts can keep an earlier observation snapshot. Match
        # their native context rather than requiring acquisition-specific duplicates.
        contexts = [
            {
                "match_id": row.provider_match_id,
                "competition": row.provider_competition_id,
                "home": row.provider_home_team_id,
                "away": row.provider_away_team_id,
                "kickoff": row.kickoff_at.isoformat(),
                "status": row.status,
                "home_score": row.home_score,
                "away_score": row.away_score,
                "basis": row.result_score_basis,
            }
            for row in rows
        ]
        observed = self.connection.execute(
            """WITH context AS (SELECT * FROM jsonb_to_recordset(%s::jsonb) AS c(
                 match_id text,competition text,home text,away text,kickoff timestamptz,
                 status text,home_score smallint,away_score smallint,basis text))
               SELECT DISTINCT o.provider_match_id,f.fixture_id,f.identity_status,
                   c.status='FINISHED' AND c.basis='REGULATION_90' AND EXISTS (
                       SELECT 1 FROM football.product_eligible_fixture_history_at(
                           %s,ARRAY[f.fixture_id]) h
                       WHERE (h.home_goals,h.away_goals)=(o.home_score,o.away_score)) qualified,
                   EXISTS (SELECT 1 FROM football.product_team_match_history h
                       WHERE h.fixture_id=f.fixture_id AND c.status='FINISHED'
                         AND (h.home_goals,h.away_goals)<>
                             (o.home_score,o.away_score)) result_conflict
               FROM context c JOIN football.product_provider_fixture_observations o
                 ON o.provider_code=%s AND o.provider_match_id=c.match_id
                AND o.provider_competition_id=c.competition
                AND o.provider_home_team_id=c.home AND o.provider_away_team_id=c.away
                AND o.kickoff_at=c.kickoff AND o.canonical_status=c.status
                AND o.home_score IS NOT DISTINCT FROM c.home_score
                AND o.away_score IS NOT DISTINCT FROM c.away_score
                AND o.result_score_basis=c.basis
               JOIN football.product_effective_fixtures f
                 ON f.fixture_id=o.canonical_fixture_id
               WHERE NOT EXISTS (SELECT 1 FROM football.fixture_identity_resolutions r
                   WHERE r.member_fixture_id=f.fixture_id AND r.active
                     AND r.representative_fixture_id<>r.member_fixture_id)""",
            (json.dumps(contexts), registered[0], self.provider_code),
        ).fetchall()
        count = len({o[0] for o in observed if o[3]})
        fixtures = [(o[1], o[2]) for o in observed]
        blockers = fixture_identity_blockers(
            self.connection,
            [f[0] for f in fixtures],
            registered[0],
            provider_code=self.provider_code,
        )
        status = "COMPLETED"
        if (
            counts.unmatched
            or len({o[0] for o in observed}) < len(rows)
            or any(f[1] != "VERIFIED" for f in fixtures)
            or any(blockers.values())
        ):
            status = "BLOCKED_IDENTITY"
        elif any(row.result_score_basis != "REGULATION_90" for row in results):
            status = "BLOCKED_SCORE_BASIS"
        elif any(o[4] for o in observed):
            status = "BLOCKED_RESULT_CONFLICT"
        elif count < len(results):
            status = "BLOCKED_HISTORY_ADMISSION"
        return {"status": status, "qualified_results": count, "provider_results": len(results)}

    def _usable_provider_season_label(
        self,
        row: FixtureObservation,
        snapshot_id: UUID,
        season_label: str | None,
        metadata: Sequence[Any] | None = None,
    ) -> str | None:
        normalized = season_label.strip() if season_label is not None else ""
        reason_code = None
        reason = None
        evidence: dict[str, Any] = {"provider_competition_id": row.provider_competition_id}
        if row.provider_competition_name is None:
            reason_code = "PROVIDER_COMPETITION_NAME_UNAVAILABLE"
            reason = "provider competition name unavailable"
        elif normalized.casefold() in {"", "unknown"}:
            reason_code = "PROVIDER_SEASON_UNAVAILABLE"
            reason = "provider season label unavailable"
            evidence["season_label"] = season_label
            evidence["kickoff_at"] = row.kickoff_at.isoformat()
        elif (
            metadata is not None
            and metadata[1] == "PROVISIONAL"
            and str(metadata[0]).strip().casefold() == "unknown"
        ):
            reason_code = "PROVISIONAL_COMPETITION_SEASON_CONFLICT"
            reason = "provisional competition season conflicts with the source season"
            evidence["stored_season_label"] = metadata[0]
            evidence["source_season_label"] = normalized
        if reason is not None:
            self._record_mapping_decision(
                row,
                snapshot_id,
                None,
                "REVIEW_REQUIRED",
                reason,
                {"reason_code": reason_code, **evidence},
            )
            return None
        return normalized

    def _fixture_identity_is_verified(
        self,
        row: FixtureObservation,
        competition_id: UUID,
        metadata: Sequence[Any] | None,
        season_label: str,
        home_id: UUID,
        away_id: UUID,
    ) -> bool:
        return (
            metadata is not None
            and metadata[1] == "VERIFIED"
            and competition_id
            != stable_id(
                "provider-scoped-competition", self.provider_code, row.provider_competition_id
            )
            and season_label != "Unknown"
            and home_id
            != stable_id("provider-scoped-team", self.provider_code, row.provider_home_team_id)
            and away_id
            != stable_id("provider-scoped-team", self.provider_code, row.provider_away_team_id)
        )

    def _canonical_crosswalk_season_label(
        self,
        row: FixtureObservation,
        metadata: Sequence[Any] | None,
        season_label: str,
    ) -> str:
        crosswalk = OPERATIONAL_COMPETITION_CROSSWALKS.get(
            (self.provider_code, row.provider_competition_id)
        )
        if (
            metadata is None
            or metadata[1] != "VERIFIED"
            or crosswalk is None
            or crosswalk[0] != "api_football"
            or not re.fullmatch(r"\d{4}/\d{4}", season_label)
        ):
            return season_label
        start, end = (int(year) for year in season_label.split("/"))
        if end != start + 1:
            raise ValueError("crosswalk league season years must be consecutive")
        return str(start)

    def _set_verified_league_season(
        self, row: FixtureObservation, fixture_id: UUID, season_label: str
    ) -> None:
        crosswalk = OPERATIONAL_COMPETITION_CROSSWALKS.get(
            (self.provider_code, row.provider_competition_id)
        )
        if crosswalk is None or crosswalk[0] != "api_football":
            return
        from football.product.provider_history_scopes import normalize_seasons

        years = normalize_seasons([season_label])[0].split(" - ", 1)[0].split("/")
        start = int(years[0])
        if len(years) == 2 and int(years[1]) != start + 1:
            raise ValueError("crosswalk league season years must be consecutive")
        with self.connection.cursor() as cursor:
            fixture = cursor.execute(
                """SELECT competition_id FROM football.product_fixtures
                   WHERE fixture_id = %s AND identity_status = 'VERIFIED'""",
                (fixture_id,),
            ).fetchone()
            if fixture is None:
                return
            season_id = self._reviewed_league_season(
                row.provider_competition_id, season_label, fixture[0]
            )
            if season_id is None:
                if " - " in season_label:
                    return
                season_id = stable_id("season", fixture[0], start)
            cursor.execute(
                "INSERT INTO football.seasons (id, competition_id) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (season_id, fixture[0]),
            )
            cursor.execute(
                "UPDATE football.matches SET season_id = %s WHERE id = %s",
                (season_id, fixture_id),
            )

    def _reviewed_league_season(
        self, competition: str, label: str, canonical_competition: UUID
    ) -> UUID | None:
        """Use only the exact prospectively reviewed native label; never extrapolate years."""
        mappings = self.connection.execute(
            """SELECT mapping.provider_season_id, mapping.season_id,
                      season.competition_id, mapping.mapping_confidence,
                      mapping.mapping_method, snapshot.status
               FROM football.season_provider_mappings mapping
               JOIN football.providers provider ON provider.id = mapping.provider_id
               JOIN football.seasons season ON season.id = mapping.season_id
               JOIN football.source_snapshots snapshot ON snapshot.id = mapping.source_snapshot_id
               WHERE provider.code = %s AND mapping.provider_competition_id = %s
                 AND mapping.valid_to IS NULL AND mapping.created_at <= clock_timestamp()
                 AND (mapping.valid_from IS NULL OR mapping.valid_from <= clock_timestamp())""",
            (self.provider_code, competition),
        ).fetchall()
        if not mappings:
            return None
        for native_label, season, target, confidence, method, status in mappings:
            if native_label != label:
                continue
            if (
                target != canonical_competition
                or confidence != 1
                or method != "manual"
                or status != "validated"
            ):
                raise ValueError("provider season correspondence is not independently reviewed")
            return cast(UUID, season)
        raise ValueError("explicit provider season correspondence required for this label")
