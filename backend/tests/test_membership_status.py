from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.auth import OrganizationContext, get_organization_context
from app.core.exceptions import AppError
from app.modules.admin.router import AdminUserStatusInput, update_admin_user_status


async def test_disabling_membership_preserves_global_identity_and_sessions():
    user = SimpleNamespace(
        id=uuid4(),
        email="member@example.com",
        status="ACTIVE",
        auth_version=4,
        last_login_at=None,
        created_at=None,
    )
    membership = SimpleNamespace(role="WORKSPACE_ADMIN", status="ACTIVE")
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[membership, user]),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        execute=AsyncMock(return_value=[]),
    )
    context = OrganizationContext(uuid4(), SimpleNamespace(user_id=uuid4(), role="ADMIN"))
    response = await update_admin_user_status(
        user.id, AdminUserStatusInput(status="DISABLED"), context, session
    )
    assert response.status == membership.status == "DISABLED"
    assert user.status == "ACTIVE" and user.auth_version == 4
    # Only the workspace list is read; no global session revocation is issued.
    assert session.execute.await_count == 1


async def test_disabled_membership_is_denied_even_with_a_valid_global_identity():
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(status="DISABLED")))
    with pytest.raises(AppError) as error:
        await get_organization_context(uuid4(), SimpleNamespace(id=uuid4()), session)
    assert error.value.code == "ORGANIZATION_ACCESS_DENIED"
