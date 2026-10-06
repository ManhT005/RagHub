"""Post-stream citation validation (metric/release gate, never blocks stream).

Parses [Cn] markers from the completed answer — single ([C1]), grouped
([C1, C2]) and adjacent ([C1][C2]) forms — and reports used IDs, invalid
IDs (outside the sent inventory), cited/uncited factual spans. Whether a
citation actually *supports* its claim is a nightly-evaluator verdict, not
a deterministic check; here invalid-ID and coverage are hard signals.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_RE = re.compile(r"\[C(\d+)\]")
CITATION_GROUP_RE = re.compile(r"\[([Cc]\d+(?:\s*,\s*[Cc]?\d+)*)\]")


def _iter_citation_ids(answer: str):
    for match in CITATION_RE.finditer(answer or ""):
        yield f"C{int(match.group(1))}"
    for match in CITATION_GROUP_RE.finditer(answer or ""):
        for part in match.group(1).split(","):
            part = part.strip().lstrip("Cc")
            if part.isdigit():
                yield f"C{int(part)}"


def _has_citation(span: str) -> bool:
    return CITATION_RE.search(span) is not None or CITATION_GROUP_RE.search(span) is not None


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
    for citation_id in _iter_citation_ids(answer):
        if citation_id not in used:
            used.append(citation_id)
    invalid = tuple(cid for cid in used if cid not in inventory_ids)
    cited = uncited = 0
    for span in _split_spans(answer):
        if _has_citation(span):
            cited += 1
        else:
            uncited += 1
    return CitationReport(
        used_ids=tuple(used),
        invalid_ids=invalid,
        cited_spans=cited,
        uncited_spans=uncited,
    )
