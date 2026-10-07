"""Admin user management contract tests (dependency-overridden, no database)."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.core.auth import OrganizationContext, get_organization_context
from app.core.database import get_session
from app.main import app
from app.modules.memberships.models import MembershipRole


def _admin_context(user_id=None):
    organization_id = uuid.uuid4()
    admin_id = user_id or uuid.uuid4()

    async def context():
        membership = SimpleNamespace(
            role=MembershipRole.ADMIN, user_id=admin_id, organization_id=organization_id
        )
        return OrganizationContext(organization_id=organization_id, membership=membership)

    return context, organization_id, admin_id


def test_workspace_admin_cannot_list_admin_users():
    async def context():
        membership = SimpleNamespace(role="WORKSPACE_ADMIN", user_id=uuid.uuid4())
        return OrganizationContext(organization_id=uuid.uuid4(), membership=membership)

    async def session():
        return SimpleNamespace()

    app.dependency_overrides[get_organization_context] = context
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/v1/admin/users", headers={"X-Organization-ID": str(uuid.uuid4())}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"


def test_list_admin_users_pagination_defaults_to_ten():
    context_override, _, _ = _admin_context()
    captured = {}

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    now = datetime.now(UTC)
    member = SimpleNamespace(user_id=uuid.uuid4(), role=MembershipRole.WORKSPACE_ADMIN)
    user = SimpleNamespace(
        id=member.user_id,
        email="a@x.vn",
        display_name=None,
        status="ACTIVE",
        last_login_at=None,
        created_at=now,
    )

    class FakeSession:
        async def scalar(self, statement):
            compiled = str(statement)
            if "count" in compiled.lower():
                return 1
            return None

        async def execute(self, statement):
            compiled = str(statement)
            if "workspace_membership" in compiled.lower():
                return FakeResult([])
            captured["statement"] = compiled
            return FakeResult([(member, user)])

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/users?q=a&page=1&page_size=10")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page"] == 1 and body["page_size"] == 10 and body["total"] == 1
    assert body["items"][0]["email"] == "a@x.vn"
    assert "OFFSET" in captured["statement"].upper() or "LIMIT" in captured["statement"].upper()


def test_create_admin_user_rejects_duplicate_email():
    context_override, _, _ = _admin_context()

    class FakeSession:
        async def scalar(self, statement):
            return uuid.uuid4()  # existing user id

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/admin/users", json={"email": "TRUNG@x.vn", "password": "mat-khau-123"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USER_EMAIL_TAKEN"


def test_admin_cannot_disable_self():
    admin_id = uuid.uuid4()
    context_override, organization_id, _ = _admin_context(user_id=admin_id)

    class FakeSession:
        async def get(self, model, key):
            name = getattr(model, "__tablename__", "")
            if name == "memberships":
                return SimpleNamespace(user_id=admin_id, role=MembershipRole.ADMIN)
            return SimpleNamespace(id=admin_id, status="ACTIVE", auth_version=1)

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.patch(
                f"/api/v1/admin/users/{admin_id}/status", json={"status": "DISABLED"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SELF_DISABLE_NOT_ALLOWED"


def test_status_change_rejects_invalid_value():
    context_override, _, _ = _admin_context()
    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{uuid.uuid4()}/status", json={"status": "SUSPENDED"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


def test_create_admin_user_stores_display_name():
    from app.modules.users.models import User

    context_override, _, _ = _admin_context()
    stored: dict = {}

    class FakeSession:
        async def scalar(self, statement):
            return None  # no existing user

        def add(self, obj):
            if isinstance(obj, User):
                stored["user"] = obj

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users",
                json={
                    "email": "Lan@x.vn",
                    "password": "mat-khau-123",
                    "display_name": "  Lan Nguyen  ",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "lan@x.vn"
    assert body["display_name"] == "Lan Nguyen"
    assert body["role"] == "WORKSPACE_ADMIN"
    assert stored["user"].display_name == "Lan Nguyen"


def test_create_admin_user_can_assign_admin_role():
    from app.modules.memberships.models import Membership

    context_override, _, _ = _admin_context()
    stored: dict = {}

    class FakeSession:
        async def scalar(self, statement):
            return None

        def add(self, obj):
            if isinstance(obj, Membership):
                stored["membership"] = obj

        async def flush(self):
            return None

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/users",
                json={
                    "email": "admin2@x.vn",
                    "password": "mat-khau-123",
                    "role": "ADMIN",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "ADMIN"
    assert stored["membership"].role == MembershipRole.ADMIN


def test_update_admin_user_display_name():
    from app.modules.users.models import User

    target_id = uuid.uuid4()
    context_override, _, _ = _admin_context()
    user = User(
        id=target_id,
        email="lan@x.vn",
        display_name="Lan Cu",
        status="ACTIVE",
    )

    class FakeResult:
        def __iter__(self):
            return iter([])

    class FakeSession:
        async def get(self, model, key):
            if getattr(model, "__tablename__", "") == "memberships":
                return SimpleNamespace(user_id=target_id, role=MembershipRole.WORKSPACE_ADMIN)
            return user

        async def execute(self, statement):
            return FakeResult()

        async def commit(self):
            return None

        async def refresh(self, obj):
            return None

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/admin/users/{target_id}", json={"display_name": "Lan Moi"}
            )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["display_name"] == "Lan Moi"
    assert user.display_name == "Lan Moi"


def test_list_admin_users_returns_display_name():
    context_override, _, _ = _admin_context()

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def __iter__(self):
            return iter(self._rows)

    now = datetime.now(UTC)
    member = SimpleNamespace(user_id=uuid.uuid4(), role=MembershipRole.WORKSPACE_ADMIN)
    user = SimpleNamespace(
        id=member.user_id,
        email="lan@x.vn",
        display_name="Lan Nguyen",
        status="ACTIVE",
        last_login_at=None,
        created_at=now,
    )

    class FakeSession:
        async def scalar(self, statement):
            return 1

        async def execute(self, statement):
            compiled = str(statement)
            if "workspace_membership" in compiled.lower():
                return FakeResult([])
            return FakeResult([(member, user)])

    async def session():
        return FakeSession()

    app.dependency_overrides[get_organization_context] = context_override
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/admin/users?q=lan")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["display_name"] == "Lan Nguyen"
