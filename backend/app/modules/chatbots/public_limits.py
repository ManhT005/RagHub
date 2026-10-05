"""Deprecated imports for hosts upgrading from the module-based admission adapter."""

from app.delivery.public.admission import (
    client_ip as client_ip,
)
from app.delivery.public.admission import (
    get_public_limits as get_public_limits,
)
from app.infrastructure.redis.public_chat_admission import PublicChatLimits as PublicChatLimits
