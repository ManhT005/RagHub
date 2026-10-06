import unicodedata

from raghub_core.domain.ingestion.normalization import normalize_sections
from raghub_core.domain.ingestion.parser import ParsedBlock


def test_normalization_retains_raw_citation_and_has_stable_nfc_hash():
    original = (
        "  " + unicodedata.normalize("NFD", "Tuyển sinh") + "   configu-\nration.\n\n\nNext.  "
    )
    block = ParsedBlock(original, "guide.pdf", 0, 1, metadata={"format": "pdf"})
    normalized = normalize_sections([block])[0]
    assert normalized.content == "Tuyển sinh configuration.\n\nNext."
    assert normalized.raw_content == original
    assert "configu-\nration" in normalized.raw_slice(11, 25)
    assert normalize_sections([block]) == [normalized]
    assert len(normalized.content_hash) == 64
    word = normalized.raw_slice(0, 5)
    assert unicodedata.normalize("NFC", word) == "Tuyển"


def test_repeated_pdf_margins_do_not_erase_body_facts_or_short_pages():
    blocks = [
        ParsedBlock(
            f"Handbook\nTopic {i}\nValue {i * 10}\nAnother fact\nPage {i}",
            "guide.pdf",
            i,
            i,
            metadata={"format": "pdf"},
        )
        for i in range(1, 5)
    ]
    normalized = normalize_sections(blocks)
    assert len(normalized) == 4
    for i, block in enumerate(normalized, 1):
        assert "Handbook" not in block.content and "Page" not in block.content
        assert f"Value {i * 10}" in block.content
        assert "Handbook" in block.raw_content
    short = ParsedBlock("Handbook\nOnly fact", "guide.pdf", 5, 5, metadata={"format": "pdf"})
    assert normalize_sections([*blocks, short])[-1].content == short.content


def test_duplicate_paragraph_detection_preserves_tables_lists_pages_and_paths():
    paragraph = ParsedBlock("Same fact", "g.docx", 0, heading_path=("A",))
    table = ParsedBlock("| H |\n|---|\n| X |\n| X |", "g.docx", 1, type="table")
    item = ParsedBlock("- Same item", "g.docx", 2, type="list")
    assert len(normalize_sections([paragraph, paragraph, table, table, item, item])) == 5
    other = ParsedBlock("Same fact", "g.docx", 3, heading_path=("B",))
    assert len(normalize_sections([paragraph, other])) == 2


def test_code_indentation_and_real_hyphens_are_preserved():
    block = ParsedBlock("def f():\n    return 1", "g.html", 0, type="code")
    assert normalize_sections([block])[0].content == block.content
    block = ParsedBlock("state-of-the-art 2026-2027", "g.pdf", 1, 1)
    assert normalize_sections([block])[0].content == block.content
