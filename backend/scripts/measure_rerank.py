"""One-off: measure reranker impact on golden QA (fusion vs reranked).

Compares fused top-5 against reranked top-25→8→5 using the pinned local
cross-encoder, on the live eval workspace. Reports hit/MRR/nDCG deltas
plus rerank latency. Nothing is enabled in production.

Usage (from backend/):
    python scripts/measure_rerank.py --organization-id <UUID> --workspace-id <UUID>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_production_eval import GOLDEN, expected_keys  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--organization-id", type=UUID, required=True)
    ap.add_argument("--workspace-id", type=UUID, required=True)
    ap.add_argument("--timeout-seconds", type=float, default=120.0)
    args = ap.parse_args()

    from raghub_core.api import RetrievalScope
    from raghub_core.domain.evaluation.metrics import hit_at_k, mrr_at_k, ndcg_at_k
    from raghub_core.domain.retrieval.hybrid import (
        RERANK_SOURCE_COUNT,
        normalize_query,
    )
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import get_settings
    from app.infrastructure.ai.local_reranker import LocalCrossEncoderReranker
    from app.infrastructure.elasticsearch.chunks import ChunkSearch
    from app.infrastructure.providers import ProviderResolverAdapter
    from app.infrastructure.retrieval_mapping import fuse_branches_to_candidates
    from app.modules.ai_providers.resolver import ProviderResolver

    host_settings = get_settings()
    org, ws = args.organization_id, args.workspace_id
    if not host_settings.rag_reranker_expected_sha256:
        raise SystemExit("Set a reviewed RAG_RERANKER_EXPECTED_SHA256 before benchmarking")
    manifest = json.loads((GOLDEN / "corpus_manifest.json").read_text(encoding="utf-8"))
    docs = manifest if isinstance(manifest, list) else manifest.get("documents", [])
    file_of = {}
    for d in docs:
        file_of[d["document_id"]] = (d.get("file") or "").split("/")[-1]
    qa = json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))

    reranker = LocalCrossEncoderReranker(
        expected_sha256=host_settings.rag_reranker_expected_sha256,
        snapshot_path=host_settings.rag_reranker_snapshot_path,
        timeout_seconds=args.timeout_seconds,
    )
    eng = create_async_engine(host_settings.database_url, poolclass=NullPool)
    lat = []
    base_rows, re_rows = [], []
    try:
        async with AsyncSession(eng, expire_on_commit=False) as session:
            resolver = ProviderResolverAdapter(ProviderResolver(session))
            scope = RetrievalScope(UUID(str(org)), UUID(str(ws)))
            runtime = await resolver.resolve_embedding(scope)
            search = ChunkSearch(index_name=runtime.index_name, settings=host_settings)
            try:
                for case in qa:
                    normed = normalize_query(case["question"])
                    exp = expected_keys(
                        case.get("expected_document_ids", []),
                        case.get("expected_chunk_ids", []),
                        file_of,
                    )
                    vector = await runtime.provider.embed_query(normed)
                    lexical, vec = await search.search_branches(
                        organization_id=scope.organization_id,
                        workspace_id=scope.workspace_id,
                        query=normed,
                        query_vector=vector,
                    )
                    cands = fuse_branches_to_candidates(
                        lexical,
                        vec,
                        limit=host_settings.rag_retrieval_candidates,
                        rrf_k=host_settings.rag_rrf_k,
                    )
                    fused_files = [c.chunk.source_name for c in cands[:5]]
                    t0 = time.perf_counter()
                    reranked = await reranker.rerank(
                        query=normed,
                        candidates=[c.chunk for c in cands[:RERANK_SOURCE_COUNT]],
                        top_n=8,
                    )
                    rms = (time.perf_counter() - t0) * 1000
                    lat.append(rms)
                    re_files = [h.source_name for h in reranked[:5]]
                    base_rows.append((exp, fused_files))
                    re_rows.append((exp, re_files))
                    print(
                        f"{case.get('id')} fused5={[f[:14] for f in fused_files]} "
                        f"re5={[f[:14] for f in re_files]} rms={rms:.0f}ms",
                        flush=True,
                    )
            finally:
                await search.close()
    finally:
        await eng.dispose()

    for name, rows in (("fused", base_rows), ("reranked", re_rows)):
        hits = sum(hit_at_k(r, e) for e, r in rows) / len(rows)
        mrr = sum(mrr_at_k(r, e) for e, r in rows) / len(rows)
        ndcg = sum(ndcg_at_k(r, {k: 1.0 for k in e}) for e, r in rows) / len(rows)
        print(f"{name}: hit@5={hits:.3f} mrr@5={mrr:.3f} ndcg@5={ndcg:.3f}", flush=True)
    lat.sort()
    print(
        f"rerank p50={lat[len(lat) // 2]:.0f}ms p95={lat[int(len(lat) * 0.95) - 1]:.0f}ms",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
