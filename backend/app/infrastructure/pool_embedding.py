from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderUnavailableError,
)


class PoolEmbeddingProvider:
    """Fail over credentials within one validated, immutable semantic profile."""

    def __init__(self, providers, credentials, session):
        self.providers, self.credentials, self.session = providers, credentials, session
        self.metadata = providers[0].metadata

    async def _call(self, method, payload):
        failure = None
        for provider, credential in zip(self.providers, self.credentials, strict=True):
            if credential.unhealthy or not credential.enabled:
                continue
            try:
                return await getattr(provider, method)(payload)
            except ProviderAuthenticationError as exc:
                credential.unhealthy = True
                await self.session.flush()
                failure = exc
            except ProviderUnavailableError as exc:
                failure = exc
        if failure is not None:
            raise failure
        raise ProviderUnavailableError("No healthy embedding credential in the compatible pool.")

    async def embed_documents(self, texts):
        return await self._call("embed_documents", texts)

    async def embed_query(self, text):
        return await self._call("embed_query", text)
