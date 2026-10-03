from contextlib import aclosing

from app.composition.self_host import SelfHostContainer
from app.delivery.security.public_chat import PublicChatResolver
from app.modules.chatbots.embed import public_config


def public_chat_resolver(session) -> PublicChatResolver:
    return PublicChatResolver(session)


class PublicChatContainer:
    def __init__(self, session):
        self.resolver = PublicChatResolver(session)
        self.runtime = SelfHostContainer(session)

    async def resolve(self, raw_key, origin):
        return await self.resolver.resolve(raw_key, origin)

    async def config(self, raw_key, origin):
        return public_config(await self.resolve(raw_key, origin))

    def stream_chat(self):
        return self.runtime.stream_chat()

    async def stream_events(self, command):
        async with aclosing(self.stream_chat().execute(command)) as events:
            async for event in events:
                yield event
