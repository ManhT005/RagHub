from app.delivery.security.public_chat import PublicChatResolver


def public_chat_resolver(session) -> PublicChatResolver:
    return PublicChatResolver(session)
