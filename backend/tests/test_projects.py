import io
import uuid
import zipfile

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _sign_up(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": f"user_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create_project(client: AsyncClient, headers: dict[str, str], **overrides) -> dict:
    payload = {"title": "季度复盘", "page_count": 8} | overrides
    response = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_create_project_applies_defaults(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    assert project["title"] == "季度复盘"
    assert project["page_count"] == 8
    assert project["tone"] == "professional"
    assert project["theme_id"] == "ivory"
    assert project["status"] == "draft"
    assert project["sources"] == []


@pytest.mark.asyncio
async def test_projects_require_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/projects")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_page_count_outside_range_is_rejected(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    response = await client.post(
        "/api/v1/projects", json={"title": "太长了", "page_count": 40}, headers=headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_theme_is_rejected(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    response = await client.post(
        "/api/v1/projects", json={"title": "主题不存在", "theme_id": "nope"}, headers=headers
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_projects_are_isolated_between_users(client: AsyncClient) -> None:
    """别人的项目必须返回 404 而非 403，否则响应码本身就泄露了该 id 存在"""
    owner = await _sign_up(client)
    intruder = await _sign_up(client)
    project = await _create_project(client, owner)

    listed = await client.get("/api/v1/projects", headers=intruder)
    assert listed.json() == []

    for method in (client.get, client.delete):
        response = await method(f"/api/v1/projects/{project['id']}", headers=intruder)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_and_delete_project(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    updated = await client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"title": "年度复盘", "theme_id": "midnight"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "年度复盘"
    assert updated.json()["theme_id"] == "midnight"
    # 未提交的字段保持原值
    assert updated.json()["page_count"] == project["page_count"]

    removed = await client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
    assert removed.status_code == 204

    assert (await client.get("/api/v1/projects", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_topic_source_becomes_one_section(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources",
        json={"kind": "topic", "content": "如何把内部工具做成平台"},
        headers=headers,
    )

    assert response.status_code == 201
    source = response.json()
    assert len(source["sections"]) == 1
    assert source["sections"][0]["locator"] == "主题"
    assert source["char_count"] == len("如何把内部工具做成平台")


@pytest.mark.asyncio
async def test_long_text_is_split_into_paragraphs(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources",
        json={"kind": "text", "content": "第一段内容。\n\n第二段内容。\n\n第三段内容。"},
        headers=headers,
    )

    assert response.status_code == 201
    assert len(response.json()["sections"]) == 3


@pytest.mark.asyncio
async def test_upload_markdown_keeps_heading_levels(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    document = "# 总览\n\n开篇说明。\n\n## 细节\n\n展开论述。\n"
    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("plan.md", document.encode("utf-8"), "text/markdown")},
        headers=headers,
    )

    assert response.status_code == 201, response.text
    sections = response.json()["sections"]
    assert [section["level"] for section in sections] == [1, 2]
    assert [section["heading"] for section in sections] == ["总览", "细节"]


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_extension(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "不支持的文件类型" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rejects_extension_content_mismatch(client: AsyncClient) -> None:
    """只看扩展名不够，改个后缀就能把任意文件送进解析器"""
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("fake.pdf", b"this is not a pdf", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "与扩展名不符" in response.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rejects_zip_disguised_as_docx(client: AsyncClient) -> None:
    """DOCX 是 zip 容器，文件头与任意压缩包一致，必须检查内部结构"""
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("hello.txt", "not a document")

    response = await client.post(
        f"/api/v1/projects/{project['id']}/sources/upload",
        files={"file": ("fake.docx", buffer.getvalue(), "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "有效的 DOCX" in response.json()["detail"]


@pytest.mark.asyncio
async def test_source_appears_in_project_detail_and_can_be_removed(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project = await _create_project(client, headers)

    created = await client.post(
        f"/api/v1/projects/{project['id']}/sources",
        json={"kind": "topic", "content": "主题"},
        headers=headers,
    )
    source_id = created.json()["id"]

    detail = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    assert [source["id"] for source in detail.json()["sources"]] == [source_id]

    removed = await client.delete(
        f"/api/v1/projects/{project['id']}/sources/{source_id}", headers=headers
    )
    assert removed.status_code == 204

    detail = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
    assert detail.json()["sources"] == []
