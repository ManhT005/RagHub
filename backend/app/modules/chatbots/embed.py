from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.chatbots.models import Chatbot


def create_embed_key() -> tuple[str, str]:
    raw_key = f"rgh_{secrets.token_urlsafe(32)}"
    return raw_key, hashlib.sha256(raw_key.encode()).hexdigest()


def hash_embed_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def origin_is_allowed(origin: str | None, allowed_origins: list[str]) -> bool:
    return bool(origin and origin.rstrip("/") in {value.rstrip("/") for value in allowed_origins})


def public_config(chatbot: Chatbot) -> dict[str, str]:
    return {
        "name": chatbot.name,
        "primary_color": chatbot.embed_primary_color,
        "title": chatbot.embed_title,
        "greeting": chatbot.embed_greeting,
    }
