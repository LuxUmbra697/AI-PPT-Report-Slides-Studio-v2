import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.domain.layout import load_layouts
from app.main import app
from app.models.project import Project, ProjectOutline
from app.models.slide import Slide as SlideRow


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def _sign_up(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": f"edit_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _project_with_slides(
    client: AsyncClient,
    headers: dict[str, str],
    slides: list[dict],
) -> tuple[dict, list[SlideRow]]:
    response = await client.post(
        "/api/v1/projects",
        json={"title": "编辑闭环", "page_count": 5},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    project = response.json()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == uuid.UUID(project["id"]))
        )
        record = result.scalar_one()
        pages = []
        rows: list[SlideRow] = []
        for index, spec in enumerate(slides, start=1):
            page_id = uuid.uuid4()
            pages.append(
                {
                    "id": str(page_id),
                    "title": spec["title"],
                    "objective": "目标",
                    "key_points": ["要点"],
                    "source_refs": [],
                    "layout_id": spec["layout_id"],
                }
            )
            row = SlideRow(
                project_id=record.id,
                outline_page_id=page_id,
                position=index,
                layout_id=spec["layout_id"],
                layout_mode=spec.get("layout_mode", "fixed"),
                layout_tree=spec.get("layout_tree"),
                title=spec["title"],
                status=spec.get("status", "ready"),
                blocks=spec["blocks"],
                issues=spec.get("issues", []),
                revision=spec.get("revision", 1),
            )
            session.add(row)
            rows.append(row)

        session.add(
            ProjectOutline(
                project_id=record.id,
                status="confirmed",
                pages=pages,
                revision=2,
            )
        )
        record.status = "ready"
        await session.commit()
        for row in rows:
            await session.refresh(row)
        return project, rows


def _bullets_blocks(*, title: str = "标题", long: bool = False) -> list[dict]:
    text = ("很长" * 20) if long else title
    return [
        {
            "id": "t1",
            "slot_id": "title",
            "type": "text",
            "text": text,
            "locked": False,
        },
        {
            "id": "b1",
            "slot_id": "body",
            "type": "bullets",
            "items": ["要点一", "要点二"],
            "locked": False,
        },
    ]


def _image_blocks() -> list[dict]:
    return [
        {
            "id": "t1",
            "slot_id": "title",
            "type": "text",
            "text": "图文标题",
            "locked": False,
        },
        {
            "id": "b1",
            "slot_id": "body",
            "type": "bullets",
            "items": ["说明"],
            "locked": False,
        },
        {
            "id": "i1",
            "slot_id": "image",
            "type": "image",
            "alt": "示意图",
            "source": "placeholder",
            "url": None,
            "credit": None,
            "locked": False,
        },
    ]


@pytest.mark.asyncio
async def test_update_text_block_locks_and_recomputes_issues(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {
                "title": "要点页",
                "layout_id": "bullets",
                "blocks": _bullets_blocks(),
            }
        ],
    )
    slide = slides[0]
    # 超过 bullets 标题 24 字上限，应落 warning 但不拒绝保存
    long_title = "这是一段明显超过二十四字上限的超长标题内容XYZ!"

    response = await client.patch(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/blocks/t1",
        headers=headers,
        json={"type": "text", "revision": slide.revision, "text": long_title},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == slide.revision + 1
    text_block = next(block for block in body["blocks"] if block["id"] == "t1")
    assert text_block["text"] == long_title
    assert text_block["locked"] is True
    assert any(issue["severity"] == "warning" for issue in body["issues"])


@pytest.mark.asyncio
async def test_update_block_revision_conflict(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [{"title": "要点页", "layout_id": "bullets", "blocks": _bullets_blocks()}],
    )
    slide = slides[0]
    response = await client.patch(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/blocks/t1",
        headers=headers,
        json={"type": "text", "revision": slide.revision - 1, "text": "新标题"},
    )
    assert response.status_code == 409
    assert "刷新" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_block_rejects_while_generating(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {
                "title": "生成中",
                "layout_id": "bullets",
                "blocks": _bullets_blocks(),
                "status": "generating",
            }
        ],
    )
    slide = slides[0]
    response = await client.patch(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/blocks/t1",
        headers=headers,
        json={"type": "text", "revision": slide.revision, "text": "新标题"},
    )
    assert response.status_code == 409
    assert "生成中" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_block_rejects_type_mismatch(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [{"title": "要点页", "layout_id": "bullets", "blocks": _bullets_blocks()}],
    )
    slide = slides[0]
    response = await client.patch(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/blocks/t1",
        headers=headers,
        json={"type": "bullets", "revision": slide.revision, "items": ["a"]},
    )
    assert response.status_code == 409
    assert "块类型不匹配" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_slides_success(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {"title": "第一页", "layout_id": "bullets", "blocks": _bullets_blocks(title="一")},
            {"title": "第二页", "layout_id": "bullets", "blocks": _bullets_blocks(title="二")},
            {"title": "第三页", "layout_id": "bullets", "blocks": _bullets_blocks(title="三")},
        ],
    )
    new_order = [slides[2].id, slides[0].id, slides[1].id]
    response = await client.put(
        f"/api/v1/projects/{project['id']}/deck/slides/order",
        headers=headers,
        json={"slide_ids": [str(item) for item in new_order]},
    )
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(item) for item in new_order]
    assert [item["position"] for item in body] == [1, 2, 3]
    assert all(item["revision"] == 2 for item in body)


@pytest.mark.asyncio
async def test_reorder_rejects_stale_set(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {"title": "第一页", "layout_id": "bullets", "blocks": _bullets_blocks(title="一")},
            {"title": "第二页", "layout_id": "bullets", "blocks": _bullets_blocks(title="二")},
        ],
    )
    response = await client.put(
        f"/api/v1/projects/{project['id']}/deck/slides/order",
        headers=headers,
        json={"slide_ids": [str(slides[0].id)]},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "页面列表已变化，请刷新后重试"


@pytest.mark.asyncio
async def test_switch_layout_remaps_slots(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {
                "title": "图文页",
                "layout_id": "image-left",
                "blocks": _image_blocks(),
            }
        ],
    )
    slide = slides[0]
    response = await client.put(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/layout",
        headers=headers,
        json={"layout_id": "image-right", "revision": slide.revision},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["layout_id"] == "image-right"
    assert body["revision"] == slide.revision + 1
    by_id = {block["id"]: block for block in body["blocks"]}
    assert by_id["t1"]["slot_id"] == "title"
    assert by_id["b1"]["slot_id"] == "body"
    assert by_id["i1"]["slot_id"] == "image"
    assert by_id["t1"]["locked"] is False


@pytest.mark.asyncio
async def test_switch_layout_rejects_incompatible(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [{"title": "要点页", "layout_id": "bullets", "blocks": _bullets_blocks()}],
    )
    slide = slides[0]
    response = await client.put(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/layout",
        headers=headers,
        json={"layout_id": "chart", "revision": slide.revision},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "图表" in detail or "要点" in detail


@pytest.mark.asyncio
async def test_list_layouts_returns_compat_flags(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [{"title": "要点页", "layout_id": "bullets", "blocks": _bullets_blocks()}],
    )
    slide = slides[0]
    response = await client.get(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/layouts",
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(load_layouts())
    current = next(item for item in body if item["current"])
    assert current["layout_id"] == "bullets"
    assert current["compatible"] is True
    chart = next(item for item in body if item["layout_id"] == "chart")
    assert chart["compatible"] is False
    assert chart["reason"]


@pytest.mark.asyncio
async def test_update_chart_block_data(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    project, slides = await _project_with_slides(
        client,
        headers,
        [
            {
                "title": "图表页",
                "layout_id": "chart",
                "blocks": [
                    {
                        "id": "t1",
                        "slot_id": "title",
                        "type": "text",
                        "text": "增长",
                        "locked": False,
                    },
                    {
                        "id": "c1",
                        "slot_id": "chart",
                        "type": "chart",
                        "chart_type": "bar",
                        "categories": ["A", "B"],
                        "series": [{"name": "系列1", "values": [3.0, 5.0]}],
                        "locked": False,
                    },
                ],
            }
        ],
    )
    slide = slides[0]
    response = await client.patch(
        f"/api/v1/projects/{project['id']}/deck/slides/{slide.id}/blocks/c1",
        headers=headers,
        json={
            "type": "chart",
            "revision": slide.revision,
            "chart_type": "column",
            "categories": ["Q1", "Q2", "Q3"],
            "series": [
                {"name": "营收", "values": [10, 20, 15]},
                {"name": "成本", "values": [4, 8, 6]},
            ],
            "unit": "万",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    chart = next(block for block in body["blocks"] if block["id"] == "c1")
    assert chart["chart_type"] == "column"
    assert chart["categories"] == ["Q1", "Q2", "Q3"]
    assert chart["series"][0]["name"] == "营收"
    assert chart["series"][0]["values"] == [10, 20, 15]
    assert chart["unit"] == "万"
    assert chart["locked"] is True
