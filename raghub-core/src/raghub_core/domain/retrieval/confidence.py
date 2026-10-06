"""Routing is based on calibrated confidence, never raw cross-query scores."""

import math
from enum import StrEnum


class ConfidenceBand(StrEnum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


def confidence_band(decision, *, high_threshold=0.85):
    if (
        not decision
        or not decision.calibrated
        or not math.isfinite(decision.confidence)
        or not 0 <= decision.confidence <= 1
    ):
        return ConfidenceBand.UNKNOWN
    if not decision.accepted:
        return ConfidenceBand.LOW
    return ConfidenceBand.HIGH if decision.confidence >= high_threshold else ConfidenceBand.MEDIUM
