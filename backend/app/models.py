"""Import every SQLAlchemy model so shared metadata is complete in each process."""

from app.modules.ai_providers.models import (
    EmbeddingIndexVersion,
    EmbeddingReindexJob,
    OllamaModelPull,
    ProviderConfig,
    ProviderConnection,
)
from app.modules.auth.models import PasswordResetToken, UserIdentity, UserSession
from app.modules.chatbots.models import Chatbot, Conversation, Message, MessageCitation, UsageEvent
from app.modules.documents.models import (
    Document,
    DocumentIndexMetadata,
    DocumentVersion,
    IngestionJob,
)
from app.modules.installation.models import InstallationState
from app.modules.memberships.models import (
    Membership,
    WorkspaceMembership,
    WorkspaceMembershipPermission,
)
from app.modules.organizations.models import Organization, OrganizationAiDefaults
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace

__all__ = [
    "InstallationState",
    "Document",
    "DocumentVersion",
    "DocumentIndexMetadata",
    "IngestionJob",
    "Membership",
    "WorkspaceMembership",
    "WorkspaceMembershipPermission",
    "Organization",
    "OrganizationAiDefaults",
    "User",
    "Workspace",
    "Chatbot",
    "Conversation",
    "Message",
    "MessageCitation",
    "UsageEvent",
    "ProviderConfig",
    "ProviderConnection",
    "OllamaModelPull",
    "EmbeddingIndexVersion",
    "EmbeddingReindexJob",
    "UserIdentity",
    "PasswordResetToken",
    "UserSession",
]
