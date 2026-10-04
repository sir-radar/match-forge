"""Verified cross-provider team identities used by product history ingestion."""

from __future__ import annotations

from typing import Final

ProviderTeamIdentity = tuple[str, str]

# Every entry maps a provider identity to the canonical product identity. These
# are explicit provider-ID decisions; names are never used to infer identity.
TEAM_PROVIDER_CROSSWALKS: Final[dict[ProviderTeamIdentity, ProviderTeamIdentity]] = {
    ("openfootball", "Hull City"): ("football_data_org", "322"),
    ("openfootball", "Hull City AFC"): ("football_data_org", "322"),
    ("football_data_uk", "Hull"): ("football_data_org", "322"),
    ("openfootball", "Ipswich Town"): ("football_data_org", "349"),
    ("openfootball", "Ipswich Town FC"): ("football_data_org", "349"),
    ("football_data_uk", "Ipswich"): ("football_data_org", "349"),
    ("football_data_uk", "Cordoba"): ("api_football", "713"),
    ("football_data_uk", "Girona"): ("api_football", "547"),
    ("football_data_uk", "Granada"): ("api_football", "715"),
    ("football_data_uk", "Las Palmas"): ("api_football", "534"),
    ("football_data_uk", "Mallorca"): ("api_football", "798"),
    ("football_data_uk", "Tenerife"): ("api_football", "719"),
    ("football_data_uk", "Valladolid"): ("api_football", "720"),
    ("openfootball", "Real Sociedad B"): ("api_football", "9585"),
    ("football_data_uk", "Sociedad B"): ("api_football", "9585"),
    ("football_data_uk", "Sp Gijon"): ("api_football", "731"),
    ("football_data_uk", "Celta B"): ("api_football", "9571"),
    ("openfootball", "CD Castellón"): ("api_football", "5254"),
    ("football_data_uk", "Castellon"): ("api_football", "5254"),
    ("openfootball", "AD Ceuta FC"): ("api_football", "10139"),
    ("football_data_uk", "Ceuta"): ("api_football", "10139"),
}


def canonical_team_provider_identity(
    provider_code: str, provider_team_id: str
) -> ProviderTeamIdentity | None:
    return TEAM_PROVIDER_CROSSWALKS.get((provider_code, provider_team_id))
