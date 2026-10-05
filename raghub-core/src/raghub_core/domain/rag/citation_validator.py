"""Post-stream citation validation (metric/release gate, never blocks stream).

Parses [Cn] markers from the completed answer and reports used IDs, invalid
IDs (outside the sent inventory), cited/uncited factual spans. Whether a
citation actually *supports* its claim is a nightly-evaluator verdict, not
a deterministic check; here invalid-ID and coverage are hard signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_RE = re.compile(r"\[C(\d+)\]")


@dataclass(frozen=True)
class CitationReport:
    used_ids: tuple[str, ...]
    invalid_ids: tuple[str, ...]
    cited_spans: int
    uncited_spans: int

    @property
    def coverage(self) -> float:
        total = self.cited_spans + self.uncited_spans
        return self.cited_spans / total if total else 1.0


def _split_spans(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", answer or "")
    return [part.strip() for part in parts if part.strip()]


def validate_citations(answer: str, *, inventory_ids: set[str]) -> CitationReport:
    used: list[str] = []
    for match in CITATION_RE.finditer(answer or ""):
        citation_id = f"C{int(match.group(1))}"
        if citation_id not in used:
            used.append(citation_id)
    invalid = tuple(cid for cid in used if cid not in inventory_ids)
    cited = uncited = 0
    for span in _split_spans(answer):
        if CITATION_RE.search(span):
            cited += 1
        else:
            uncited += 1
    return CitationReport(
        used_ids=tuple(used),
        invalid_ids=invalid,
        cited_spans=cited,
        uncited_spans=uncited,
    )
