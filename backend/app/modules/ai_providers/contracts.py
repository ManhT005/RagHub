"""Compatibility imports; new callers should use app.core_domain.providers.contracts."""

from app.core_domain.providers.contracts import (
    ChatMessage as ChatMessage,
)
from app.core_domain.providers.contracts import (
    ChatOptions as ChatOptions,
)
from app.core_domain.providers.contracts import (
    ChatProvider as ChatProvider,
)
from app.core_domain.providers.contracts import (
    ChatStreamDelta as ChatStreamDelta,
)
from app.core_domain.providers.contracts import (
    ChatUsage as ChatUsage,
)
from app.core_domain.providers.contracts import (
    EmbeddingMetadata as EmbeddingMetadata,
)
from app.core_domain.providers.contracts import (
    EmbeddingProvider as EmbeddingProvider,
)
from app.core_domain.providers.contracts import (
    ProviderTestResult as ProviderTestResult,
)
