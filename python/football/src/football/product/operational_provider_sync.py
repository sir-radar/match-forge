"""Idempotent operational fixture sync for FotMob and PitchAPI."""

from __future__ import annotations

from datetime import date

from football.product.operational_details import OperationalDetailMixin
from football.product.operational_reviewed import OperationalReviewedMappingMixin
from football.product.operational_support import FixtureObservation

__all__ = ["FixtureObservation", "OperationalProviderSync"]
from football.providers.fotmob import (
    FotmobClient,
    normalize_daily_matches,
)
from football.providers.pitchapi import (
    PitchApiClient,
    normalize_pitchapi_matches,
)


class OperationalProviderSync(OperationalReviewedMappingMixin, OperationalDetailMixin):
    def sync_fotmob(
        self,
        client: FotmobClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        live_details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=client.matches_by_date,
            normalize=normalize_daily_matches,
            detail=lambda item: self._fotmob_details(client, item),
            details_limit=details_limit,
            live_details_limit=live_details_limit,
            competition_id=competition_id,
        )

    def sync_pitchapi(
        self,
        client: PitchApiClient,
        from_date: date,
        through_date: date,
        *,
        details_limit: int = 10,
        live_details_limit: int = 10,
        competition_id: str | None = None,
    ) -> dict[str, object]:
        return self._sync_dates(
            from_date,
            through_date,
            fetch=lambda day: client.matches_by_date(day, status="all"),
            normalize=normalize_pitchapi_matches,
            detail=lambda item: self._pitchapi_details(client, item),
            details_limit=details_limit,
            live_details_limit=live_details_limit,
            competition_id=competition_id,
        )
