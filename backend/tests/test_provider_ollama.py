from app.modules.ai_providers.adapters.ollama import OllamaChatProvider
from app.modules.ai_providers.contracts import ChatProvider


def test_ollama_implements_common_chat_contract() -> None:
    provider = OllamaChatProvider(base_url="http://ollama:11434", model="llama3.2")

    assert isinstance(provider, ChatProvider)
    assert provider.provider_name == "OLLAMA"
    assert provider.model == "llama3.2"
