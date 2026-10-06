"""Read-only live ES ablations. Reports remain informational without reviewed labels.

Use an explicit tenant/workspace, deployment settings and a reviewed evidence map
{case_id: [actual chunk UUID, ...]}. Query embeddings are reused across grid cells;
each cell executes real BM25/ANN queries with its own candidate count.
"""

import argparse
import asyncio
import hashlib
import itertools
import json
import math
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raghub_core.api import RetrievalScope  # noqa: E402
from raghub_core.domain.embedding.quota import estimate_tokens  # noqa: E402
from raghub_core.domain.evaluation.metrics import (  # noqa: E402
    hit_at_k,
    mrr_at_k,
    ndcg_at_k,
    recall_at_k,
)
from raghub_core.domain.ingestion.tokenizer import ENCODING  # noqa: E402
from raghub_core.domain.retrieval.hybrid import (
    MAPPING_VERSION,
    fuse_rrf,
    normalize_query,
    render_citation_block,
)  # noqa: E402
from raghub_core.domain.retrieval.relevance import FEATURE_SCHEMA  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.elasticsearch.chunks import ChunkSearch  # noqa: E402
from app.infrastructure.persistence.readiness import DocumentReadinessAdapter  # noqa: E402
from app.infrastructure.providers import ProviderResolverAdapter  # noqa: E402
from app.infrastructure.redis.query_quota import QueryQuota  # noqa: E402
from app.infrastructure.retrieval_mapping import chunk_from_hit  # noqa: E402
from app.modules.ai_providers.resolver import ProviderResolver  # noqa: E402
from app.modules.search.relevance import dataset_hash, retrieval_config_hash  # noqa: E402
from scripts.rag_dataset_audit import audit_dataset  # noqa: E402
from scripts.run_production_eval import percentile  # noqa: E402

DEFAULT_QA = Path(__file__).resolve().parents[1] / "tests/fixtures/rag_golden/qa.json"


def grid_configs(candidate_counts=(15, 25, 40), rrf_values=(30, 60, 90), caps=(1, 2, 3)):
    result = []
    for candidates, rrf_k, cap in itertools.product(candidate_counts, rrf_values, caps):
        if not 10 <= candidates <= 100 or not 1 <= rrf_k <= 200 or not 1 <= cap <= 25:
            raise ValueError("Ablation configuration is outside supported runtime bounds.")
        result.append({"candidates": candidates, "rrf_k": rrf_k, "max_per_document": cap})
    return result


def score_case(case, hits, expected, elapsed):
    ranked = [str(hit.chunk_id) for hit in hits]
    result = {
        "id": case["id"],
        "split": case["split"],
        "answerable": bool(case["answerable"]),
        "fused_scores": [hit.score for hit in hits],
        "ranked_chunk_ids": ranked,
        "hit@5": hit_at_k(ranked, expected or set()),
        "recall@5": recall_at_k(ranked, expected or set()),
        "mrr@5": mrr_at_k(ranked, expected or set()),
        "ndcg@5": ndcg_at_k(ranked, {key: 1 for key in expected or set()}),
        "context_tokens": sum(
            len(ENCODING.encode(render_citation_block(i, hit))) for i, hit in enumerate(hits, 1)
        ),
        "search_ms": elapsed,
    }
    if expected is None:
        result.update({metric: None for metric in ("hit@5", "recall@5", "mrr@5", "ndcg@5")})
    return result


async def collect(session, settings, scope, cases, configs, evidence_map):
    runtime = await ProviderResolverAdapter(ProviderResolver(session)).resolve_embedding(scope)
    quota = QueryQuota(settings)
    readiness = DocumentReadinessAdapter(session)
    reports = [
        {
            "config": cfg,
            "config_hash": retrieval_config_hash(**cfg, mapping_version=MAPPING_VERSION),
            "cases": [],
        }
        for cfg in configs
    ]
    embedding_latencies = []
    for case in cases:
        expected = (
            {str(UUID(key)) for key in evidence_map.get(case["id"], [])}
            if evidence_map is not None
            else None
        )
        if evidence_map is not None and case["answerable"] and not expected:
            raise ValueError(f"Missing reviewed runtime chunk mapping for {case['id']}")
        query = normalize_query(case["question"])
        started = time.perf_counter()
        if runtime.quota_scope:
            await quota.acquire(
                scope=runtime.quota_scope, tokens=estimate_tokens(len(query)), background=False
            )
        vector = await runtime.provider.embed_query(query)
        if len(vector) != runtime.dimension or not all(math.isfinite(x) for x in vector):
            raise ValueError("Query vector dimension differs from active index.")
        embedding_latencies.append((time.perf_counter() - started) * 1000)
        for report in reports:
            cfg = report["config"]
            search = ChunkSearch(
                index_name=runtime.index_name,
                settings=settings.model_copy(
                    update={
                        "rag_retrieval_candidates": cfg["candidates"],
                        "rag_rrf_k": cfg["rrf_k"],
                        "rag_max_chunks_per_document": cfg["max_per_document"],
                    }
                ),
            )
            started = time.perf_counter()
            try:
                lexical, vector_hits = await search.search_branches(
                    organization_id=scope.organization_id,
                    workspace_id=scope.workspace_id,
                    query=query,
                    query_vector=vector,
                )
                hits = fuse_rrf(
                    [[chunk_from_hit(h) for h in branch] for branch in (lexical, vector_hits)],
                    limit=cfg["candidates"],
                    rrf_k=cfg["rrf_k"],
                    max_per_document=cfg["max_per_document"],
                )
                hits = await readiness.filter_ready(scope, hits)
                elapsed = (time.perf_counter() - started) * 1000
                report["cases"].append(score_case(case, hits[:5], expected, elapsed))
            finally:
                await search.close()
    for report in reports:
        eligible = [c for c in report["cases"] if c["answerable"]]
        report["summary"] = {
            metric: sum(c[metric] for c in eligible) / len(eligible)
            if eligible and all(c[metric] is not None for c in eligible)
            else None
            for metric in ("hit@5", "recall@5", "mrr@5", "ndcg@5", "context_tokens")
        }
        report["summary"].update(
            search_p50_ms=percentile([c["search_ms"] for c in report["cases"]], 0.5),
            search_p95_ms=percentile([c["search_ms"] for c in report["cases"]], 0.95),
        )
    return {
        "index_name": runtime.index_name,
        "embedding_fingerprint": runtime.fingerprint,
        "document_pipeline": runtime.document_pipeline,
        "mapping_version": MAPPING_VERSION,
        "feature_schema": FEATURE_SCHEMA,
        "results": reports,
        "embedding_p50_ms": percentile(embedding_latencies, 0.5),
        "embedding_p95_ms": percentile(embedding_latencies, 0.95),
    }


async def run(args):
    cases = json.loads(args.qa.read_text(encoding="utf-8"))
    evidence_map = (
        json.loads(args.evidence_map.read_text(encoding="utf-8")) if args.evidence_map else None
    )
    audit = audit_dataset(cases)
    if audit["issues"]:
        raise ValueError("Dataset audit failed: " + "; ".join(audit["issues"]))
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            report = await collect(
                session,
                settings,
                RetrievalScope(args.organization_id, args.workspace_id),
                cases,
                grid_configs(args.candidates, args.rrf, args.document_caps),
                evidence_map,
            )
    finally:
        await engine.dispose()
    report.update(
        mode="live-retrieval-ablation",
        created_at=datetime.now(UTC).isoformat(),
        dataset_hash=dataset_hash(args.qa),
        evidence_map_sha256=hashlib.sha256(args.evidence_map.read_bytes()).hexdigest()
        if args.evidence_map
        else None,
        dataset_audit=audit,
        release_eligible=audit["release_eligible"] and evidence_map is not None,
        seed=0,
        facts_recall=None,
        citation_support_precision=None,
    )
    try:
        report["commit"] = (
            await asyncio.to_thread(
                subprocess.check_output, ["git", "rev-parse", "HEAD"], text=True
            )
        ).strip()
    except Exception:
        report["commit"] = "unknown"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "configs": len(report["results"]),
                "cases": len(cases),
                "release_eligible": report["release_eligible"],
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--workspace-id", type=UUID, required=True)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument(
        "--evidence-map",
        type=Path,
        help="Optional labels; omit for latency/capacity diagnostics only",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--candidates", type=int, nargs="+", default=[15, 25, 40])
    parser.add_argument("--rrf", type=int, nargs="+", default=[30, 60, 90])
    parser.add_argument("--document-caps", type=int, nargs="+", default=[1, 2, 3])
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
