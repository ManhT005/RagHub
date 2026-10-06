from app.modules.ai_providers.adapters.sentence_transformer import (
    LocalSentenceTransformerProvider,
)


class FakeEncoded:
    def __init__(self, values: list[list[float]]) -> None:
        self.values = values

    def tolist(self) -> list[list[float]]:
        return self.values


class FakeModel:
    calls = 0

    def encode(self, texts: list[str], **_kwargs: object) -> FakeEncoded:
        self.calls += 1
        return FakeEncoded([[1.0, 0.0] for _ in texts])


async def test_local_embedding_runs_blocking_model_and_checks_dimension() -> None:
    model = FakeModel()
    provider = LocalSentenceTransformerProvider(
        model="local-model", dimension=2, model_loader=lambda _name: model
    )

    assert await provider.embed_query("query") == [1.0, 0.0]
    assert await provider.embed_documents(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    assert model.calls == 2


async def test_cancelled_query_keeps_capacity_until_native_inference_finishes():
    import asyncio
    import threading

    import pytest

    entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()

    class BlockingModel:
        calls = 0

        def encode(self, texts, **kwargs):
            self.calls += 1
            if self.calls == 1:
                entered.set()
                assert release.wait(3)
            else:
                second_entered.set()
            return FakeEncoded([[1.0, 0.0] for _ in texts])

    model = BlockingModel()
    provider = LocalSentenceTransformerProvider(
        model="cancel-test", dimension=2, max_concurrency=1, model_loader=lambda _: model
    )
    first = asyncio.create_task(provider.embed_query("first"))
    assert await asyncio.to_thread(entered.wait, 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(provider.embed_query("second"))
    try:
        await asyncio.sleep(0.05)
        assert not second_entered.is_set()
    finally:
        release.set()
    assert await asyncio.wait_for(second, 2) == [1.0, 0.0]
