"""Compatibility imports; new callers should use raghub_core.domain.providers.errors."""

from raghub_core.domain.providers.errors import (
    ProviderAuthenticationError as ProviderAuthenticationError,
)
from raghub_core.domain.providers.errors import (
    ProviderConfigurationError as ProviderConfigurationError,
)
from raghub_core.domain.providers.errors import (
    ProviderDisabledError as ProviderDisabledError,
)
from raghub_core.domain.providers.errors import (
    ProviderError as ProviderError,
)
from raghub_core.domain.providers.errors import (
    ProviderInvalidResponseError as ProviderInvalidResponseError,
)
from raghub_core.domain.providers.errors import (
    ProviderRateLimitError as ProviderRateLimitError,
)
from raghub_core.domain.providers.errors import (
    ProviderTimeoutError as ProviderTimeoutError,
)
from raghub_core.domain.providers.errors import (
    ProviderUnavailableError as ProviderUnavailableError,
)
