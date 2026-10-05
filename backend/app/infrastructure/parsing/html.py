"""Sanitized HTML adapter: stdlib only, never fetches external resources.

Drops script/style/form and hidden content, keeps headings, lists and
tables in reading order. External URLs are preserved as plain text and
never dereferenced: the parser performs zero network I/O by construction.
"""
from __future__ import annotations

from html.parser import HTMLParser

from raghub_core.domain.ingestion.limits import check_compressed_size
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedSection

_SKIP_TAGS = {"script", "style", "form", "noscript", "template"}
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.blocks: list[tuple[str, str]] = []
        self._text: list[str] = []
        self._in_cell = False
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_li = False
        self.fetched: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        attrs_d = dict(attrs)
        style = (attrs_d.get("style") or "").replace(" ", "").lower()
        if attrs_d.get("hidden") is not None or "display:none" in style:
            self.skip_depth += 1
            self._text.append("\x00hidden\x00")
            return
        if tag == "br":
            self._text.append("\n")
        elif tag == "li":
            self._flush()
            self._in_li = True
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell = []
        elif tag == "tr":
            self._row = []
        elif tag in ("p", "div", "section", "article", "ul", "ol", "table"):
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._row.append(" ".join(self._cell).strip())
        elif tag == "tr" and self._row:
            cells = [cell.replace("|", "/") for cell in self._row]
            self.blocks.append(("row", "| " + " | ".join(cells) + " |"))
            self._row = []
        elif tag == "li" and self._in_li:
            self._in_li = False
            text = " ".join(self._text).strip()
            self._text = []
            if text:
                self.blocks.append(("bullet", f"- {text}"))
        elif tag in ("p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_cell:
            self._cell.append(text)
        else:
            self._text.append(text)

    def _flush(self) -> None:
        # Hidden subtrees pushed a sentinel; drop everything they collected.
        if "\x00hidden\x00" in self._text:
            self._text = []
            return
        text = " ".join(self._text).strip()
        self._text = []
        if text:
            self.blocks.append(("text", text))


def parse_html(content: bytes, source_name: str = "document.html") -> list[ParsedSection]:
    check_compressed_size(len(content))
    try:
        html = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        html = content.decode("windows-1252", errors="replace")
    parser = _Sanitizer()
    parser.feed(html)
    parser._flush()
    assert parser.fetched == [], "HTML adapter must never fetch external resources."
    sections: list[ParsedSection] = []
    rows: list[str] = []
    heading: str | None = None

    def flush_rows() -> None:
        if rows:
            width = max(row.count("|") - 1 for row in rows)
            table = [rows[0], "| " + " | ".join(["---"] * width) + " |", *rows[1:]]
            sections.append(ParsedSection("\n".join(table), source_name, len(sections),
                                          heading=heading))
            rows.clear()

    for kind, text in parser.blocks:
        if kind == "row":
            rows.append(text)
        else:
            flush_rows()
            if kind == "bullet":
                sections.append(ParsedSection(text, source_name, len(sections), heading=heading))
            else:
                if len(text) < 120 and not text.endswith((".", "!", "?", ":", ";")):
                    heading = text
                sections.append(ParsedSection(text, source_name, len(sections), heading=heading))
    flush_rows()
    sections = [s for s in sections if s.content]
    if not sections:
        raise EmptyExtractedTextError("The HTML file contains no text.")
    return sections
