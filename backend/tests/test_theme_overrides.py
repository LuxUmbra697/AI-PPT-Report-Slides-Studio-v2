import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.domain.theme import (
    ThemeOverrides,
    fonts_are_whitelisted,
    get_theme,
    merge_theme,
    resolve_theme,
)
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
        json={"email": f"theme_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_merge_theme_palette_and_accent_series() -> None:
    base = get_theme("ivory")
    merged = merge_theme(
        base,
        ThemeOverrides.model_validate({"palette": {"accent": "#0D9488"}}),
    )
    assert merged.palette.accent == "#0D9488"
    assert merged.palette.chart_series[0] == "#0D9488"
    assert merged.palette.background == base.palette.background


def test_merge_theme_text_size() -> None:
    base = get_theme("ivory")
    merged = merge_theme(
        base,
        ThemeOverrides.model_validate({"text_styles": {"title": {"size_pt": 40}}}),
    )
    assert merged.text_styles["title"].size_pt == 40
    assert merged.text_styles["body"].size_pt == base.text_styles["body"].size_pt


def test_fonts_whitelist() -> None:
    assert fonts_are_whitelisted(get_theme("midnight").fonts)
    foreign = get_theme("ivory").fonts.model_copy(deep=True)
    foreign.display.pptx_latin = "Comic Sans MS"
    assert not fonts_are_whitelisted(foreign)


def test_resolve_theme_empty_overrides() -> None:
    assert resolve_theme("scholar", {}).id == "scholar"
    assert resolve_theme("scholar", None).palette.accent == get_theme("scholar").palette.accent


@pytest.mark.asyncio
async def test_theme_api_after_outline_confirmed(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "主题微调", "page_count": 5},
    )
    assert created.status_code == 201, created.text
    project = created.json()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline))
            .where(Project.id == uuid.UUID(project["id"]))
        )
        record = result.scalar_one()
        page_id = uuid.uuid4()
        session.add(
            ProjectOutline(
                project_id=record.id,
                status="confirmed",
                pages=[
                    {
                        "id": str(page_id),
                        "title": "页",
                        "objective": "目标",
                        "key_points": ["要点"],
                        "source_refs": [],
                        "layout_id": "bullets",
                    }
                ],
                revision=1,
            )
        )
        session.add(
            SlideRow(
                project_id=record.id,
                outline_page_id=page_id,
                position=1,
                layout_id="bullets",
                layout_mode="fixed",
                title="页",
                status="ready",
                blocks=[
                    {
                        "id": "t1",
                        "slot_id": "title",
                        "type": "text",
                        "text": "标题",
                        "locked": False,
                    }
                ],
                issues=[],
                revision=1,
            )
        )
        record.status = "ready"
        await session.commit()

    # 大纲确认后普通 PATCH 仍 409
    locked = await client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={"theme_id": "midnight"},
    )
    assert locked.status_code == 409

    ok = await client.patch(
        f"/api/v1/projects/{project['id']}/theme",
        headers=headers,
        json={"overrides": {"palette": {"accent": "#112233"}}},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["theme_id"] == "ivory"
    assert body["theme_overrides"]["palette"]["accent"] == "#112233"

    switched = await client.patch(
        f"/api/v1/projects/{project['id']}/theme",
        headers=headers,
        json={"theme_id": "midnight"},
    )
    assert switched.status_code == 200
    assert switched.json()["theme_id"] == "midnight"
    assert switched.json()["theme_overrides"] == {}


@pytest.mark.asyncio
async def test_theme_api_rejects_bad_hex_and_fonts(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"title": "校验", "page_count": 5},
    )
    project_id = created.json()["id"]

    bad_hex = await client.patch(
        f"/api/v1/projects/{project_id}/theme",
        headers=headers,
        json={"overrides": {"palette": {"accent": "red"}}},
    )
    assert bad_hex.status_code == 422

    bad_fonts = await client.patch(
        f"/api/v1/projects/{project_id}/theme",
        headers=headers,
        json={
            "overrides": {
                "fonts": {
                    "display": {
                        "web": "Foo",
                        "pptx_latin": "Foo",
                        "pptx_east_asian": "黑体",
                    },
                    "body": {
                        "web": "Bar",
                        "pptx_latin": "Bar",
                        "pptx_east_asian": "黑体",
                    },
                }
            }
        },
    )
    assert bad_fonts.status_code == 422
    assert "字体" in bad_fonts.json()["detail"]
