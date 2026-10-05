from raghub_core.domain.chatbots.models import ChatbotRecord, CreateChatbotCommand
from raghub_core.domain.errors import CoreError


def validate_chatbot_configuration(config: ChatbotRecord | CreateChatbotCommand) -> None:
    if not config.name.strip() or len(config.name) > 200:
        raise CoreError(
            "INVALID_CHATBOT_CONFIG", "Chatbot name is required and must be at most 200 characters."
        )
    if not 1 <= config.retrieval_limit <= 10 or len(config.system_prompt) > 12_000:
        raise CoreError(
            "INVALID_CHATBOT_CONFIG", "Chatbot retrieval or prompt configuration is invalid."
        )
