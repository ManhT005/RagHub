import uuid
from types import SimpleNamespace

from app.workers.reindex_tasks import _is_current_target


def test_only_latest_pending_index_is_allowed_to_activate() -> None:
    older = SimpleNamespace(id=uuid.uuid4())
    newer = SimpleNamespace(id=uuid.uuid4())
    workspace = SimpleNamespace(pending_embedding_index_version_id=newer.id)

    assert not _is_current_target(workspace, older)  # type: ignore[arg-type]
    assert _is_current_target(workspace, newer)  # type: ignore[arg-type]
