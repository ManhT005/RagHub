from __future__ import annotations

import hashlib
import secrets
from html import escape
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.delivery.security.origins import origin_is_allowed as origin_is_allowed
from app.modules.chatbots.schemas import EmbedCodeResponse

if TYPE_CHECKING:
    from app.modules.chatbots.models import Chatbot


def create_embed_key() -> tuple[str, str]:
    raw_key = f"rgh_{secrets.token_urlsafe(32)}"
    return raw_key, hashlib.sha256(raw_key.encode()).hexdigest()


def hash_embed_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def embed_response(key: str | None = None, *, has_embed_key: bool = False) -> EmbedCodeResponse:
    base_url = get_settings().public_base_url
    if not base_url:
        raise AppError(
            "PUBLIC_BASE_URL_NOT_CONFIGURED",
            "Configure PUBLIC_BASE_URL with the public RagHub HTTP(S) origin.",
            status_code=503,
        )
    script_src = f"{base_url}/widget/raghub.js"
    return EmbedCodeResponse(
        code=(
            f'<script src="{escape(script_src, quote=True)}" charset="utf-8" '
            f'data-chatbot-key="{escape(key, quote=True)}" async></script>'
            if key
            else None
        ),
        key=key,
        script_src=script_src,
        public_base_url=base_url,
        has_embed_key=has_embed_key or key is not None,
    )


def public_config(chatbot: Chatbot) -> dict[str, str]:
    return {
        "name": chatbot.name,
        "primary_color": chatbot.embed_primary_color,
        "title": chatbot.embed_title,
        "greeting": chatbot.embed_greeting,
    }
