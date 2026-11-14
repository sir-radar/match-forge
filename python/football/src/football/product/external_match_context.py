"""Deterministic reading of the team and competition text an external source prints.

These helpers only describe source text. They never decide identity on their own:
the contextual matching policy combines them with the date and the fixture
catalogue, and requires exactly one fixture to survive.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from football.product.domain import normalize_team_name

NameRule = Literal["EXACT", "VARIANT"]
CompetitionRelation = Literal["MATCH", "COMPATIBLE", "UNKNOWN", "CONFLICT"]

# Club-form words that do not distinguish one club from another.
_AFFIXES = frozenset(
    {"fc", "cf", "afc", "sc", "club", "fk", "sk", "ac", "as", "cd", "ud", "sv", "if", "bk"}
    | {"nk", "ks", "sd", "ca", "cfc", "kv", "kfc", "calcio"}
)
_WOMEN = frozenset({"w", "women", "womens", "woman", "ladies", "fem", "femenino", "feminine"})
_RESERVE = frozenset({"ii", "reserve", "reserves", "res", "jong"})
_TOKEN_VARIANTS = {"utd": "united", "turkiye": "turkey", "czechia": "czech"}
# Different spellings of the same national side or club seen on supported sources.
_PHRASE_VARIANTS = {
    "czech republic": "czech",
    "fyr macedonia": "north macedonia",
    "macedonia": "north macedonia",
    "korea republic": "south korea",
    "united states": "usa",
    "cote d ivoire": "ivory coast",
    "bosnia and herzegovina": "bosnia",
}


@dataclass(frozen=True, slots=True)
class NameForm:
    """Distinguishing words of a team name, keeping source abbreviations visible."""

    core: tuple[tuple[str, bool], ...]
    markers: frozenset[str]
    canonical: str

    @property
    def words(self) -> tuple[str, ...]:
        return tuple(word for word, _ in self.core)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


@lru_cache(maxsize=65536)
def name_form(text: str) -> NameForm:
    tokens = [
        # A dotted number such as "1." is an ordinal, not an abbreviation.
        (match[1], bool(match[2]) and not match[1].isdigit())
        for match in re.finditer(r"([a-z0-9]+)(\.*)", fold(text).replace("&", " and "))
    ]
    markers: set[str] = set()
    core: list[tuple[str, bool]] = []
    index = 0
    while index < len(tokens):
        word, abbreviated = tokens[index]
        following = tokens[index + 1][0] if index + 1 < len(tokens) else ""
        if word in {"under", "u"} and following.isdigit():
            markers.add("U" + following)
            index += 1
        elif not abbreviated and (marker := _marker(word, index, len(tokens))):
            markers.add(marker)
        elif not (abbreviated or len(tokens) == 1) and _affix(word, index):
            pass
        else:
            core.append((_TOKEN_VARIANTS.get(word, word), abbreviated))
        index += 1
    return NameForm(_phrase_variant(tuple(core)), frozenset(markers), normalize_team_name(text))


def _marker(word: str, index: int, length: int) -> str:
    if word in _WOMEN:
        return "WOMEN"
    if re.fullmatch(r"u(1[5-9]|2[0-3])", word):
        return "U" + word[1:]
    if word in _RESERVE or (word == "b" and 0 < index == length - 1):
        return "RESERVE"
    return ""


def _affix(word: str, index: int) -> bool:
    return word in _AFFIXES or (word == "1" and index == 0)


def _phrase_variant(core: tuple[tuple[str, bool], ...]) -> tuple[tuple[str, bool], ...]:
    if any(abbreviated for _, abbreviated in core):
        return core
    replacement = _PHRASE_VARIANTS.get(" ".join(word for word, _ in core))
    return tuple((word, False) for word in replacement.split()) if replacement else core


def match_name(source: NameForm, team: NameForm) -> NameRule | None:
    """EXACT for equal names; VARIANT for abbreviations or omitted trailing words.

    Women's, youth and reserve markers must agree exactly, so a first team never
    matches its youth or women's side.
    """
    if source.markers != team.markers or not source.core or not team.core:
        return None
    if source.words == team.words or source.canonical == team.canonical:
        return "EXACT"
    if _aligned(source.core, team.core) or _aligned(team.core, source.core):
        return "VARIANT"
    return None


def _aligned(short: tuple[tuple[str, bool], ...], long: tuple[tuple[str, bool], ...]) -> bool:
    """Every short word matches a long word in order, and the first words correspond."""
    if len(short) > len(long):
        return False
    position = 0
    for index, (word, abbreviated) in enumerate(short):
        while position < len(long) and not _word_matches(word, abbreviated, long[position][0]):
            if index == 0:
                return False
            position += 1
        if position == len(long):
            return False
        position += 1
    return True


def _word_matches(word: str, abbreviated: bool, other: str) -> bool:
    return word == other or (abbreviated and other.startswith(word))


# Three-letter codes printed by supported sources (ISO 3166 alpha-3 and FIFA style).
_COUNTRY_CODES = {
    "AGO": "angola", "ARE": "united arab emirates", "ARG": "argentina", "ARM": "armenia",
    "AUT": "austria", "BEL": "belgium", "BGD": "bangladesh", "BGR": "bulgaria",
    "BHR": "bahrain", "BIH": "bosnia", "BOL": "bolivia", "BRA": "brazil", "BUL": "bulgaria",
    "CAN": "canada", "CHL": "chile", "CHN": "china", "COL": "colombia", "CRI": "costa rica",
    "CYP": "cyprus", "CZE": "czech", "DEN": "denmark", "DEU": "germany", "DNK": "denmark",
    "DZA": "algeria", "ECU": "ecuador", "EGY": "egypt", "ENG": "england", "ESP": "spain",
    "EST": "estonia", "FIN": "finland", "FRA": "france", "GER": "germany", "GRC": "greece",
    "GRE": "greece", "HOL": "netherlands", "HRV": "croatia", "IDN": "indonesia",
    "IRE": "ireland", "IRL": "ireland", "ISR": "israel", "ITA": "italy", "JPN": "japan",
    "KSA": "saudi arabia", "KWT": "kuwait", "LVA": "latvia", "MEX": "mexico",
    "NGA": "nigeria", "NLD": "netherlands", "NOR": "norway", "POL": "poland",
    "POR": "portugal", "PRT": "portugal", "PRY": "paraguay", "QAT": "qatar",
    "ROU": "romania", "RUS": "russia", "SAU": "saudi arabia", "SCO": "scotland",
    "SRB": "serbia", "SUI": "switzerland", "SVK": "slovakia", "SWE": "sweden",
    "TUR": "turkey", "TZA": "tanzania", "UKR": "ukraine", "UZB": "uzbekistan",
    "VIE": "vietnam", "WAL": "wales",
}  # fmt: skip
_COUNTRY_VARIANTS = {
    "czech republic": "czech",
    "turkiye": "turkey",
    "holland": "netherlands",
    "bosnia and herzegovina": "bosnia",
    "united states": "usa",
    "korea republic": "south korea",
}
_INTERNATIONAL = frozenset(
    {"uefa", "afc", "caf", "concacaf", "conmebol", "fifa", "international", "world"}
    | {"europe", "euro", "africa", "asean", "friendlies", "saff"}
)
_INTERNATIONAL_COUNTRIES = frozenset({"world", "international"})
_CUP_WORDS = frozenset(
    {"cup", "cupen", "kupa", "kupasi", "pokal", "pokalen", "beker", "coppa", "copa", "taca"}
    | {"trophy", "shield"}
)
_UNKNOWN_TEXT = frozenset({"", "n a", "na", "unknown", "none"})


def country_key(value: str) -> str:
    folded = " ".join(re.findall(r"[a-z0-9]+", fold(value).replace("&", " and ")))
    return _COUNTRY_VARIANTS.get(folded, folded)


@dataclass(frozen=True, slots=True)
class CompetitionContext:
    known: bool
    country: str | None = None
    international: bool = False
    division: int | None = None
    cup: bool = False
    name: tuple[str, ...] = ()


def competition_context(text: str, countries: frozenset[str]) -> CompetitionContext:
    """Read country, tier and cup facts; free-text names never decide a conflict."""
    words = re.findall(r"[a-z0-9]+", fold(text).replace("&", " and "))
    if " ".join(words) in _UNKNOWN_TEXT:
        return CompetitionContext(known=False)
    country, rest = _leading_country(text, words, countries)
    international = country in _INTERNATIONAL_COUNTRIES or (
        country is None and words[0] in _INTERNATIONAL
    )
    division = re.fullmatch(r"d([1-9])", " ".join(rest))
    return CompetitionContext(
        known=True,
        country=None if international else country,
        international=international,
        division=int(division[1]) if division else None,
        cup=any(word in _CUP_WORDS for word in rest),
        name=tuple(rest),
    )


def _leading_country(
    text: str, words: list[str], countries: frozenset[str]
) -> tuple[str | None, list[str]]:
    code = re.match(r"\s*([A-Z]{3})\b", text)
    if code and code[1] in _COUNTRY_CODES:
        return _COUNTRY_CODES[code[1]], words[1:]
    for size in (3, 2, 1):
        candidate = country_key(" ".join(words[:size]))
        if len(words) >= size and candidate in countries:
            return candidate, words[size:]
    return None, words


def competition_relation(
    source: CompetitionContext,
    *,
    name: str,
    country: str,
    competition_type: str,
    division: int | None,
) -> CompetitionRelation:
    """Only structured facts (country, international, cup, tier) can conflict."""
    if not source.known:
        return "UNKNOWN"
    target = country_key(country)
    international = target in _INTERNATIONAL_COUNTRIES
    if _structured_conflict(source, target, international, competition_type, division):
        return "CONFLICT"
    target_name = tuple(re.findall(r"[a-z0-9]+", fold(name)))
    if source.name and (source.name == target_name or _contains(target_name, source.name)):
        return "MATCH"
    if source.country or source.international:
        return "COMPATIBLE"
    return "UNKNOWN"


def _structured_conflict(
    source: CompetitionContext,
    target: str,
    international: bool,
    competition_type: str,
    division: int | None,
) -> bool:
    if target == "unknown":
        return False
    if source.country is not None and (international or source.country != target):
        return True
    if source.international and not international:
        return True
    if source.cup and not international and competition_type == "LEAGUE":
        return True
    return source.division is not None and division is not None and source.division != division


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    size = len(needle)
    return any(haystack[index : index + size] == needle for index in range(len(haystack)))
