"""Offline golden baseline runner (compare-only, no thresholds enforced).

Reads committed fixtures, runs a deterministic lexical retriever over the
local corpus (no ES, no paid provider), and writes a baseline JSON with
commit + dataset/config hashes + per-case metrics.

Usage (from backend/):
    python scripts/rag_golden_eval.py --out ../artifacts/rag_golden_baseline.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raghub_core.domain.evaluation.metrics import hit_at_k, mrr_at_k, ndcg_at_k  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
GOLDEN = BACKEND / "tests" / "fixtures" / "rag_golden"
TOKEN_RE = re.compile(r"[a-z0-9\u00e0-\u1ef9]+")


def tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall(text.lower()))


def dataset_hash() -> str:
    h = hashlib.sha256()
    for path in sorted((GOLDEN).rglob("*")):
        if path.is_file():
            h.update(path.relative_to(GOLDEN).as_posix().encode())
            h.update(path.read_bytes())
    return h.hexdigest()[:16]


def config_hash() -> str:
    cfg = {"retrieval_candidates": 25, "rrf_k": 60, "max_context_tokens": 6000}
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:16]


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(BACKEND.parent),
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    manifest = json.loads((GOLDEN / "corpus_manifest.json").read_text(encoding="utf-8"))
    qa = json.loads((GOLDEN / "qa.json").read_text(encoding="utf-8"))
    docs = {}
    for entry in manifest["documents"]:
        docs[entry["document_id"]] = (GOLDEN / entry["file"]).read_text(encoding="utf-8")
    doc_tokens = {doc_id: tokenize(text) for doc_id, text in docs.items()}

    cases = []
    for item in qa:
        q_tokens = tokenize(item["question"])
        ranked = sorted(
            docs,
            key=lambda d: (-len(q_tokens & doc_tokens[d]), d),
        )
        expected = set(item["expected_document_ids"])
        relevance = {d: 1.0 for d in expected}
        cases.append(
            {
                "id": item["id"],
                "answerable": item["answerable"],
                "retrieved_top5": ranked[:5],
                "hit@5": hit_at_k(ranked, expected),
                "mrr@5": mrr_at_k(ranked, expected),
                "ndcg@5": ndcg_at_k(ranked, relevance),
            }
        )

    answerable = [c for c in cases if next(q for q in qa if q["id"] == c["id"])["answerable"]]
    summary = {
        "hit@5": sum(c["hit@5"] for c in cases) / len(cases),
        "mrr@5": sum(c["mrr@5"] for c in cases) / len(cases),
        "ndcg@5": sum(c["ndcg@5"] for c in cases) / len(cases),
        "answerable_hit@5": sum(c["hit@5"] for c in answerable) / len(answerable),
    }
    report = {
        "corpus_revision": "golden-v1",
        "mode": "compare-only-baseline",
        "thresholds_enforced": False,
        "commit": git_sha(),
        "dataset_hash": dataset_hash(),
        "config_hash": config_hash(),
        "model_ids": {"embedding": "offline-lexical-v1", "chat": "none"},
        "seed": args.seed,
        "retrieval_config": {"candidates": 25, "rrf_k": 60, "max_context_tokens": 6000},
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": summary,
        "cases": cases,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
