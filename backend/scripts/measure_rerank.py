"""One-off: measure reranker impact on golden QA (fusion vs reranked).

Compares fused top-5 against reranked top-25→8→5 using the pinned local
cross-encoder, on the live eval workspace. Reports hit/MRR/nDCG deltas
plus rerank latency. Nothing is enabled in production.

Usage (from backend/):
    python scripts/measure_rerank.py --mint-email you@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_production_eval import GOLDEN, expected_keys  # noqa: E402


def snapshot_sha(model) -> str:
    digest = hashlib.sha256()
    base = Path(model.model_path) if hasattr(model, "model_path") else None
    files = sorted(base.rglob("*")) if base else []
    for path in files:
        if path.is_file():
            digest.update(path.name.encode())
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
    return digest.hexdigest()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint-email", required=False, default=None)
    args = ap.parse_args()

    import asyncpg
    from raghub_core.api import RetrievalScope
    from raghub_core.domain.evaluation.metrics import hit_at_k, mrr_at_k, ndcg_at_k
    from raghub_core.domain.retrieval.hybrid import (
        RERANK_SOURCE_COUNT,
        normalize_query,
    )
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.infrastructure.ai.local_reranker import LocalCrossEncoderReranker
    from app.infrastructure.elasticsearch.chunks import ChunkSearch
    from app.infrastructure.providers import ProviderResolverAdapter
    from app.infrastructure.retrieval_mapping import fuse_branches_to_candidates
    from app.modules.ai_providers.resolver import ProviderResolver

    conn = await asyncpg.connect(
        "postgresql://raghub:raghub-local-only@127.0.0.1:5434/raghub"
    )
    try:
        me = await conn.fetchval(
            "SELECT id FROM users WHERE email='khactu731@gmail.com'"
        )
        if me is None:
            raise SystemExit("eval user not found")
        org = await conn.fetchval("SELECT id FROM organizations WHERE slug='eval-golden'")
        ws = await conn.fetchval(
            "SELECT id FROM workspaces WHERE slug='golden-test' AND organization_id=$1", org
        )
        index = await conn.fetchval(
            """SELECT v.index_name FROM embedding_index_versions v
               JOIN workspaces w ON w.active_embedding_index_version_id = v.id
               WHERE w.id=$1""",
            ws,
        )
    finally:
        await conn.close()
    print(f"index: {index}", flush=True)

    manifest = json.loads((GOLDEN / "corpus_manifest.json").read_text(encoding="utf-8"))
    docs = manifest if isinstance(manifest, list) else manifest.get("documents", [])
    file_of = {}
    for d in docs:
        file_of[d["document_id"]] = (d.get("file") or "").split("/")[-1]
    qa = json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))

    try:
        from sentence_transformers import CrossEncoder

        model = CrossEncoder("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", max_length=512)
        sha = snapshot_sha(model)
    except ImportError as exc:
        raise SystemExit("sentence-transformers is required for measurement") from exc
    reranker = LocalCrossEncoderReranker(expected_sha256=sha, timeout_seconds=120.0)

    from app.core.config import Settings as AppSettings

    db_url = "postgresql+asyncpg://raghub:raghub-local-only@127.0.0.1:5434/raghub"
    host_settings = AppSettings(_env_file=None, elasticsearch_url="http://127.0.0.1:9200")
    eng = create_async_engine(db_url, poolclass=NullPool)
    lat = []
    base_rows, re_rows = [], []
    try:
        async with AsyncSession(eng, expire_on_commit=False) as session:
            resolver = ProviderResolverAdapter(ProviderResolver(session))
            scope = RetrievalScope(UUID(str(org)), UUID(str(ws)))
            runtime = await resolver.resolve_embedding(scope)
            search = ChunkSearch(index_name=index, settings=host_settings)
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
                    cands = fuse_branches_to_candidates(lexical, vec, limit=25, rrf_k=60)
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
        f"rerank p50={lat[len(lat)//2]:.0f}ms p95={lat[int(len(lat)*0.95)-1]:.0f}ms",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
