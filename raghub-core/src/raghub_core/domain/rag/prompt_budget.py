"""Global prompt-token budget: system/question first, history capped, context rest.

Priority: system guardrail + current question are never cut (oversize is a
validation error, never a silent truncation). History keeps at most 25% of
the input budget as newest-first intact user/assistant pairs, re-emitted in
chronological order. Retrieved context fills the remainder whole-chunk;
only the first chunk may be cut when nothing fits, and citations then
reflect exactly the sent slice.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from raghub_core.domain.errors import CoreError
from raghub_core.domain.providers.contracts import ChatMessage

Counter = Callable[[str], int]
HISTORY_BUDGET_RATIO = 0.25


@dataclass(frozen=True)
class ContextSlice:
    index: int
    text: str
    truncated: bool


@dataclass(frozen=True)
class BudgetedPrompt:
    system_text: str
    question: str
    history: tuple[ChatMessage, ...]
    context_slices: tuple[ContextSlice, ...]
    input_budget: int
    used_tokens: int


def _pair_history(history: Sequence[ChatMessage]) -> list[tuple[ChatMessage, ...]]:
    """Group trailing messages into newest-first (user, assistant) pairs."""
    items = list(history)
    pairs: list[tuple[ChatMessage, ...]] = []
    index = len(items)
    while index > 0:
        if index >= 2:
            pairs.append((items[index - 2], items[index - 1]))
            index -= 2
        else:
            pairs.append((items[index - 1],))
            index -= 1
    return pairs


def _cut_to_fit(chunk: str, remaining: int, count_tokens: Counter) -> str:
    """Keep the longest word-boundary prefix fitting the budget, else char prefix."""
    words = chunk.split()
    kept: list[str] = []
    for word in words:
        trial = " ".join([*kept, word])
        if count_tokens(trial) <= remaining:
            kept.append(word)
        else:
            break
    if kept:
        return " ".join(kept)
    low, high, best = 1, len(chunk), ""
    while low <= high:
        mid = (low + high) // 2
        if count_tokens(chunk[:mid]) <= remaining:
            best = chunk[:mid]
            low = mid + 1
        else:
            high = mid - 1
    return best


class PromptBudgeter:
    def __init__(
        self,
        *,
        context_window: int,
        max_output_tokens: int = 1024,
        safety_margin: int = 256,
        history_ratio: float = HISTORY_BUDGET_RATIO,
        count_tokens: Counter | None = None,
    ) -> None:
        from raghub_core.domain.rag.model_profile import validate_budget_config

        self.input_budget = validate_budget_config(
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            safety_margin=safety_margin,
        )
        self.max_output_tokens = max_output_tokens
        self.safety_margin = safety_margin
        self.history_ratio = history_ratio
        self.count_tokens = count_tokens or (lambda text: max(1, len(text or "") // 4))

    def budget(
        self,
        *,
        system_text: str,
        question: str,
        history: Sequence[ChatMessage] = (),
        context_chunks: Sequence[str] = (),
    ) -> BudgetedPrompt:
        system_tokens = self.count_tokens(system_text)
        question_tokens = self.count_tokens(question)
        if system_tokens + question_tokens > self.input_budget:
            raise CoreError(
                "PROMPT_BUDGET_EXCEEDED",
                "System prompt and question exceed the model input budget.",
            )
        history_allowance = int(self.input_budget * self.history_ratio)
        kept_pairs: list[tuple[ChatMessage, ...]] = []
        used_history = 0
        for pair in _pair_history(history):
            cost = sum(self.count_tokens(message.content or "") for message in pair)
            if used_history + cost <= history_allowance:
                kept_pairs.append(pair)
                used_history += cost
            else:
                break
        kept_pairs.reverse()
        kept_history = tuple(message for pair in kept_pairs for message in pair)
        remaining = self.input_budget - system_tokens - question_tokens - used_history
        slices: list[ContextSlice] = []
        used_context = 0
        for position, chunk in enumerate(context_chunks):
            cost = self.count_tokens(chunk)
            if used_context + cost <= remaining:
                slices.append(ContextSlice(position, chunk, False))
                used_context += cost
            elif not slices and remaining > 0:
                # Only the first chunk may be cut, and only if nothing fits.
                cut = _cut_to_fit(chunk, remaining, self.count_tokens)
                if cut:
                    slices.append(ContextSlice(position, cut, True))
                    used_context += self.count_tokens(cut)
                break
            else:
                break
        return BudgetedPrompt(
            system_text=system_text,
            question=question,
            history=kept_history,
            context_slices=tuple(slices),
            input_budget=self.input_budget,
            used_tokens=system_tokens + question_tokens + used_history + used_context,
        )
