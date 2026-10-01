from app.modules.ai_providers.contracts import ChatMessage, ChatUsage
from app.modules.ingestion.tokenizer import ENCODING


def estimate_chat_usage(messages: list[ChatMessage], completion: str) -> ChatUsage:
    prompt_tokens = sum(len(ENCODING.encode(message.content)) + 4 for message in messages) + 2
    completion_tokens = len(ENCODING.encode(completion))
    return ChatUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        source="estimated",
    )
