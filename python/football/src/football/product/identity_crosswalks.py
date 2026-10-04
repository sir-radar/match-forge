"""Explicit entity identifiers shared by supported product providers."""

from __future__ import annotations

COMPETITION_CROSSWALKS: dict[str, dict[str, tuple[str, str]]] = {
    "openfootball": {
        "br.1": ("api_football", "71"),
        "ch.1": ("api_football", "207"),
        "de.1": ("api_football", "78"),
        "de.cup": ("api_football", "81"),
        "en.1": ("api_football", "39"),
        "en.2": ("api_football", "40"),
        "en.3": ("api_football", "41"),
        "en.4": ("api_football", "42"),
        "es.1": ("api_football", "140"),
        "fr.1": ("api_football", "61"),
        "fr.2": ("api_football", "62"),
        "it.1": ("api_football", "135"),
        "it.2": ("api_football", "136"),
        "mls": ("api_football", "253"),
        "mx.1": ("api_football", "262"),
        "nl.1": ("api_football", "88"),
        "pt.1": ("api_football", "94"),
        "sco.1": ("api_football", "179"),
        "tr.1": ("api_football", "203"),
        "uefa.cl": ("api_football", "2"),
    },
    "football_data_uk": {
        "B1": ("api_football", "144"),
        "D1": ("api_football", "78"),
        "D2": ("api_football", "79"),
        "E0": ("api_football", "39"),
        "E1": ("api_football", "40"),
        "E2": ("api_football", "41"),
        "E3": ("api_football", "42"),
        "EC": ("api_football", "43"),
        "F1": ("api_football", "61"),
        "F2": ("api_football", "62"),
        "G1": ("api_football", "197"),
        "I1": ("api_football", "135"),
        "I2": ("api_football", "136"),
        "N1": ("api_football", "88"),
        "P1": ("api_football", "94"),
        "SC0": ("api_football", "179"),
        "SC1": ("api_football", "180"),
        "SC2": ("api_football", "183"),
        "SC3": ("api_football", "184"),
        "SP1": ("api_football", "140"),
        "SP2": ("api_football", "141"),
        "T1": ("api_football", "203"),
    },
}

TEAM_CROSSWALKS: dict[tuple[str, str], tuple[str, str]] = {
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
) -> tuple[str, str] | None:
    return TEAM_CROSSWALKS.get((provider_code, provider_team_id))
