"""Default domain-independent clarification policy."""
from raghub_core.domain.rag.intent import IntentAction, IntentDecision


class ClarificationPolicy:
    def evaluate(
        self, question: str, *, domain_profile: str = "generic",
        mode: str = "conservative", clarifying_turns: int = 0,
        max_clarifying_turns: int = 1, retrieval_confidence: float | None = None,
    ) -> IntentDecision:
        if mode not in {"off", "conservative", "proactive"}:
            raise ValueError("mode must be one of: off, conservative, proactive")
        return IntentDecision(IntentAction.ANSWER_NOW, reason="generic_policy")

    def is_clarification(self, text: str) -> bool:
        return False
