import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal


class InvalidPdfError(ValueError):
    pass


class UnsupportedOcrError(ValueError):
    pass


class TextDecodeError(ValueError):
    pass


class EmptyExtractedTextError(ValueError):
    pass


class UnsupportedFileTypeError(ValueError):
    pass


class DocumentLimitError(ValueError):
    pass


class DecompressionBombError(DocumentLimitError):
    pass


class MacroBlockedError(ValueError):
    pass


class SignatureMismatchError(ValueError):
    pass


class OcrRequiredError(ValueError):
    pass


class OcrTimeoutError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedSection:
    content: str
    source_name: str
    section_index: int
    page_number: int | None = None
    heading: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedBlock(ParsedSection):
    type: Literal["heading", "paragraph", "table", "list", "code", "ocr_text"] = "paragraph"
    heading_path: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TextDecodeError("The text file must be UTF-8 encoded.") from exc


def parse_txt(content: bytes, source_name: str) -> list[ParsedSection]:
    text = _decode(content).strip()
    if not text:
        raise EmptyExtractedTextError("The file contains no text.")
    # Blank lines are soft chunk boundaries, not separate citation sections.
    return [ParsedSection(text, source_name, 0)]


def parse_markdown(content: bytes, source_name: str) -> list[ParsedSection]:
    text = _decode(content)
    sections: list[ParsedSection] = []
    heading: str | None = None
    lines: list[str] = []
    fence_character: str | None = None
    fence_length = 0

    def append_section() -> None:
        body = "\n".join(lines).strip()
        if body:
            sections.append(ParsedSection(body, source_name, len(sections), heading=heading))

    for line in text.splitlines():
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence_character is not None:
            lines.append(line)
            if (
                fence
                and fence.group(1)[0] == fence_character
                and len(fence.group(1)) >= fence_length
                and not fence.group(2).strip()
            ):
                fence_character = None
            continue
        if fence:
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            lines.append(line)
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match:
            append_section()
            heading = match.group(1).strip()
            lines = []
        else:
            lines.append(line)
    append_section()
    if not sections:
        raise EmptyExtractedTextError("The file contains no text.")
    return sections


def parse_document(
    content: bytes,
    source_name: str,
    *,
    pdf_parser: Callable[[bytes, str], list[ParsedSection]] | None = None,
    docx_parser: Callable[[bytes, str], list[ParsedSection]] | None = None,
    html_parser: Callable[[bytes, str], list[ParsedSection]] | None = None,
    xlsx_parser: Callable[[bytes, str], list[ParsedSection]] | None = None,
) -> list[ParsedSection]:
    extension = source_name.rsplit(".", 1)[-1].lower()
    if extension == "pdf":
        if pdf_parser is None:
            raise ValueError("PDF decoding requires a PDF parser adapter.")
        return pdf_parser(content, source_name)
    if extension == "txt":
        return parse_txt(content, source_name)
    if extension == "md":
        return parse_markdown(content, source_name)
    if extension == "docx":
        if docx_parser is None:
            raise ValueError("DOCX decoding requires a DOCX parser adapter.")
        return docx_parser(content, source_name)
    if extension in {"html", "htm"}:
        if html_parser is None:
            raise ValueError("HTML decoding requires an HTML parser adapter.")
        return html_parser(content, source_name)
    if extension == "xlsx":
        if xlsx_parser is None:
            raise ValueError("XLSX decoding requires an XLSX parser adapter.")
        return xlsx_parser(content, source_name)
    raise UnsupportedFileTypeError("Unsupported document type.")
