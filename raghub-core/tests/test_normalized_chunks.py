from uuid import uuid4

from raghub_core.domain.ingestion.chunker import chunk_sections
from raghub_core.domain.ingestion.embedding_text import build_embedding_text
from raghub_core.domain.ingestion.normalization import normalize_sections
from raghub_core.domain.ingestion.parser import ParsedBlock
from raghub_core.ports.provider_resolver import EmbeddingRuntime

from .test_ingestion import pipeline


def test_normalized_chunks_keep_raw_slices_and_deterministic_links():
    blocks = [
        ParsedBlock(
            "Fact  " + str(i) + ".", "guide.pdf", i, 1, "Topic", heading_path=("Guide", "Topic")
        )
        for i in range(90)
    ]
    version = uuid4()
    normalized = normalize_sections(blocks)
    chunks = chunk_sections(normalized, version, target_tokens=100, overlap_tokens=12)
    assert chunks == chunk_sections(normalized, version, target_tokens=100, overlap_tokens=12)
    assert len(chunks) < len(blocks) and len(chunks) > 1
    assert all(c.content and c.normalized_content and "Fact  " in c.content for c in chunks)
    assert chunks[0].previous_chunk_id is None and chunks[-1].next_chunk_id is None
    for before, after in zip(chunks, chunks[1:], strict=False):
        assert before.next_chunk_id == after.chunk_id
        assert after.previous_chunk_id == before.chunk_id
        assert before.parent_section_id == after.parent_section_id
    assert all(c.heading_path == ("Guide", "Topic") for c in chunks)


def test_table_normalization_keeps_rows_in_raw_citation_and_actual_row_metadata():
    raw = "| Name | Value |\n|---|---|\n" + "\n".join(
        f"| item-{i} | value  {i} |" for i in range(40)
    )
    block = ParsedBlock(
        raw,
        "g.xlsx",
        0,
        type="table",
        heading_path=("Data",),
        metadata={"sheet": "Data", "row_numbers": list(range(2, 82, 2))},
    )
    chunks = chunk_sections(
        normalize_sections([block]), uuid4(), target_tokens=100, overlap_tokens=12
    )
    assert len(chunks) > 1
    assert chunks[0].metadata["row_start"] == 2
    assert chunks[-1].metadata["row_end"] == 80
    for i in range(40):
        assert sum(f"| item-{i} | value  {i} |" in c.content for c in chunks) == 1
    assert all(c.content.startswith("| Name | Value |") for c in chunks)


def test_context_renderer_does_not_edit_raw_citation():
    chunk = chunk_sections(
        normalize_sections(
            [ParsedBlock("Raw  fact.", "g.pdf", 0, 12, "Topic", heading_path=("Guide", "Topic"))]
        ),
        uuid4(),
    )[0]
    assert (
        build_embedding_text(chunk, pipeline="context-v1")
        == "Source: g.pdf\nSection: Guide > Topic\nPage: 12\n\nRaw fact."
    )
    assert chunk.content == "Raw  fact."


async def test_pipeline_uses_the_index_snapshot_strategy_and_embeds_enriched_text():
    document, repository, providers, store, use_case = pipeline(b"# Guide\n\nRaw  fact.")

    async def resolve(scope):
        return EmbeddingRuntime(
            providers.embedding,
            "index",
            2,
            fingerprint="context-fp",
            document_pipeline="context-v1",
        )

    providers.resolve_embedding = resolve
    await use_case.execute(document.version_id)
    chunk = store.indexes[0].chunks[0].chunk
    assert chunk.content == "Raw  fact."
    assert chunk.embedding_content.startswith("Source: a.md\nSection: Guide")
