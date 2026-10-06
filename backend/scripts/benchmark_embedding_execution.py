"""Controlled scheduling benchmark: simulated latency, no live provider or model.

Run from backend/: python scripts/benchmark_embedding_execution.py --out <path>
This isolates scheduling from DB/storage/network latency; it does not measure
production throughput or model quality.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import Settings
from app.infrastructure.embedding_execution import resolve_policy
from app.modules.ai_providers.work_items import WorkItemProcessor, encode_manifest


class Repository:
    def __init__(self, item):
        self.item, self.checkpoints, self.first_batch_at = item, {}, None

    async def claim(self, _):
        return self.item

    async def completed_batches(self, _):
        return set(self.checkpoints)

    async def record_batch(self, item, *, batch, start, end, artifact):
        self.first_batch_at = self.first_batch_at or time.perf_counter()
        self.checkpoints[batch] = artifact

    async def checkpoint_artifact(self, _, batch):
        return self.checkpoints.get(batch)

    async def complete(self, item):
        item.state = "COMPLETED"


async def benchmark(provider_type, profile, chunks=192):
    item = SimpleNamespace(
        id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        manifest_key="manifest",
        total_chunks=chunks,
        embedded_chunks=0,
        state="QUEUED",
    )
    repo = Repository(item)
    storage = {
        "manifest": encode_manifest([{"text": f"chunk {i}", "tokens": 10} for i in range(chunks)])
    }
    inflight = peak = requests = 0

    async def embed(texts):
        nonlocal inflight, peak, requests
        inflight += 1
        peak = max(peak, inflight)
        native = provider_type == "GOOGLE_GEMINI"
        requests += len(texts) if native else 1
        try:
            await asyncio.sleep(0.002 * len(texts) if native else 0.015)
            return [[float(text.split()[-1]), 0.0] for text in texts]
        finally:
            inflight -= 1

    async def load(key):
        return storage[key]

    async def store(key, data):
        storage[key] = data

    async def finalize(_, vectors):
        assert vectors == [[float(i), 0.0] for i in range(chunks)]

    async def quota(**_):
        pass

    if profile == "legacy_sequential":
        concurrency, batch_chunks, tokens = 1, 24, 10000
    else:
        policy = resolve_policy(
            Settings(_env_file=None), provider_type, workspace_options={"profile": profile}
        )
        concurrency, batch_chunks, tokens = (
            policy.max_inflight_requests,
            policy.batch_max_chunks,
            policy.batch_target_tokens,
        )
    processor = WorkItemProcessor(
        repo,
        SimpleNamespace(acquire=quota),
        load_blob=load,
        store_blob=store,
        embed_texts=embed,
        finalize=finalize,
        dimension=2,
        max_chunks=batch_chunks,
        target_tokens=tokens,
        max_inflight=concurrency,
    )
    started = time.perf_counter()
    while not (await processor.process_one(item.id)).done:
        pass
    return {
        "provider_type": provider_type,
        "profile": profile,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "first_batch_ms": round((repo.first_batch_at - started) * 1000, 2),
        "provider_request_count": requests,
        "peak_inflight": peak,
        "retry_count": 0,
        "cache_hit_ratio": 0,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    rows = []
    for provider in ("OPENAI_COMPATIBLE", "GOOGLE_GEMINI", "LOCAL_SENTENCE_TRANSFORMER", "OLLAMA"):
        for profile in ("legacy_sequential", "conservative", "balanced", "fast"):
            rows.append(await benchmark(provider, profile))
    report = {
        "measurement": "controlled simulated latency; not a live provider benchmark",
        "timestamp": datetime.now(UTC).isoformat(),
        "chunks": 192,
        "results": rows,
    }
    payload = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    asyncio.run(main())
