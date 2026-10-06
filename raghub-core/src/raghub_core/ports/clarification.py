from typing import Protocol

from raghub_core.domain.rag.intent import IntentDecision


class ClarificationPolicyPort(Protocol):
    def evaluate(
        self,
        question: str,
        *,
        domain_profile: str,
        mode: str,
        clarifying_turns: int,
        max_clarifying_turns: int,
        retrieval_confidence: float | None = None,
    ) -> IntentDecision: ...

    def is_clarification(self, text: str) -> bool: ...
