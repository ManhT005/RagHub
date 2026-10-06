import pytest
from pydantic import ValidationError

from app.modules.chatbots.schemas import ChatbotInput, ChatbotPatch


def test_chatbot_clarification_defaults_are_backward_compatible() -> None:
    payload = ChatbotInput(name="Admissions bot")

    assert payload.clarification_mode == "conservative"
    assert payload.max_clarifying_turns == 1
    assert payload.domain_profile == "generic"


def test_chatbot_clarification_accepts_three_modes() -> None:
    for mode in ("off", "conservative", "proactive"):
        payload = ChatbotInput(name="Admissions bot", clarification_mode=mode)
        assert payload.clarification_mode == mode


def test_chatbot_clarification_rejects_invalid_mode() -> None:
    with pytest.raises(ValidationError):
        ChatbotInput(name="Admissions bot", clarification_mode="aggressive")


def test_chatbot_clarification_rejects_invalid_turn_limit() -> None:
    with pytest.raises(ValidationError):
        ChatbotPatch(max_clarifying_turns=-1)
    with pytest.raises(ValidationError):
        ChatbotPatch(max_clarifying_turns=6)