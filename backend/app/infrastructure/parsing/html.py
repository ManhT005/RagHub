"""Offline structural HTML extraction with nested hidden subtree removal."""

from dataclasses import replace
from html.parser import HTMLParser

from raghub_core.domain.ingestion.limits import check_compressed_size
from raghub_core.domain.ingestion.parser import EmptyExtractedTextError, ParsedBlock

_SKIP = {"script", "style", "form", "noscript", "template", "head"}
_VOID = {"br", "hr", "img", "input", "meta", "link", "source", "wbr"}


class _Sanitizer(HTMLParser):
    def __init__(self, *, structured=False, focus_main=False):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.blocks = []
        self.text = []
        self.kind = "paragraph"
        self.row = []
        self.cell = None
        self.structured, self.focus_main = structured, focus_main
        self.list_counts = {}
        self.marker = "- "
        self.table_warnings = []

    def flush(self):
        raw = ("" if self.kind == "code" else " ").join(self.text)
        text = raw.rstrip("\r\n") if self.structured and self.kind == "code" else raw.strip()
        self.text = []
        if text:
            self.blocks.append(
                (
                    self.kind,
                    (self.marker if self.structured else "- ") + text
                    if self.kind == "list"
                    else text,
                )
            )

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (self.stack and self.stack[-1][1]) or tag in _SKIP or "hidden" in attrs
        if self.structured:
            hidden = (
                hidden
                or tag in {"nav", "footer", "aside"}
                or attrs.get("role") in {"navigation", "complementary", "banner", "contentinfo"}
            )
            if tag == "header" and not any(t in {"main", "article"} for t, _ in self.stack):
                hidden = True
        style = (attrs.get("style") or "").replace(" ", "").lower()
        hidden = bool(hidden or "display:none" in style or "visibility:hidden" in style)
        if tag not in _VOID:
            self.stack.append((tag, hidden))
        if hidden or (self.focus_main and not any(t == "main" for t, _ in self.stack)):
            return
        if self.structured and tag == "ol":
            try:
                self.list_counts[len(self.stack) - 1] = int(attrs.get("start", "1")) - 1
            except ValueError:
                self.list_counts[len(self.stack) - 1] = 0
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
            if self.structured and tag == "li":
                parents = [
                    (i, name) for i, (name, _) in enumerate(self.stack) if name in {"ul", "ol"}
                ]
                if parents and parents[-1][1] == "ol":
                    index = parents[-1][0]
                    self.list_counts[index] = self.list_counts.get(index, 0) + 1
                    self.marker = f"{self.list_counts[index]}. "
                else:
                    self.marker = "- "
        if tag == "tr":
            self.row = []
        if tag in {"td", "th"}:
            self.cell = []
            if self.structured and any(
                attrs.get(key, "1") != "1" for key in ("rowspan", "colspan")
            ):
                self.table_warnings = ["TABLE_SPANS_REQUIRE_REVIEW"]
        if tag == "br":
            self.text.append("\n")

    def handle_endtag(self, tag):
        hidden = (self.stack and self.stack[-1][1]) or (
            self.focus_main and not any(t == "main" for t, _ in self.stack)
        )
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
        if self.focus_main and not any(t == "main" for t, _ in self.stack):
            return
        if data.strip() or (self.structured and self.kind == "code"):
            (self.cell if self.cell is not None else self.text).append(
                data if self.kind == "code" else data.strip()
            )


class _MainProbe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = False

    def handle_starttag(self, tag, attrs):
        if tag == "main" and "hidden" not in dict(attrs):
            self.found = True


def parse_html(content, source_name="document.html", *, structured=False):
    check_compressed_size(len(content))
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("windows-1252", errors="replace")
    probe = _MainProbe()
    probe.feed(text)
    parser = _Sanitizer(structured=structured, focus_main=structured and probe.found)
    parser.feed(text)
    parser.flush()
    if structured and probe.found and not parser.blocks:
        parser = _Sanitizer(structured=True)
        parser.feed(text)
        parser.flush()
    sections, path, rows, levels = [], [], [], []

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
                    metadata={"format": "html", "quality_warnings": parser.table_warnings}
                    if structured
                    else {},
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
            if structured:
                level = int(kind[1])
                while levels and levels[-1][0] >= level:
                    levels.pop()
                levels.append((level, text))
                path = [label for _, label in levels]
            else:
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
                metadata={"format": "html"} if structured else {},
            )
        )
    flush_rows()
    if structured:
        unique, seen, removed = [], set(), 0
        for block in sections:
            key = (block.heading_path, " ".join(block.content.split()).casefold())
            if block.type == "paragraph" and key in seen:
                removed += 1
                continue
            if block.type == "paragraph":
                seen.add(key)
            unique.append(block)
        sections = [
            replace(b, metadata={**b.metadata, "duplicate_paragraphs_removed": removed})
            for b in unique
        ]
    if not sections:
        raise EmptyExtractedTextError("The HTML file contains no text.")
    return sections
