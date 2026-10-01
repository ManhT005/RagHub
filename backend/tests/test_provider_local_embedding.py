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
