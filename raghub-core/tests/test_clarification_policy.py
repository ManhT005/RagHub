import pytest

from raghub_core.domain.rag.clarification import ClarificationPolicy
from raghub_core.domain.rag.intent import IntentAction


def test_default_policy_is_domain_independent():
    for profile in ("generic", "custom"):
        decision = ClarificationPolicy().evaluate("Where is the document?", domain_profile=profile)
        assert decision.action is IntentAction.ANSWER_NOW


def test_invalid_mode_is_rejected():
    with pytest.raises(ValueError):
        ClarificationPolicy().evaluate("question", mode="invalid")
