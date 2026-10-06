from raghub_core.domain.rag.clarification import ClarificationPolicy

from app.modules.rag_policies.admissions import AdmissionsPolicy


class HostClarificationPolicy:
    def __init__(self):
        self.generic = ClarificationPolicy()
        self.admissions = AdmissionsPolicy()

    def evaluate(self, question, *, domain_profile="generic", **kwargs):
        policy = self.admissions if domain_profile == "admissions" else self.generic
        return policy.evaluate(question, domain_profile=domain_profile, **kwargs)

    def is_clarification(self, text):
        return self.admissions.is_clarification(text)
