"""Compatibility imports; new callers should use app.core_domain.providers.errors."""

from app.core_domain.providers.errors import (
    ProviderAuthenticationError as ProviderAuthenticationError,
)
from app.core_domain.providers.errors import (
    ProviderConfigurationError as ProviderConfigurationError,
)
from app.core_domain.providers.errors import (
    ProviderDisabledError as ProviderDisabledError,
)
from app.core_domain.providers.errors import (
    ProviderError as ProviderError,
)
from app.core_domain.providers.errors import (
    ProviderInvalidResponseError as ProviderInvalidResponseError,
)
from app.core_domain.providers.errors import (
    ProviderRateLimitError as ProviderRateLimitError,
)
from app.core_domain.providers.errors import (
    ProviderTimeoutError as ProviderTimeoutError,
)
from app.core_domain.providers.errors import (
    ProviderUnavailableError as ProviderUnavailableError,
)
