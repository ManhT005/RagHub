"""Build golden corpus Markdown from collected HaUI snapshots (haui/).

Deterministic: same input files always produce byte-identical Markdown.
HTML: keep title/date/article body, drop menu/header/footer/scripts;
tables -> Markdown tables, lists kept, links kept as text (real URLs kept
only for xettuyen/haui domains inside body text).
PDF: text-first via PyMuPDF with page markers.

Usage (from backend/):
    .venv/Scripts/python scripts/build_golden_corpus.py
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
HAUI = BACKEND.parent / "haui"
OUT = BACKEND / "tests" / "fixtures" / "rag_golden" / "corpus"

def _ascii_fold(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# (doc_id, keyword in ascii-folded filename, admission year)
FILES = [
    ("doc-001", "thong bao tuyen sinh", "2026"),
    ("doc-002", "phuong thuc tuyen sinh", "2026"),
    ("doc-003", "diem moi trong tuyen sinh", "2026"),
    ("doc-004", "dang ky xet tuyen", "2026"),
    ("doc-005", "vi mach ban dan", "2026"),
    ("doc-006", "quy tac quy doi", "2026"),
    ("doc-007", "huong dan tuyen sinh dai hoc", "2026"),
    ("doc-008", "dot 2", "2026"),
    ("doc-009", "chuong trinh dao tao bang tieng anh", "2026"),
]


def _resolve(keyword: str) -> Path:
    matches = [p for p in HAUI.iterdir() if keyword in _ascii_fold(p.name)]
    if len(matches) != 1:
        raise FileNotFoundError(f"keyword {keyword!r} matched {len(matches)} files")
    return matches[0]


class ArticleExtractor(HTMLParser):
    """Extract title/date/body from HaUI article pages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._depth = 0
        self._body_depth: int | None = None
        self._in_h3 = False
        self._in_table = 0
        self._in_cell = False
        self._cell_text: list[str] = []
        self._row: list[str] = []
        self._in_li = False
        self._in_strong = False
        self._in_a = False
        self.title_parts: list[str] = []
        self.page_title = ""
        self._in_title_tag = False
        self.blocks: list[str] = []
        self._para: list[str] = []
        self.date = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "title":
            self._in_title_tag = True
        if tag == "div" and "single-latest-text" in (attrs_d.get("class") or ""):
            self._body_depth = self._depth
        self._depth += 1
        if self._body_depth is None:
            return
        if tag == "h3":
            self._in_h3 = True
        elif tag == "table":
            self._flush_para()
            self._in_table += 1
        elif tag in ("td", "th") and self._in_table:
            self._in_cell = True
            self._cell_text = []
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag == "li":
            self._flush_para()
            self._in_li = True
            self._para = []
        elif tag == "strong":
            self._in_strong = True
        elif tag == "a":
            self._in_a = True
        elif tag == "br":
            self._text("\n")
        elif tag == "img":
            alt = (attrs_d.get("alt") or "").strip()
            if alt:
                self._text(f"[hình: {alt}]")

    def handle_endtag(self, tag: str) -> None:
        self._depth -= 1
        if tag == "title":
            self._in_title_tag = False
        if self._body_depth is not None and self._depth < self._body_depth:
            self._flush_para()
            self._body_depth = None
            return
        if self._body_depth is None:
            return
        if tag == "h3":
            self._in_h3 = False
        elif tag == "table":
            self._in_table = max(0, self._in_table - 1)
        elif tag in ("td", "th") and self._in_cell:
            self._in_cell = False
            self._row.append(clean(" ".join(self._cell_text)))
        elif tag == "tr" and self._in_table and self._row:
            cells = [c.replace("\n", "; ").replace("|", "/") for c in self._row]
            cells = [clean(c) for c in cells]
            if any(cells):
                self.blocks.append(("| " + " | ".join(cells) + " |", True))
            self._row = []
        elif tag == "li" and self._in_li:
            self._in_li = False
            text = clean(" ".join(self._para))
            if text:
                self.blocks.append(f"- {text}")
            self._para = []
        elif tag == "strong":
            self._in_strong = False
        elif tag == "a":
            self._in_a = False
        elif tag == "p":
            self._flush_para()

    def handle_data(self, data: str) -> None:
        if self._in_title_tag:
            self.page_title += data
            return
        if self._body_depth is None:
            return
        if self._in_h3:
            self.title_parts.append(data)
            return
        text = data.strip()
        if not text:
            return
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}(\s+\d{2}:\d{2}(:\d{2})?)?", text):
            self.date = text
            return
        if self._in_cell:
            self._cell_text.append(text)
            return
        if self._in_strong:
            text = f"**{text}**"
        self._text(text)

    def _text(self, text: str) -> None:
        if self._in_cell:
            self._cell_text.append(text)
        else:
            self._para.append(text)

    def _flush_para(self) -> None:
        text = clean(" ".join(self._para))
        self._para = []
        if not text:
            return
        if re.fullmatch(r"[\d\s/views:]*", text):
            return
        self.blocks.append(text)


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_html(path: Path) -> tuple[str, str, str]:
    raw = path.read_bytes()
    html = raw.decode("utf-8", errors="replace")
    parser = ArticleExtractor()
    parser.feed(html)
    title = clean("".join(parser.title_parts)) or clean(parser.page_title) or path.stem
    date = ""
    match = re.search(r"(\d{2}/\d{2}/\d{4})", parser.date)
    if match:
        day, month, year = match.group(1).split("/")
        date = f"{year}-{month}-{day}"
    lines = [f"# {title}", ""]
    if date:
        lines += [f"> Ngày đăng: {date} (theo trang tuyển sinh HaUI).", ""]
    lines += ["> Snapshot offline cho golden corpus `golden-v1`.", ""]
    in_table = False
    for block in parser.blocks:
        if isinstance(block, tuple):
            row, _ = block
            if re.fullmatch(r"\|(\s*\|)+", row):
                continue
            lines.append(row)
            if not in_table:
                lines.append(_sep(row))
                in_table = True
        else:
            if re.fullmatch(r"\|(\s*\|)+", block):
                continue
            in_table = False
            lines.append(block)
            lines.append("")
    return title, date, clean("\n".join(lines)) + "\n"


def _sep(row: str) -> str:
    ncols = row.count("|") - 1
    return "| " + " | ".join(["---"] * ncols) + " |"


def convert_pdf(path: Path) -> tuple[str, str]:
    import fitz

    doc = fitz.open(path)
    parts = []
    for i, page in enumerate(doc):
        text = clean(page.get_text("text"))
        if text:
            parts.append(f"## Trang {i + 1}\n\n{text}")
    title = path.stem
    header = f"# {title}\n\n> Snapshot offline (PDF) cho golden corpus `golden-v1`.\n\n"
    body = header + "\n\n".join(parts)
    return title, clean(body) + "\n"


def slugify(name: str) -> str:
    name = name.replace("đ", "d").replace("Đ", "D")
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    if len(name) > 50:
        cut = name[:50].rsplit("-", 1)[0]
        name = cut or name[:50]
    return name


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # Drop previous synthetic corpus files (replaced by real snapshots).
    for old in OUT.glob("doc-*.md"):
        old.unlink()
    manifest_docs = []
    for doc_id, keyword, year in FILES:
        src = _resolve(keyword)
        if src.suffix.lower() == ".pdf":
            title, md = convert_pdf(src)
            published = ""
        else:
            title, published, md = convert_html(src)
        out_name = f"{doc_id}-{slugify(title)}.md"
        payload = md.encode("utf-8")
        (OUT / out_name).write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        slug = slugify(title)
        manifest_docs.append(
            {
                "document_id": doc_id,
                "title": title,
                "source_url": f"https://tuyensinh.haui.edu.vn/dai-hoc-chinh-quy/{slug}",
                "url_verified": False,
                "source_file": src.name,
                "file": f"corpus/{out_name}",
                "published_at": published or f"{year}-01-01",
                "retrieved_at": "2026-10-04",
                "admission_year": year,
                "content_sha256": digest,
                "bytes": len(md.encode("utf-8")),
            }
        )
        print(f"{doc_id}: {len(md)} chars date={published}")
    manifest = {"corpus_revision": "golden-v1", "created": "2026-10-04", "documents": manifest_docs}
    (OUT.parent / "corpus_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
