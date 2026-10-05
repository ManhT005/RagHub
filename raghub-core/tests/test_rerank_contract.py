import pytest

from raghub_core.domain.providers.contracts import RerankItem, RerankResult
from raghub_core.domain.providers.errors import ProviderInvalidResponseError
from raghub_core.domain.providers.rerank import validated_rerank_indices


def result(items):
    return RerankResult([RerankItem(*item) for item in items], "model", "runtime")


def test_rerank_order_is_deterministic_and_uses_original_indices():
    assert validated_rerank_indices(result([(0, 0.3), (2, 0.9), (1, 0.5)]), 3, 2) == [2, 1]


@pytest.mark.parametrize(
    "items",
    [
        [],
        [(3, 0.5)],
        [(-1, 0.5)],
        [(0, float("nan"))],
        [(0, float("inf"))],
        [(0, 0.5), (0, 0.8)],
        [(True, 0.5)],
        [(0, True)],
    ],
)
def test_malformed_rerank_results_never_change_context(items):
    with pytest.raises(ProviderInvalidResponseError):
        validated_rerank_indices(result(items), 3, 1)
