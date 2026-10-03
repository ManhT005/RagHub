"""Compatibility imports; new callers should use app.core_domain.retrieval.hybrid."""

from app.core_domain.retrieval.hybrid import (
    MAX_CONTEXT_TOKENS as MAX_CONTEXT_TOKENS,
)
from app.core_domain.retrieval.hybrid import (
    RETRIEVAL_CANDIDATES as RETRIEVAL_CANDIDATES,
)
from app.core_domain.retrieval.hybrid import (
    RRF_K as RRF_K,
)
from app.core_domain.retrieval.hybrid import (
    ContextBundle as ContextBundle,
)
from app.core_domain.retrieval.hybrid import (
    build_context as build_context,
)
from app.core_domain.retrieval.hybrid import (
    build_context_bundle as build_context_bundle,
)
from app.core_domain.retrieval.hybrid import (
    fuse_rrf as fuse_rrf,
)
