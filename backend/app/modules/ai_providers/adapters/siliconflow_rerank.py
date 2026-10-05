from app.modules.ai_providers.adapters.rerank import JsonRerankProvider


class SiliconFlowRerankProvider(JsonRerankProvider):
    def __init__(self, **kwargs):
        super().__init__(provider_name="SILICONFLOW", **kwargs)
