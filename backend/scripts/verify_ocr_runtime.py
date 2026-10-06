"""Verify Tesseract languages and image-only PDF parsing inside an OCR image.

Run from the repository root:
    Get-Content -Raw backend/scripts/verify_ocr_runtime.py | docker run --rm -i IMAGE python -
"""

import subprocess

import pymupdf

from app.infrastructure.parsing.pdf import parse_pdf


class Recorder:
    def __init__(self):
        self.pages = 0
        self.timings = []

    def timing(self, name, elapsed_ms, labels):
        self.timings.append((name, elapsed_ms))

    def counter(self, name, labels):
        if name == "ocr_pages":
            self.pages += 1


def main():
    languages = subprocess.check_output(["tesseract", "--list-langs"], text=True).splitlines()
    assert {"eng", "vie"}.issubset(languages), languages
    with pymupdf.open() as original:
        page = original.new_page()
        page.insert_textbox(
            pymupdf.Rect(40, 40, 550, 400),
            "RagHub configuration documents support reliable retrieval.\n"
            "The workspace contains information about providers and indexing.\n"
            "Read the source document before answering the question.",
            fontsize=18,
        )
        bitmap = page.get_pixmap(dpi=200).tobytes("png")
    with pymupdf.open() as scanned:
        page = scanned.new_page()
        page.insert_image(page.rect, stream=bitmap)
        assert not page.get_text().strip()
        telemetry = Recorder()
        sections = parse_pdf(scanned.tobytes(), "scan.pdf", ocr_enabled=True, telemetry=telemetry)
    assert len(sections) == 1 and sections[0].type == "ocr_text"
    assert "configuration" in sections[0].content.lower()
    assert sections[0].page_number == 1
    assert telemetry.pages == 1 and telemetry.timings[0][1] > 0
    print("OCR smoke passed: image-only PDF, eng+vie, page metadata and telemetry.")


if __name__ == "__main__":
    main()
