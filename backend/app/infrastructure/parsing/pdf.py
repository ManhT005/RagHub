import pymupdf

from app.core_domain.ingestion.parser import InvalidPdfError, ParsedSection, UnsupportedOcrError


def parse_pdf(content: bytes, source_name: str = "document.pdf") -> list[ParsedSection]:
    if not content.startswith(b"%PDF-"):
        raise InvalidPdfError("The uploaded file does not have a valid PDF signature.")
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
        try:
            pages = [
                ParsedSection(page.get_text("text").strip(), source_name, index, index + 1)
                for index, page in enumerate(document)
            ]
        finally:
            document.close()
    except Exception as exc:
        raise InvalidPdfError("The PDF cannot be opened or read.") from exc
    if not any(page.content for page in pages):
        raise UnsupportedOcrError("The PDF contains no extractable text; OCR is not supported.")
    return [page for page in pages if page.content]


