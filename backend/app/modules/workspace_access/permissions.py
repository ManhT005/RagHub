"""Host-owned workspace capabilities; these never grant system administration."""

from app.core.exceptions import AppError

PERMISSIONS = (
    "workspace.view",
    "workspace.edit",
    "document.view",
    "document.upload",
    "document.reindex",
    "document.delete",
    "chat.use",
    "ai.view",
    "ai.change_embedding",
    "member.view",
    "member.manage",
)
DEPENDENCIES = {
    "workspace.edit": "workspace.view",
    "document.upload": "document.view",
    "document.reindex": "document.view",
    "document.delete": "document.view",
    "ai.change_embedding": "ai.view",
    "member.manage": "member.view",
}


def normalize_permissions(values: list[str]) -> list[str]:
    if set(values) - set(PERMISSIONS):
        raise AppError(
            "INVALID_WORKSPACE_PERMISSION", "Unknown workspace permission.", status_code=422
        )
    result = set(values) | {"workspace.view"}
    result.update(DEPENDENCIES[value] for value in values if value in DEPENDENCIES)
    return [permission for permission in PERMISSIONS if permission in result]
