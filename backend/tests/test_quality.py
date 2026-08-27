"""文字度量、内容质量与导出前检查。"""

from __future__ import annotations

import struct
import uuid
from collections.abc import AsyncGenerator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import async_session_factory
from app.domain.content import BulletsBlock, Deck, ImageBlock, Slide, TextBlock
from app.domain.export_check import (
    allow_export,
    check_images,
    check_slot_bounds,
    run_export_check,
)
from app.domain.quality import (
    check_duplicate_pages,
    check_unsourced_numbers,
    extract_numbers,
)
from app.domain.text_metrics import (
    clear_font_cache,
    fonts_available,
    measure_bullets,
    measure_text,
)
from app.domain.theme import get_theme
from app.domain.validation import has_blocking_issue, validate_slide
from app.main import app
from app.models.project import Project, ProjectOutline, ProjectSource
from app.models.slide import Slide as SlideRow


@pytest.fixture(autouse=True)
def _reset_font_cache() -> Iterator[None]:
    clear_font_cache()
    yield
    clear_font_cache()


def _png(width: int, height: int) -> bytes:
    # 最小合法 IHDR，足够 _image_size 解析
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_len = struct.pack(">I", 13)
    ihdr_crc = struct.pack(">I", 0)
    return signature + ihdr_len + b"IHDR" + ihdr_data + ihdr_crc


def _overflow_title_slide(*, text: str, slide_id: str = "s1") -> Slide:
    return Slide(
        id=slide_id,
        layout_id="bullets",
        blocks=[
            TextBlock(id="t1", slot_id="title", text=text),
            BulletsBlock(id="b1", slot_id="body", items=["短要点"]),
        ],
    )


def _deck_from_slides(slides: list[Slide], *, theme_id: str = "ivory") -> Deck:
    return Deck(id="d1", title="质量测试", theme_id=theme_id, slides=slides)


# --- 文字度量 ---


@pytest.mark.skipif(not fonts_available(), reason="度量字体未下载，跳过精确路径")
def test_precise_measure_short_text_fits() -> None:
    style = get_theme("ivory").text_style("title")
    result = measure_text("季度复盘", style=style, width_pt=800, height_pt=80)
    assert result.used_estimate is False
    assert result.overflows is False
    assert result.line_count == 1


@pytest.mark.skipif(not fonts_available(), reason="度量字体未下载，跳过精确路径")
def test_precise_measure_detects_overflow() -> None:
    style = get_theme("ivory").text_style("title")
    # 标题槽位高度约 62 pt；超长中文必然折多行并溢出
    long = "年度业务复盘与下一阶段重点工作安排说明" * 4
    result = measure_text(long, style=style, width_pt=816, height_pt=62)
    assert result.used_estimate is False
    assert result.overflows is True
    assert result.line_count > 1


def test_estimate_measure_when_fonts_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain import text_metrics as tm

    monkeypatch.setattr(tm, "FONTS_DIR", Path("/tmp/luxumbra-no-fonts"))
    clear_font_cache()

    assert fonts_available() is False
    style = get_theme("ivory").text_style("body")
    result = measure_text("Hello 中文宽度估算", style=style, width_pt=200, height_pt=40)
    assert result.used_estimate is True


def test_overflow_warning_marks_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain import text_metrics as tm

    monkeypatch.setattr(tm, "FONTS_DIR", Path("/tmp/luxumbra-no-fonts"))
    clear_font_cache()

    long = "这是一段故意写得很长用来触发溢出检测的中文标题内容" * 3
    issues = validate_slide(_overflow_title_slide(text=long), theme_id="ivory")
    overflow = [i for i in issues if "溢出" in i.message]
    assert overflow
    assert all(i.severity == "warning" for i in overflow)
    assert any("估算" in i.message for i in overflow)


@pytest.mark.skipif(not fonts_available(), reason="度量字体未下载，跳过精确路径")
def test_overflow_warning_precise_path() -> None:
    long = "这是一段故意写得很长用来触发溢出检测的中文标题内容" * 3
    short = "短标题"
    overflow_issues = validate_slide(_overflow_title_slide(text=long), theme_id="ivory")
    ok_issues = validate_slide(_overflow_title_slide(text=short), theme_id="ivory")

    assert any("溢出" in i.message for i in overflow_issues)
    assert all("估算" not in i.message for i in overflow_issues if "溢出" in i.message)
    assert not any("溢出" in i.message for i in ok_issues)


def test_capacity_check_still_present_alongside_overflow() -> None:
    # 字数上限筛查必须保留（提示词约束依据）
    text = "字" * 40  # bullets 标题上限 24
    issues = validate_slide(_overflow_title_slide(text=text), theme_id="ivory")
    assert any("超出建议上限" in i.message for i in issues)


def test_measure_bullets_empty() -> None:
    style = get_theme("ivory").text_style("bullet")
    result = measure_bullets([], style=style, width_pt=800, height_pt=300)
    assert result.overflows is False
    assert result.line_count == 0


# --- 内容质量 ---


def test_extract_numbers_skips_single_digit() -> None:
    assert extract_numbers("第1点与第12点，完成率 37.5%，营收 1,234") == [
        "12",
        "37.5%",
        "1,234",
    ]


def test_duplicate_pages_by_title() -> None:
    left = _overflow_title_slide(text="完全相同的标题", slide_id="a")
    right = _overflow_title_slide(text="完全相同的标题", slide_id="b")
    deck = _deck_from_slides([left, right])
    titles = {"a": "完全相同的标题", "b": "完全相同的标题"}
    issues = check_duplicate_pages(deck, slide_titles=titles)
    assert issues
    assert all(i.severity == "warning" for i in issues)
    assert any("相似" in i.message and "请确认是否重复" in i.message for i in issues)


def test_unsourced_numbers_warns_without_claiming_fact_check() -> None:
    slide = Slide(
        id="s1",
        layout_id="bullets",
        blocks=[
            TextBlock(id="t1", slot_id="title", text="增长"),
            BulletsBlock(id="b1", slot_id="body", items=["营收增长 37%", "用户破 1200 万"]),
        ],
    )
    issues = check_unsourced_numbers(slide, source_text="介绍产品亮点与路线图")
    assert len(issues) == 1
    assert issues[0].severity == "warning"
    assert "请核对数据来源" in issues[0].message
    assert "事实" not in issues[0].message
    assert "核验" not in issues[0].message


def test_sourced_numbers_pass() -> None:
    slide = Slide(
        id="s1",
        layout_id="bullets",
        blocks=[
            TextBlock(id="t1", slot_id="title", text="增长"),
            BulletsBlock(id="b1", slot_id="body", items=["营收增长 37%"]),
        ],
    )
    assert check_unsourced_numbers(slide, source_text="本季营收增长 37%，表现良好") == []


# --- 导出前检查 ---


def test_allow_export_blocks_on_error() -> None:
    from app.domain.validation import StructureIssue

    assert allow_export([]) is True
    assert (
        allow_export(
            [StructureIssue(severity="warning", slide_id="s", slot_id=None, message="提示")]
        )
        is True
    )
    assert (
        allow_export([StructureIssue(severity="error", slide_id="s", slot_id=None, message="错")])
        is False
    )


def test_run_export_check_grades_and_fonts_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain import text_metrics as tm

    monkeypatch.setattr(tm, "FONTS_DIR", Path("/tmp/luxumbra-no-fonts"))
    clear_font_cache()

    # 缺必填槽位 → error；字体缺失 → warning
    deck = _deck_from_slides(
        [
            Slide(
                id="s1",
                layout_id="bullets",
                blocks=[TextBlock(id="t1", slot_id="title", text="仅标题")],
            )
        ]
    )
    report = run_export_check(deck)
    assert report.export_allowed is False
    assert report.fonts_precise is False
    assert has_blocking_issue(report.issues)
    assert any(i.severity == "error" for i in report.issues)
    assert any("度量字体" in i.message for i in report.issues)


def test_run_export_check_allows_warnings_only() -> None:
    slide = _overflow_title_slide(text="正常标题", slide_id="s1")
    report = run_export_check(_deck_from_slides([slide]))
    # 结构完整时即使有字体/溢出类 warning 也允许导出
    assert report.export_allowed is True
    assert not has_blocking_issue(report.issues)


def test_check_images_missing_is_error() -> None:
    deck = _deck_from_slides(
        [
            Slide(
                id="s1",
                layout_id="image-left",
                blocks=[
                    TextBlock(id="t1", slot_id="title", text="图"),
                    ImageBlock(
                        id="i1",
                        slot_id="image",
                        alt="示意",
                        source="upload",
                        url="/api/v1/media/media/missing.png",
                    ),
                    BulletsBlock(id="b1", slot_id="body", items=["说明"]),
                ],
            )
        ]
    )

    def boom(_key: str) -> bytes:
        raise FileNotFoundError(_key)

    issues = check_images(
        deck,
        load_image=boom,
        media_key_from_url=lambda url: url.split("/api/v1/media/", 1)[-1],
    )
    assert any(i.severity == "error" and "无法读取" in i.message for i in issues)


def test_check_images_low_res_is_warning() -> None:
    deck = _deck_from_slides(
        [
            Slide(
                id="s1",
                layout_id="image-left",
                blocks=[
                    TextBlock(id="t1", slot_id="title", text="图"),
                    ImageBlock(
                        id="i1",
                        slot_id="image",
                        alt="示意",
                        source="upload",
                        url="/api/v1/media/media/tiny.png",
                    ),
                    BulletsBlock(id="b1", slot_id="body", items=["说明"]),
                ],
            )
        ]
    )
    data = _png(64, 64)
    issues = check_images(
        deck,
        load_image=lambda _key: data,
        media_key_from_url=lambda url: "media/tiny.png",
    )
    assert any(i.severity == "warning" and "分辨率偏低" in i.message for i in issues)


def test_slot_bounds_uses_layout_definitions() -> None:
    # 布局定义本身应在画布内；空检查返回 []
    deck = _deck_from_slides([_overflow_title_slide(text="标题")])
    assert check_slot_bounds(deck) == []


# --- 质量接口 ---


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


async def _sign_up(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": f"quality_{uuid.uuid4().hex}@example.com", "password": "password123"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.asyncio
async def test_quality_endpoint_returns_report(client: AsyncClient) -> None:
    headers = await _sign_up(client)
    created = await client.post(
        "/api/v1/projects",
        json={"title": "质量接口", "page_count": 5},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    project = created.json()

    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.outline), selectinload(Project.sources))
            .where(Project.id == uuid.UUID(project["id"]))
        )
        record = result.scalar_one()
        page_id = uuid.uuid4()
        session.add(
            ProjectSource(
                project_id=record.id,
                kind="text",
                sections=[
                    {"level": 0, "heading": None, "text": "营收增长 37%", "locator": "第 1 段"}
                ],
                warnings=[],
                char_count=10,
            )
        )
        session.add(
            ProjectOutline(
                project_id=record.id,
                status="confirmed",
                pages=[
                    {
                        "id": str(page_id),
                        "title": "增长",
                        "objective": "目标",
                        "key_points": ["要点一", "要点二"],
                        "source_refs": ["S1:1"],
                        "layout_id": "bullets",
                    }
                ],
                revision=2,
            )
        )
        session.add(
            SlideRow(
                project_id=record.id,
                outline_page_id=page_id,
                position=1,
                layout_id="bullets",
                layout_mode="fixed",
                title="增长",
                status="ready",
                blocks=[
                    {
                        "id": "t1",
                        "slot_id": "title",
                        "type": "text",
                        "text": "增长",
                        "locked": False,
                    },
                    {
                        "id": "b1",
                        "slot_id": "body",
                        "type": "bullets",
                        "items": ["营收增长 37%"],
                        "locked": False,
                    },
                ],
                issues=[],
                revision=1,
            )
        )
        record.status = "ready"
        await session.commit()

    response = await client.get(f"/api/v1/projects/{project['id']}/deck/quality", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "issues" in body
    assert "export_allowed" in body
    assert "fonts_precise" in body
    assert body["export_allowed"] is True
    assert isinstance(body["fonts_precise"], bool)
    # 来源里有 37%，不应再报无来源
    assert not any("请核对数据来源" in issue["message"] for issue in body["issues"])
