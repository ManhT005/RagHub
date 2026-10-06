"""Deterministic evidence selection using rank, coverage, redundancy and token cost."""

import re
from dataclasses import replace

from raghub_core.domain.ingestion.tokenizer import ENCODING
from raghub_core.domain.retrieval.hybrid import normalize_query, render_citation_block


def _words(text):
    return set(re.findall(r"\w+", normalize_query(text).casefold()))


def _trim_overlap(hit, selected):
    if hit.metadata.get("header"):
        return hit
    matches = list(re.finditer(r"\S+", hit.content))
    words = [m.group().casefold() for m in matches]
    for prior in selected:
        if (
            prior.document_version_id != hit.document_version_id
            or prior.chunk_index is None
            or hit.chunk_index != prior.chunk_index + 1
        ):
            continue
        earlier = [m.casefold() for m in prior.content.split()]
        for length in range(min(len(earlier), len(words) - 1), 7, -1):
            if earlier[-length:] == words[:length]:
                return replace(
                    hit, content=hit.content[matches[length].start() :], normalized_content=None
                )
    return hit


def select_evidence(query, hits, limit, *, max_tokens=6000, max_per_document=None):
    if limit <= 0 or max_tokens <= 0:
        return []
    candidates, seen = [], set()
    for rank, hit in enumerate(hits):
        text = normalize_query(hit.normalized_content or hit.content)
        identity = (text, hit.metadata.get("row_start"), hit.metadata.get("row_end"))
        if not text or hit.chunk_id in seen or identity in seen:
            continue
        seen.update((hit.chunk_id, identity))
        candidates.append((rank, hit))
    terms, covered, documents, selected = _words(query), set(), {}, []
    used = 0
    while candidates and len(selected) < limit:
        options = []
        for rank, original in candidates:
            if max_per_document and documents.get(original.document_id, 0) >= max_per_document:
                continue
            hit = _trim_overlap(original, selected)
            cost = len(ENCODING.encode(render_citation_block(len(selected) + 1, hit)))
            if used + cost > max_tokens:
                continue
            new_terms = (_words(hit.content) & terms) - covered
            gain = (
                0.6 / (rank + 1)
                + 0.3 * len(new_terms) / max(1, len(terms))
                + 0.1 * (original.document_id not in documents)
            ) / (1 + cost / max_tokens)
            options.append((gain, -rank, hit, cost, original.chunk_id))
        if not options:
            break
        _, _, hit, cost, chosen = max(options, key=lambda item: item[:2])
        selected.append(hit)
        covered.update(_words(hit.content) & terms)
        documents[hit.document_id] = documents.get(hit.document_id, 0) + 1
        used += cost
        candidates = [
            (rank, candidate) for rank, candidate in candidates if candidate.chunk_id != chosen
        ]
    # The final rendered prompt budgeter owns truncation when no whole evidence fits.
    return selected or ([candidates[0][1]] if candidates else [])
