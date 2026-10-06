"""Evaluation metrics for RAG golden suite (Phase 1 baseline).

Pure functions only: no I/O, no network, no provider calls.
Used by both pytest and the offline baseline runner.
"""

from __future__ import annotations

import math


def hit_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int = 5) -> float:
    top = retrieved_ids[:k]
    return 1.0 if any(item in expected_ids for item in top) else 0.0


def mrr_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int = 5) -> float:
    for rank, item in enumerate(retrieved_ids[:k], start=1):
        if item in expected_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved_ids: list[str],
    relevance: dict[str, float],
    k: int = 5,
) -> float:
    def dcg(ids: list[str]) -> float:
        total = 0.0
        for rank, item in enumerate(ids, start=1):
            rel = relevance.get(item, 0.0)
            if rel > 0:
                total += (2**rel - 1) / math.log2(rank + 1)
        return total

    top = retrieved_ids[:k]
    ideal = sorted(relevance, key=lambda key: relevance[key], reverse=True)[:k]
    ideal_dcg = dcg(ideal)
    if ideal_dcg == 0:
        return 0.0
    return dcg(top) / ideal_dcg


def rejection_scores(
    *,
    predicted_unanswerable: list[bool],
    actual_unanswerable: list[bool],
) -> dict[str, float]:
    zipped = list(zip(predicted_unanswerable, actual_unanswerable, strict=False))
    tp = sum(1 for p, a in zipped if p and a)
    fp = sum(1 for p, a in zipped if p and not a)
    fn = sum(1 for p, a in zipped if not p and a)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def citation_precision(
    *,
    cited_ids: list[str],
    inventory_ids: set[str],
    supporting_ids: set[str],
) -> float:
    """Fraction of emitted citations that are valid AND support the claim."""
    if not cited_ids:
        return 1.0
    good = sum(1 for cid in cited_ids if cid in inventory_ids and cid in supporting_ids)
    return good / len(cited_ids)


def citation_coverage(*, supported_claims: int, total_claims: int) -> float:
    if total_claims == 0:
        return 1.0
    return supported_claims / total_claims


def fact_support_scores(
    *, expected_facts: list[dict], observed_facts: list[dict], inventory_chunk_ids: set[str]
) -> dict[str, float | None]:
    """Score reviewed fact-to-source mappings independently from citation ID validity.

    Fact labels identify reviewer-matched claims, not automatic semantic judgments.
    Missing annotations are unavailable evidence, never a passing score.
    """
    if not expected_facts:
        return {"citation_support_precision": None, "fact_support_recall": None}
    support = {fact["fact"]: set(fact["supporting_chunk_ids"]) for fact in expected_facts}
    if len(support) != len(expected_facts) or any(not ids for ids in support.values()):
        raise ValueError("Expected facts need unique labels and supporting chunks.")
    cited, supported, recalled = 0, 0, set()
    for claim in observed_facts:
        chunks = set(claim.get("cited_chunk_ids", []))
        good = chunks & inventory_chunk_ids & support.get(claim["fact"], set())
        cited += len(chunks)
        supported += len(good)
        if good:
            recalled.add(claim["fact"])
    return {
        "citation_support_precision": supported / cited if cited else None,
        "fact_support_recall": len(recalled) / len(expected_facts),
    }
