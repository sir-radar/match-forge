"""Explicit entity identifiers shared by supported product providers."""

from __future__ import annotations

# Explicit cross-provider competition mapping. No fuzzy competition matching is permitted.
FOOTBALL_DATA_COMPETITIONS = {
    1: "WC",
    2: "CL",
    4: "EC",
    13: "CLI",
    39: "PL",
    40: "ELC",
    61: "FL1",
    71: "BSA",
    78: "BL1",
    88: "DED",
    94: "PPL",
    135: "SA",
    140: "PD",
}

COMPETITION_CROSSWALKS: dict[str, dict[str, tuple[str, str]]] = {
    "football_data_org": {
        code: ("api_football", str(identifier))
        for identifier, code in FOOTBALL_DATA_COMPETITIONS.items()
    },
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

OPERATIONAL_TEAM_CROSSWALKS: dict[tuple[str, str], tuple[str, str]] = {
    ("fotmob", "9825"): ("api_football", "42"),  # Arsenal
    ("fotmob", "10252"): ("api_football", "66"),  # Aston Villa
    ("fotmob", "8678"): ("api_football", "35"),  # Bournemouth
    ("fotmob", "9937"): ("api_football", "55"),  # Brentford
    ("fotmob", "10204"): ("api_football", "51"),  # Brighton
    ("fotmob", "8455"): ("api_football", "49"),  # Chelsea
    ("fotmob", "9826"): ("api_football", "52"),  # Crystal Palace
    ("fotmob", "8668"): ("api_football", "45"),  # Everton
    ("fotmob", "9879"): ("api_football", "36"),  # Fulham
    ("fotmob", "8667"): ("api_football", "64"),  # Hull City
    ("fotmob", "9902"): ("api_football", "57"),  # Ipswich
    ("fotmob", "8463"): ("api_football", "63"),  # Leeds
    ("fotmob", "8650"): ("api_football", "40"),  # Liverpool
    ("fotmob", "8456"): ("api_football", "50"),  # Manchester City
    ("fotmob", "10260"): ("api_football", "33"),  # Manchester United
    ("fotmob", "10203"): ("api_football", "65"),  # Nottingham Forest
    ("fotmob", "8472"): ("api_football", "746"),  # Sunderland
    ("fotmob", "8586"): ("api_football", "47"),  # Tottenham
    ("football_data_org", "354"): ("api_football", "52"),  # Crystal Palace
    ("football_data_org", "351"): ("api_football", "65"),  # Nottingham Forest
    ("football_data_org", "322"): ("api_football", "64"),  # Hull City
    ("football_data_org", "62"): ("api_football", "45"),  # Everton
    ("football_data_org", "64"): ("api_football", "40"),  # Liverpool
    ("football_data_org", "65"): ("api_football", "50"),  # Manchester City
    ("football_data_org", "57"): ("api_football", "42"),  # Arsenal
    ("football_data_org", "58"): ("api_football", "66"),  # Aston Villa
    ("football_data_org", "1044"): ("api_football", "35"),  # Bournemouth
    ("football_data_org", "402"): ("api_football", "55"),  # Brentford
    ("football_data_org", "397"): ("api_football", "51"),  # Brighton
    ("football_data_org", "61"): ("api_football", "49"),  # Chelsea
    ("football_data_org", "63"): ("api_football", "36"),  # Fulham
    ("football_data_org", "349"): ("api_football", "57"),  # Ipswich
    ("football_data_org", "341"): ("api_football", "63"),  # Leeds
    ("football_data_org", "66"): ("api_football", "33"),  # Manchester United
    ("football_data_org", "71"): ("api_football", "746"),  # Sunderland
    ("football_data_org", "73"): ("api_football", "47"),  # Tottenham
}

# Operational only: never changes historical training identity construction.
OPERATIONAL_COMPETITION_CROSSWALKS = {
    ("fotmob", "47"): ("api_football", "39", "Premier League", "ENG"),
    ("fotmob", "53"): ("api_football", "61", "Ligue 1", "FRA"),
    ("fotmob", "54"): ("api_football", "78", "Bundesliga", "GER"),
    ("fotmob", "55"): ("api_football", "135", "Serie A", "ITA"),
    ("fotmob", "59"): ("api_football", "103", "Eliteserien", "NOR"),
    ("fotmob", "61"): ("api_football", "94", "Liga Portugal", "POR"),
    ("fotmob", "71"): ("api_football", "203", "Super Lig", "TUR"),
    ("fotmob", "87"): ("api_football", "140", "LaLiga", "ESP"),
    ("fotmob", "110"): ("api_football", "62", "Ligue 2", "FRA"),
    ("fotmob", "111"): ("api_football", "89", "Eerste Divisie", "NED"),
    ("fotmob", "118"): ("api_football", "342", "Premier League", "ARM"),
    ("fotmob", "126"): ("api_football", "357", "Premier Division", "IRL"),
    ("fotmob", "146"): ("api_football", "79", "2. Bundesliga", "GER"),
    ("fotmob", "168"): ("api_football", "114", "Superettan", "SWE"),
    ("fotmob", "173"): ("api_football", "373", "Prva Liga", "SVN"),
    ("fotmob", "185"): ("api_football", "95", "Liga Portugal 2", "POR"),
    ("fotmob", "197"): ("api_football", "107", "I Liga", "POL"),
    ("fotmob", "203"): ("api_football", "104", "1. Divisjon", "NOR"),
    ("fotmob", "208"): ("api_football", "80", "3. Liga", "GER"),
    ("fotmob", "212"): ("api_football", "271", "NB I", "HUN"),
    ("fotmob", "219"): ("api_football", "359", "FAI Cup", "IRL"),
    ("fotmob", "229"): ("api_football", "261", "National Division", "LUX"),
    ("fotmob", "232"): ("api_football", "355", "1. CFL", "MNE"),
    ("fotmob", "250"): ("api_football", "367", "Premier League", "FRO"),
    ("fotmob", "252"): ("api_football", "210", "HNL", "CRO"),
    ("fotmob", "439"): ("api_football", "327", "Erovnuli Liga", "GEO"),
    ("fotmob", "516"): ("api_football", "186", "Ligue 1", "ALG"),
    ("fotmob", "522"): ("api_football", "570", "Premier League", "GHA"),
    ("fotmob", "530"): ("api_football", "200", "Botola Pro", "MAR"),
    ("fotmob", "8935"): ("api_football", "109", "II Liga", "POL"),
    ("fotmob", "8970"): ("api_football", "63", "Ligue 3", "FRA"),
    ("fotmob", "8972"): ("api_football", "255", "USL Championship", "USA"),
    ("fotmob", "8983"): ("api_football", "274", "Super League", "IDN"),
    ("fotmob", "9066"): ("api_football", "567", "Premier League", "TAN"),
    ("fotmob", "9096"): ("api_football", "173", "Second Professional League", "BUL"),
    ("fotmob", "9117"): ("api_football", "272", "NB II", "HUN"),
    ("fotmob", "9136"): ("api_football", "100", "J. League 3", "JPN"),
    ("fotmob", "9195"): ("api_football", "492", "Tweede Divisie", "NED"),
    ("fotmob", "9372"): ("api_football", "291", "Azadegan League", "IRN"),
    ("fotmob", "9471"): ("api_football", "874", "Australia Cup", "AUS"),
    ("fotmob", "9676"): ("api_football", "82", "Frauen-Bundesliga", "GER"),
    ("fotmob", "10186"): ("api_football", "640", "Kansallinen Liiga Qualification Group", "FIN"),
    ("pitchapi", "l_4WFCIZ"): ("api_football", "39", "Premier League", "ENG"),
}


def canonical_team_provider_identity(
    provider_code: str, provider_team_id: str
) -> tuple[str, str] | None:
    return TEAM_CROSSWALKS.get((provider_code, provider_team_id))
