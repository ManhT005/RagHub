from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError,
    ProviderUnavailableError,
)


class PoolEmbeddingProvider:
    """Fail over credentials within one validated, immutable semantic profile."""

    def __init__(self, providers, credentials, session, mark_unhealthy=None):
        self.providers, self.credentials, self.session = providers, credentials, session
        self.metadata = providers[0].metadata
        self.mark_unhealthy = mark_unhealthy

    async def _call(self, method, payload):
        failure = None
        for provider, credential in zip(self.providers, self.credentials, strict=True):
            if credential.unhealthy or not credential.enabled:
                continue
            try:
                return await getattr(provider, method)(payload)
            except ProviderAuthenticationError as exc:
                if self.mark_unhealthy is not None:
                    await self.mark_unhealthy(credential)
                credential.unhealthy = True
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
