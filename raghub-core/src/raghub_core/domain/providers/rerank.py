"""Vendor-independent rerank validation; returned text never replaces retrieved source content."""

import math

from raghub_core.domain.providers.contracts import RerankResult
from raghub_core.domain.providers.errors import ProviderInvalidResponseError


def validated_rerank_indices(result: RerankResult, count: int, top_n: int) -> list[int]:
    expected = min(count, top_n)
    if len(result.items) < expected or len(result.items) > count:
        raise ProviderInvalidResponseError("Rerank result count does not match the request.")
    seen = set()
    for item in result.items:
        if (
            type(item.index) is not int
            or not 0 <= item.index < count
            or item.index in seen
            or isinstance(item.score, bool)
            or not isinstance(item.score, int | float)
            or not math.isfinite(item.score)
        ):
            raise ProviderInvalidResponseError("Rerank indices or scores are invalid.")
        seen.add(item.index)
    return [
        item.index
        for item in sorted(result.items, key=lambda item: item.score, reverse=True)[:expected]
    ]
