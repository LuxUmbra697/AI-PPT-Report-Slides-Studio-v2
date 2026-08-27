import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _random_email() -> str:
    return f"user_{uuid.uuid4().hex}@example.com"


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    email = _random_email()
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str) and body["access_token"]
    assert body["user"]["email"] == email
    assert "id" in body["user"]
    assert "created_at" in body["user"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    email = _random_email()
    first = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password456"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "该邮箱已被注册"


@pytest.mark.asyncio
async def test_register_email_case_insensitive(client: AsyncClient) -> None:
    suffix = uuid.uuid4().hex
    first = await client.post(
        "/api/v1/auth/register",
        json={"email": f"Case_{suffix}@Example.COM", "password": "password123"},
    )
    assert first.status_code == 201
    assert first.json()["user"]["email"] == f"case_{suffix}@example.com"

    second = await client.post(
        "/api/v1/auth/register",
        json={"email": f"case_{suffix}@example.com", "password": "password456"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "该邮箱已被注册"


@pytest.mark.asyncio
async def test_register_password_too_short(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": _random_email(), "password": "short"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    email = _random_email()
    password = "password123"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == email


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    email = _random_email()
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "邮箱或密码错误"


@pytest.mark.asyncio
async def test_me_with_token(client: AsyncClient) -> None:
    email = _random_email()
    register = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    token = register.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert "id" in body
    assert "created_at" in body


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "登录状态无效或已过期"


@pytest.mark.asyncio
async def test_me_with_forged_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer forged.invalid.token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "登录状态无效或已过期"
