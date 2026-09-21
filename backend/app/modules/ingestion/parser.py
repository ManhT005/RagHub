from dataclasses import dataclass

import pymupdf


class InvalidPdfError(ValueError):
    pass


class UnsupportedOcrError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedPage:
    page_number: int
    content: str


def parse_pdf(content: bytes) -> list[ParsedPage]:
    if not content.startswith(b"%PDF-"):
        raise InvalidPdfError("The uploaded file does not have a valid PDF signature.")

    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise InvalidPdfError("The PDF cannot be opened.") from exc

    try:
        pages = [
            ParsedPage(page_number=index + 1, content=page.get_text("text").strip())
            for index, page in enumerate(document)
        ]
    finally:
        document.close()

    if not any(page.content for page in pages):
        raise UnsupportedOcrError("The PDF contains no extractable text; OCR is not supported.")
    return pages
