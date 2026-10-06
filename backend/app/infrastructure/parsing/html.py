"""Offline structural HTML extraction with nested hidden subtree removal."""

from html.parser import HTMLParser

from raghub_core.domain.ingestion.limits import check_compressed_size
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedBlock

_SKIP = {"script", "style", "form", "noscript", "template", "head"}
_VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.blocks = []
        self.text = []
        self.kind = "paragraph"
        self.row = []
        self.cell = None

    def flush(self):
        text = ("" if self.kind == "code" else " ").join(self.text).strip()
        self.text = []
        if text:
            self.blocks.append((self.kind, "- " + text if self.kind == "list" else text))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (self.stack and self.stack[-1][1]) or tag in _SKIP or "hidden" in attrs
        style = (attrs.get("style") or "").replace(" ", "").lower()
        hidden = bool(hidden or "display:none" in style or "visibility:hidden" in style)
        if tag not in _VOID:
            self.stack.append((tag, hidden))
        if hidden:
            return
        if tag in {"p", "div", "section", "article", "ul", "ol", "table", "li", "pre"} or tag in {
            f"h{i}" for i in range(1, 7)
        }:
            self.flush()
            self.kind = (
                tag
                if tag.startswith("h") and len(tag) == 2
                else "list"
                if tag == "li"
                else "code"
                if tag == "pre"
                else "paragraph"
            )
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"}:
            self.cell = []
        if tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        hidden = self.stack and self.stack[-1][1]
        if not hidden:
            if tag in {"td", "th"} and self.cell is not None:
                self.row.append(" ".join(self.cell).strip().replace("|", "/"))
                self.cell = None
            elif tag == "tr" and self.row:
                self.blocks.append(("row", "| " + " | ".join(self.row) + " |"))
                self.row = []
            elif tag in {"p", "div", "section", "article", "li", "table", "pre"} or tag in {
                f"h{i}" for i in range(1, 7)
            }:
                self.flush()
                if tag == "pre":
                    self.kind = "paragraph"
                if tag == "table":
                    self.blocks.append(("boundary", ""))
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1][1]:
            return
        if data.strip():
            (self.cell if self.cell is not None else self.text).append(
                data if self.kind == "code" else data.strip()
            )


def parse_html(content, source_name="document.html"):
    check_compressed_size(len(content))
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("windows-1252", errors="replace")
    parser = _Sanitizer()
    parser.feed(text)
    parser.flush()
    sections, path, rows = [], [], []

    def flush_rows():
        if rows:
            width = max(row.count("|") - 1 for row in rows)
            body = "\n".join([rows[0], "| " + " | ".join(["---"] * width) + " |", *rows[1:]])
            sections.append(
                ParsedBlock(
                    body,
                    source_name,
                    len(sections),
                    type="table",
                    heading=" / ".join(path) or None,
                    heading_path=tuple(path),
                )
            )
            rows.clear()

    for kind, text in parser.blocks:
        if kind == "row":
            rows.append(text)
            continue
        flush_rows()
        if kind == "boundary":
            continue
        if kind in {f"h{i}" for i in range(1, 7)}:
            path = path[: int(kind[1]) - 1] + [text]
            block_type = "heading"
        else:
            block_type = kind
        sections.append(
            ParsedBlock(
                text,
                source_name,
                len(sections),
                type=block_type,
                heading=" / ".join(path) or None,
                heading_path=tuple(path),
            )
        )
    flush_rows()
    if not sections:
        raise EmptyExtractedTextError("The HTML file contains no text.")
    return sections
