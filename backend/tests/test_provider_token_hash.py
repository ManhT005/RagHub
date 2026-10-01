from app.modules.ai_providers.adapters.token_hash import LocalTokenHashEmbeddingProvider


async def test_token_hash_embedding_is_deterministic_and_normalized() -> None:
    provider = LocalTokenHashEmbeddingProvider(model="token-hash-v1", dimension=32)

    first = await provider.embed_query("repeatable integration text")
    second = await provider.embed_query("repeatable integration text")

    assert first == second
    assert len(first) == 32
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9
