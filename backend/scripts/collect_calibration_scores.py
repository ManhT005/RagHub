"""Collect canonical ready pre-rerank scores from an explicit eval workspace."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

from raghub_core.api import RetrievalScope

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.modules.search.relevance import dataset_hash
from scripts.run_retrieval_ablation import DEFAULT_QA, collect  # noqa: E402


async def run(args):
    settings = get_settings()
    cases = json.loads(args.qa.read_text(encoding="utf-8"))
    config = {
        "candidates": settings.rag_retrieval_candidates,
        "rrf_k": settings.rag_rrf_k,
        "max_per_document": settings.rag_max_chunks_per_document,
    }
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            report = await collect(
                session,
                settings,
                RetrievalScope(args.organization_id, args.workspace_id),
                cases,
                [config],
                None,
            )
    finally:
        await engine.dispose()
    payload = {
        "calibration": [],
        "holdout": [],
        "metadata": {
            "dataset_hash": dataset_hash(args.qa),
            "retrieval_config_hash": report["results"][0]["config_hash"],
            "embedding_fingerprint": report["embedding_fingerprint"],
            "mapping_version": report["mapping_version"],
            "feature_schema": report["feature_schema"],
            "document_pipeline": report["document_pipeline"],
        },
    }
    for row in report["results"][0]["cases"]:
        if row["split"] not in {"calibration", "holdout"}:
            raise ValueError("Every calibration case must declare its split.")
        payload[row["split"]].append(
            {key: row[key] for key in ("id", "split", "fused_scores", "answerable")}
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps({"calibration": len(payload["calibration"]), "holdout": len(payload["holdout"])})
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization-id", type=UUID, required=True)
    parser.add_argument("--workspace-id", type=UUID, required=True)
    parser.add_argument("--qa", type=Path, default=DEFAULT_QA)
    parser.add_argument("--out", type=Path, default=Path("../artifacts/calib_scores.json"))
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
