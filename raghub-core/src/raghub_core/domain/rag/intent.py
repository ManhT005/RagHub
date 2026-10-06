from dataclasses import dataclass
from enum import StrEnum


class IntentAction(StrEnum):
    ANSWER_NOW = "answer_now"
    CLARIFY = "clarify"
    REFUSE_OR_REDIRECT = "refuse_or_redirect"


@dataclass(frozen=True)
class IntentDecision:
    action: IntentAction
    missing_slots: tuple[str, ...] = ()
    suggestions: tuple[str, ...] = ()
    reason: str = ""
    message: str = ""