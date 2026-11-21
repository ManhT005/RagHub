from uuid import uuid4

import pytest

from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.domain.ingestion.errors import IngestionError
from raghub_core.domain.ingestion.markdown_v2 import chunk_markdown_blocks, parse_markdown_blocks
from raghub_core.domain.ingestion.parser import DocumentLimitError, parse_markdown
from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.ports.provider_resolver import EmbeddingRuntime

from .test_ingestion import pipeline


def chunks(text, budget=140):
    return chunk_markdown_blocks(
        parse_markdown_blocks(text.encode(), "guide.md"), uuid4(), target_tokens=budget
    )


def test_block_types_heading_path_frontmatter_and_source_lines():
    text = (
        '---\ntitle: "Guide"\n---\n# Guide\nIntro\n\n## Setup\n1. First\n2. Second\n\n'
        '| Key | Value |\n|---|---|\n| k | v |\n\n```python\n# Not a heading\n    pass\n```\n'
    )
    blocks = parse_markdown_blocks(text.encode(), "guide.md")
    assert [b.type for b in blocks] == ["heading", "paragraph", "heading", "list", "table", "code"]
    assert blocks[-1].heading_path == ("Guide", "Setup")
    assert blocks[-1].metadata["document_title"] == "Guide"
    for block in blocks:
        assert block.content == "\n".join(
            text.splitlines()[block.metadata["line_start"] - 1 : block.metadata["line_end"]]
        )


def test_setext_headings_and_fence_matching_do_not_create_false_sections():
    blocks = parse_markdown_blocks(
        b"Title\n=====\nText\n\n~~~md\n# code heading\n```\n~~~\n\nSection\n---\nMore", "g.md"
    )
    assert blocks[-1].heading_path == ("Title", "Section")
    assert len([b for b in blocks if b.type == "heading"]) == 2
    assert "```" in next(b.content for b in blocks if b.type == "code")


def test_oversized_code_chunks_keep_indentation_and_fences():
    lines = [f'    print("line-{i}")' for i in range(50)]
    result = chunks("# Example\n\n```python\n" + "\n".join(lines) + "\n```", 100)
    assert len(result) > 1
    assert all(c.content.startswith("```python\n") and c.content.endswith("\n```") for c in result)
    assert all(len(ENCODING.encode(c.embedding_content)) <= 100 for c in result)
    for line in lines:
        assert sum(line in c.content.splitlines() for c in result) == 1


def test_lists_pack_whole_items_with_nested_children_and_no_loss():
    items = [f"{i}. Step {i}\n   - child {i}" for i in range(1, 25)]
    result = chunks("# Steps\n\n" + "\n\n".join(items), 110)
    assert len(result) > 1
    for item in items:
        assert sum(item in c.content for c in result) == 1
    assert all(c.metadata["block_type"] == "list" for c in result)


def test_tables_repeat_header_and_preserve_every_row_once():
    header = "| Name | Value |\n|---|---|"
    rows = [f"| item-{i} | value {i} |" for i in range(50)]
    result = chunks("# Settings\n\n" + header + "\n" + "\n".join(rows), 110)
    assert len(result) > 1
    assert all(c.content.startswith(header) for c in result)
    for row in rows:
        assert sum(row in c.content.splitlines() for c in result) == 1
    assert all(len(ENCODING.encode(c.embedding_content)) <= 110 for c in result)


def test_unrepresentable_table_row_fails_explicitly_instead_of_breaking_columns():
    with pytest.raises(DocumentLimitError, match="table row"):
        chunks("# Table\n\n| A | B |\n|---|---|\n| a | " + "large " * 300 + "|", 100)


def test_large_code_line_and_unicode_are_bounded_without_text_loss():
    body = "tiếng Việt 🧠 " * 120
    result = chunks("# Ví dụ\n\n```text\n" + body + "\n```", 120)
    restored = "".join(c.content.partition("\n")[2].rpartition("\n")[0] for c in result)
    assert restored == body
    assert all(len(ENCODING.encode(c.embedding_content)) <= 120 for c in result)
    assert all(c.metadata["structural_split"] for c in result)


def test_chunk_ids_and_neighbor_links_are_deterministic_and_scoped():
    blocks = parse_markdown_blocks(("# Intro\n" + "Text " * 300).encode(), "guide.md")
    version = uuid4()
    result = chunk_markdown_blocks(blocks, version, target_tokens=100)
    assert result == chunk_markdown_blocks(blocks, version, target_tokens=100)
    assert result[0].previous_chunk_id is None and result[-1].next_chunk_id is None
    assert result[0].next_chunk_id == result[1].chunk_id
    assert (
        result[0].chunk_id != chunk_markdown_blocks(blocks, uuid4(), target_tokens=100)[0].chunk_id
    )


async def test_pipeline_is_opt_in_and_embeds_bounded_structured_context():
    text = b"# Guide\n\n## Setup\n```python\n    print(1)\n```"
    doc, _, providers, store, use_case = pipeline(text)
    legacy = chunk_sections(parse_markdown(text, "a.md"), doc.version_id)

    async def resolve(scope):
        return EmbeddingRuntime(providers.embedding, "index", 2, document_pipeline="markdown-v2")

    providers.resolve_embedding = resolve
    await use_case.execute(doc.version_id)
    chunk = store.indexes[0].chunks[0].chunk
    assert chunk.heading_path == ("Guide", "Setup")
    assert chunk.content == "```python\n    print(1)\n```"
    assert chunk.embedding_content.startswith("Source: a.md\nSection: Guide > Setup\n\n")
    assert chunk_sections(parse_markdown(text, "a.md"), doc.version_id) == legacy


async def test_frontmatter_only_is_rejected_without_embedding():
    doc, _, providers, _, use_case = pipeline(b"---\ntitle: Empty\n---")

    async def resolve(scope):
        return EmbeddingRuntime(providers.embedding, "index", 2, document_pipeline="markdown-v2")

    providers.resolve_embedding = resolve
    with pytest.raises(IngestionError) as error:
        await use_case.execute(doc.version_id)
    assert error.value.code == "EMPTY_EXTRACTED_TEXT"
    assert not providers.embedding.calls


def test_repeated_headings_get_separate_parents_and_small_paragraphs_are_not_split():
    result = chunks("# Guide\n\n## Setup\nFirst body.\n\n## Setup\nSecond body.")
    assert len(result) == 2
    assert result[0].heading_path == result[1].heading_path
    assert result[0].parent_section_id != result[1].parent_section_id
    assert all(not c.metadata["structural_split"] for c in result)


def test_unclosed_fence_is_preserved_with_an_explicit_warning():
    blocks = parse_markdown_blocks(b"# Guide\n```text\n# stays code", "g.md")
    assert blocks[-1].type == "code" and blocks[-1].metadata["unclosed_fence"]
    result = chunk_markdown_blocks(blocks, uuid4())
    assert "# stays code" in result[0].content
    assert result[0].metadata["synthetic_fences"]


def test_long_paragraph_prefers_sentence_boundaries_without_dropping_text():
    body = "Sentence with important configuration details. " * 100
    result = chunks("# Guide\n" + body, 100)
    assert "".join(c.content for c in result) == body
    assert all(c.content.endswith(". ") for c in result)
