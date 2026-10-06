from uuid import uuid4

import pytest

from raghub_core.domain.providers.contracts import ChatMessage
from raghub_core.domain.rag.citations import render_sliced_bundle
from raghub_core.domain.rag.model_profile import count_tokens_exact
from raghub_core.domain.rag.prompt import build_prompt
from raghub_core.domain.rag.prompt_budget import PromptBudgeter
from raghub_core.domain.retrieval.models import RetrievedChunk


@pytest.mark.parametrize("window", [512, 8192, 128000])
def test_budget_counts_final_wrapper_and_preserves_citation_slice(window):
    hits = [
        RetrievedChunk(
            uuid4(),
            uuid4(),
            uuid4(),
            "knowledge " * 2000,
            "very-long-name " * 5,
            123,
            "heading " * 20,
            0.03,
        )
    ]
    budgeter = PromptBudgeter(
        context_window=window,
        max_output_tokens=128,
        safety_margin=16,
        count_tokens=count_tokens_exact,
    )

    def render(slices, history):
        return build_prompt(
            "Follow evidence.",
            "question",
            render_sliced_bundle(hits, [(s.index, s.text) for s in slices]),
            history,
        )

    budget = budgeter.budget(
        system_text="Follow evidence.",
        question="question",
        history=[ChatMessage("user", "earlier " * 500)],
        context_chunks=[hits[0].content],
        render_prompt=render,
    )
    messages = render(budget.context_slices, budget.history)
    actual = sum(count_tokens_exact(m.content) for m in messages)
    assert actual == budget.used_tokens <= budget.input_budget
    for slice in budget.context_slices:
        assert slice.text in messages[0].content
    assert "CONTEXT:" in messages[0].content


def test_history_cannot_overrun_remaining_input_budget():
    budgeter = PromptBudgeter(
        context_window=100, max_output_tokens=10, safety_margin=0, count_tokens=len
    )
    result = budgeter.budget(
        system_text="s" * 80, question="q" * 5, history=[ChatMessage("user", "h" * 20)]
    )
    assert result.used_tokens <= result.input_budget
    assert not result.history


@pytest.mark.parametrize("rendered", [False, True])
def test_evidence_is_preserved_before_older_history(rendered):
    budgeter = PromptBudgeter(
        context_window=100, max_output_tokens=10, safety_margin=0, count_tokens=len
    )

    def render(slices, history):
        return [
            ChatMessage("system", "s" * 5 + "".join(s.text for s in slices)),
            *history,
            ChatMessage("user", "q" * 5),
        ]

    result = budgeter.budget(
        system_text="s" * 5,
        question="q" * 5,
        context_chunks=["e" * 70],
        history=[ChatMessage("user", "h" * 9), ChatMessage("assistant", "a" * 9)],
        render_prompt=render if rendered else None,
    )
    assert result.context_slices[0].text == "e" * 70
    assert not result.context_slices[0].truncated and not result.history
    assert result.used_tokens == 80
