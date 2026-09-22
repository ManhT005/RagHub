"""Import every SQLAlchemy model so shared metadata is complete in each process."""

from app.modules.documents.models import Document, DocumentVersion, IngestionJob
from app.modules.memberships.models import Membership
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace

__all__ = [
    "Document",
    "DocumentVersion",
    "IngestionJob",
    "Membership",
    "Organization",
    "User",
    "Workspace",
]
