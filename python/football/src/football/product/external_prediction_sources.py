"""Public external-prediction adapters for the private local MVP."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from football.product.domain import map_external_market
from football.product.external_predictions import ImportedPrediction

FetchPage = Callable[[str], str]
Parser = Callable[[str, date, str], tuple[ImportedPrediction, ...]]


class ParserBrokenError(ValueError):
    """The public page loaded but no longer matches its adapter contract."""


@dataclass(slots=True)
class Element:
    tag: str
    attrs: dict[str, str]
    children: list[Element] = field(default_factory=list)
    data: list[str] = field(default_factory=list)


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, {name: value or "" for name, value in attrs})
        self.stack[-1].children.append(element)
        if tag not in {"area", "base", "br", "embed", "hr", "img", "input", "link", "meta"}:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].data.append(data)


@dataclass(frozen=True, slots=True)
class SourceCollection:
    source_code: str
    source_page: str
    status: str
    rows: tuple[ImportedPrediction, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SourceAdapter:
    source_code: str
    page_url: Callable[[date, date], str | None]
    parser: Parser


def _tree(value: str) -> Element:
    parser = _TreeBuilder()
    parser.feed(value)
    parser.close()
    return parser.root


def _walk(element: Element) -> Iterator[Element]:
    for child in element.children:
        yield child
        yield from _walk(child)


def _has_class(element: Element, name: str) -> bool:
    return name in element.attrs.get("class", "").split()


def _elements(
    element: Element, *, tag: str | None = None, class_name: str | None = None
) -> list[Element]:
    return [
        item
        for item in _walk(element)
        if (tag is None or item.tag == tag) and (class_name is None or _has_class(item, class_name))
    ]


def _text(element: Element) -> str:
    values = list(element.data)
    for child in element.children:
        values.append(_text(child))
    return " ".join(" ".join(values).replace("\xa0", " ").split())


def _own_text(element: Element) -> str:
    return " ".join(" ".join(element.data).replace("\xa0", " ").split())


def _first(
    element: Element, *, tag: str | None = None, class_name: str | None = None
) -> Element | None:
    return next(iter(_elements(element, tag=tag, class_name=class_name)), None)


def _mapped_prediction(
    *,
    source_page: str,
    prediction_date: date,
    original_date_text: str,
    competition: str,
    home_team: str,
    away_team: str,
    raw_selection: str,
    unmapped_market: str = "UNMAPPED",
) -> ImportedPrediction | None:
    selection_text = raw_selection.strip()
    if not selection_text:
        return None
    mapped = map_external_market(raw_selection)
    if mapped is None:
        market, selection = unmapped_market, selection_text
    else:
        market, selection = mapped
    return ImportedPrediction(
        source_page=source_page,
        prediction_date=prediction_date,
        original_date_text=original_date_text,
        competition=competition,
        home_team=home_team,
        away_team=away_team,
        market=market,
        selection=selection,
    )


def _split_fixture(value: str) -> tuple[str, str] | None:
    parts = re.split(r"\s+vs\.?\s+", value.strip(), maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def parse_r2bet(
    html: str, prediction_date: date, source_page: str
) -> tuple[ImportedPrediction, ...]:
    root = _tree(html)
    date_text = next(
        (
            _text(item)
            for item in _elements(root, tag="p")
            if re.search(r"\d{1,2}(?:st|nd|rd|th)\s*,\s*\w{3}\s+\w{3}\s+\d{4}", _text(item))
        ),
        None,
    )
    if date_text is None or prediction_date.strftime("%b %Y") not in date_text:
        raise ParserBrokenError("R2Bet prediction date was not found")
    rows: list[ImportedPrediction] = []
    for article in _elements(root, tag="article"):
        values = [_text(item) for item in _elements(article, tag="p")]
        pick_index = next(
            (index for index, value in enumerate(values) if value.startswith("Pick:")), None
        )
        odds_index = next(
            (index for index, value in enumerate(values) if value.startswith("Odds:")), None
        )
        if pick_index is None or odds_index is None or odds_index < 2:
            continue
        row = _mapped_prediction(
            source_page=source_page,
            prediction_date=prediction_date,
            original_date_text=date_text,
            competition=values[0],
            home_team=values[odds_index - 2],
            away_team=values[odds_index - 1],
            raw_selection=values[pick_index].removeprefix("Pick:").strip(),
        )
        if row is not None:
            rows.append(row)
    return tuple(rows)


def parse_1960tips(
    html: str, prediction_date: date, source_page: str
) -> tuple[ImportedPrediction, ...]:
    root = _tree(html)
    heading = next(
        (_text(item) for item in _elements(root, tag="h1") if "Predictions" in _text(item)), None
    )
    expected = prediction_date.strftime("%-d %b %Y")
    if heading is None or expected not in heading:
        raise ParserBrokenError("1960Tips prediction date was not found")
    rows: list[ImportedPrediction] = []
    for item in _elements(root, class_name="table-row"):
        competition = _first(item, class_name="tb-league")
        match = _first(item, class_name="tb-match")
        tip = _first(item, class_name="tb-tip")
        if competition is None or match is None or tip is None:
            continue
        fixture = _split_fixture(_text(match))
        if fixture is None:
            continue
        row = _mapped_prediction(
            source_page=source_page,
            prediction_date=prediction_date,
            original_date_text=heading,
            competition=_text(competition),
            home_team=fixture[0],
            away_team=fixture[1],
            raw_selection=_text(tip),
        )
        if row is not None:
            rows.append(row)
    return tuple(rows)


def parse_slybet(
    html: str, prediction_date: date, source_page: str
) -> tuple[ImportedPrediction, ...]:
    root = _tree(html)
    expected = prediction_date.strftime("%d.%m.%y")
    table = next(
        (
            item
            for item in _elements(root, tag="table", class_name="smp-picks-table")
            if any(_text(header) == expected for header in _elements(item, tag="th"))
        ),
        None,
    )
    if table is None:
        raise ParserBrokenError("SlyBet prediction date was not found")
    rows: list[ImportedPrediction] = []
    for item in _elements(table, tag="tr"):
        home = _first(item, class_name="smp-team1")
        away = _first(item, class_name="smp-team2")
        if home is None or away is None:
            continue
        date_cell = _first(item, class_name="smp-col-date")
        flag = _first(date_cell, tag="img") if date_cell is not None else None
        competition = flag.attrs.get("alt", "Unknown") if flag is not None else "Unknown"
        raw_values = (
            (
                "RESULT_1X2",
                _text(_first(item, class_name="smp-col-1x2") or Element("td", {})),
            ),
            (
                "TOTAL_GOALS",
                _slybet_total(_text(_first(item, class_name="smp-col-ou") or Element("td", {}))),
            ),
            (
                "BTTS",
                _slybet_btts(_text(_first(item, class_name="smp-col-btts") or Element("td", {}))),
            ),
        )
        for unmapped_market, raw_selection in raw_values:
            row = _mapped_prediction(
                source_page=source_page,
                prediction_date=prediction_date,
                original_date_text=expected,
                competition=competition,
                home_team=_text(home),
                away_team=_text(away),
                raw_selection=raw_selection,
                unmapped_market=unmapped_market,
            )
            if row is not None:
                rows.append(row)
    return tuple(rows)


def _slybet_total(value: str) -> str:
    return {"+2.5": "Over 2.5", "-2.5": "Under 2.5"}.get(value, value)


def _slybet_btts(value: str) -> str:
    return "BTTS" if value.casefold() in {"yes", "gg", "btts"} else value


def parse_matchoutlook(
    html: str, prediction_date: date, source_page: str
) -> tuple[ImportedPrediction, ...]:
    root = _tree(html)
    section_id, title = _matchoutlook_section(source_page)
    heading = next(
        (_text(item) for item in _elements(root, tag="h1") if title in _text(item)), None
    )
    section = next((item for item in _walk(root) if item.attrs.get("id") == section_id), None)
    if heading is None or section is None:
        raise ParserBrokenError("MatchOutlook prediction section was not found")
    rows: list[ImportedPrediction] = []
    for item in _elements(section, class_name="match-section"):
        title_element = _first(item, class_name="match-title")
        content = _first(item, class_name="match-content")
        if title_element is None or content is None:
            continue
        direct_bold = [child for child in content.children if child.tag == "b"]
        versus = next(
            (index for index, child in enumerate(direct_bold) if _text(child).casefold() == "vs"),
            None,
        )
        bet = next((child for child in direct_bold if _has_class(child, "our-bet")), None)
        if versus is None or versus == 0 or versus + 1 >= len(direct_bold) or bet is None:
            continue
        selection = _text(bet).removeprefix("Best Bet:").strip()
        row = _mapped_prediction(
            source_page=source_page,
            prediction_date=prediction_date,
            original_date_text=heading,
            competition=_own_text(title_element),
            home_team=_text(direct_bold[versus - 1]),
            away_team=_text(direct_bold[versus + 1]),
            raw_selection=selection,
        )
        if row is not None:
            rows.append(row)
    return tuple(rows)


def _matchoutlook_section(source_page: str) -> tuple[str, str]:
    if "yesterdays-" in source_page:
        return "yesterday-div", "Yesterday's Football Predictions"
    if "tomorrows-" in source_page:
        return "tomorrow-div", "Tomorrow's Football Predictions"
    return "today-div", "Today's Football Predictions"


def fetch_page(url: str) -> str:
    request = Request(url, headers={"User-Agent": "MatchForge/1.0 (private-local-analysis)"})
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload: bytes = response.read()
        return payload.decode(charset, errors="replace")


def collect_sources(
    prediction_date: date,
    *,
    requested_source: str | None = None,
    fetcher: FetchPage = fetch_page,
    today: date | None = None,
) -> tuple[SourceCollection, ...]:
    current_date = today or date.today()
    if requested_source is not None and requested_source not in _KNOWN_SOURCES:
        raise ValueError(f"unknown external prediction source: {requested_source}")
    results: list[SourceCollection] = []
    for adapter in _ADAPTERS:
        if requested_source is not None and adapter.source_code != requested_source:
            continue
        results.append(_collect_source(adapter, prediction_date, current_date, fetcher))
    if requested_source in {None, "forebet"}:
        results.append(
            SourceCollection(
                source_code="forebet",
                source_page="https://www.forebet.com/en/football-predictions",
                status="TECHNICALLY_UNAVAILABLE",
                error="Managed anti-bot challenge returned HTTP 403; no circumvention attempted.",
            )
        )
    return tuple(results)


def _collect_source(
    adapter: SourceAdapter, prediction_date: date, today: date, fetcher: FetchPage
) -> SourceCollection:
    source_page = adapter.page_url(prediction_date, today)
    if source_page is None:
        return SourceCollection(adapter.source_code, "", "NO_DATE_PAGE")
    try:
        rows = adapter.parser(fetcher(source_page), prediction_date, source_page)
    except ParserBrokenError as error:
        return SourceCollection(adapter.source_code, source_page, "PARSER_BROKEN", error=str(error))
    except OSError as error:
        return SourceCollection(
            adapter.source_code, source_page, "TECHNICALLY_UNAVAILABLE", error=str(error)
        )
    return SourceCollection(
        adapter.source_code,
        source_page,
        "ENABLED" if rows else "NO_PREDICTIONS",
        rows=rows,
    )


def _relative_page(
    prediction_date: date, today: date, *, base: str, paths: tuple[str, str, str]
) -> str | None:
    offset = (prediction_date - today).days
    if offset not in {-1, 0, 1}:
        return None
    return f"{base}/{paths[offset + 1]}"


_ADAPTERS = (
    SourceAdapter(
        "r2bet",
        lambda target, _: (
            "https://r2bet.com/index.php/best_football_prediction?dt=" + target.isoformat()
        ),
        parse_r2bet,
    ),
    SourceAdapter(
        "tips1960",
        lambda target, today: _relative_page(
            target,
            today,
            base="https://www.1960tips.com",
            paths=("yesterdays-predictions", "todays-predictions", "tomorrows-predictions"),
        ),
        parse_1960tips,
    ),
    SourceAdapter(
        "slybet",
        lambda target, today: (
            "https://slybet.net/football-predictions/"
            if target == today + timedelta(days=1)
            else "https://slybet.net/"
        ),
        parse_slybet,
    ),
    SourceAdapter(
        "matchoutlook",
        lambda target, today: _relative_page(
            target,
            today,
            base="https://www.matchoutlook.com",
            paths=(
                "yesterdays-football-predictions/",
                "todays-football-predictions",
                "tomorrows-football-predictions/",
            ),
        ),
        parse_matchoutlook,
    ),
)
_KNOWN_SOURCES = frozenset(adapter.source_code for adapter in _ADAPTERS) | {"forebet"}
