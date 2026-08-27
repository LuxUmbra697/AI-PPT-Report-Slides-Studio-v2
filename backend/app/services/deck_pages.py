"""编辑器内的整页增删复制。

一次操作要同时改三处：slides 行、大纲页列表与项目目标页数。少改任何一处，
``sync_slides`` 都会在下次生成时按大纲把页面拽回去——新插的页被删掉，删掉的页
又长回来。所以三者统一在这里的一个事务里维护。
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.slide_pages import (
    blank_outline_page,
    blank_slide_content,
    clone_slide_content,
)
from app.domain.theme import resolve_project_theme
from app.models.project import Project, ProjectOutline
from app.models.slide import Slide
from app.schemas.project import MAX_DECK_PAGE_COUNT, MIN_DECK_PAGE_COUNT
from app.services.deck import refresh_slide_issues

PageErrorCode = Literal["page_limit", "outline_missing", "last_page"]


class PageOperationError(Exception):
    """整页操作被业务规则拒绝；由 API 层按 code 翻成状态码。"""

    def __init__(self, code: PageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


async def insert_blank_page(
    session: AsyncSession,
    project: Project,
    slides: list[Slide],
    *,
    after: Slide | None,
) -> Slide:
    """在指定页之后插入一张空白页；after 为 None 表示追加到末尾。"""
    outline = _require_outline(project)
    _ensure_page_bounds(len(slides) + 1)

    page = blank_outline_page()
    blocks, tree = blank_slide_content()
    slide = Slide(
        project_id=project.id,
        outline_page_id=page.id,
        position=len(slides) + 1,
        layout_id=page.layout_id,
        layout_mode="flex",
        layout_tree=tree.model_dump(mode="json"),
        title=page.title,
        # 空白页内容是本地造的，不需要过一遍生成流程就能编辑
        status="ready",
        blocks=blocks,
        issues=[],
        # 显式给版本号：列默认值要等 flush 才生效，而下面算告警时就要读它
        revision=1,
    )
    session.add(slide)
    outline.pages = [*outline.pages, page.model_dump(mode="json")]
    refresh_slide_issues(slide, theme=resolve_project_theme(project))

    await _commit_order(session, project, outline, _inserted(slides, slide, after))
    return slide


async def duplicate_page(
    session: AsyncSession,
    project: Project,
    slides: list[Slide],
    source: Slide,
) -> Slide:
    """在源页之后插入一张副本；内容深拷贝，块 id 全部换新。"""
    outline = _require_outline(project)
    _ensure_page_bounds(len(slides) + 1)

    page = _copied_outline_page(outline, source)
    blocks, layout_tree = clone_slide_content(source.blocks, source.layout_tree)
    slide = Slide(
        project_id=project.id,
        outline_page_id=uuid.UUID(str(page["id"])),
        position=source.position + 1,
        layout_id=source.layout_id,
        layout_mode=source.layout_mode,
        layout_tree=layout_tree,
        title=source.title,
        status=source.status,
        blocks=blocks,
        speaker_notes=source.speaker_notes,
        issues=[],
        error=None,
        # 副本从头计数：源页的编辑历史与它无关
        revision=1,
    )
    session.add(slide)
    outline.pages = [*outline.pages, page]
    # 未就绪的页没有可校验的内容，告警等生成完再算
    if slide.status == "ready":
        refresh_slide_issues(slide, theme=resolve_project_theme(project))

    await _commit_order(session, project, outline, _inserted(slides, slide, source))
    return slide


async def delete_page(
    session: AsyncSession,
    project: Project,
    slides: list[Slide],
    target: Slide,
) -> None:
    """删除一页；至少保留一页，否则编辑器会退回空态。"""
    outline = _require_outline(project)
    if len(slides) <= 1:
        raise PageOperationError("last_page", "至少保留一页")

    remaining = [slide for slide in slides if slide.id != target.id]
    await session.delete(target)
    await _commit_order(session, project, outline, remaining)


def neighbour_slide_id(slides: list[Slide], removed: Slide) -> uuid.UUID | None:
    """删除后应当选中的页：优先后一页，末页则取前一页。"""
    index = next((i for i, slide in enumerate(slides) if slide.id == removed.id), -1)
    if index < 0:
        return None
    rest = [slide for slide in slides if slide.id != removed.id]
    if not rest:
        return None
    return rest[min(index, len(rest) - 1)].id


async def _commit_order(
    session: AsyncSession,
    project: Project,
    outline: ProjectOutline,
    ordered: list[Slide],
) -> None:
    for position, slide in enumerate(ordered, start=1):
        slide.position = position
    _align_outline_pages(project, outline, ordered)
    await session.commit()


def _align_outline_pages(
    project: Project,
    outline: ProjectOutline,
    ordered: list[Slide],
) -> None:
    """按当前页序重排大纲页，并同步目标页数。

    拖拽排序只改 slides.position，大纲页序会因此与实际页序脱节；整页增删本来就
    要重写这份列表，顺手对齐可以避免下次生成把页序拽回旧顺序。
    """
    by_id = {str(page.get("id")): page for page in outline.pages}
    pages = [
        by_id[str(slide.outline_page_id)]
        for slide in ordered
        if str(slide.outline_page_id) in by_id
    ]
    outline.pages = pages
    outline.revision += 1
    # 确认大纲时会校验 len(pages) == page_count，页数必须跟着走
    project.page_count = len(pages)


def _copied_outline_page(outline: ProjectOutline, source: Slide) -> dict:
    """复制源页对应的大纲页并换新 id。

    源页在大纲里找不到只会发生在数据已经不一致时；此时用空白页兜底，但沿用页面
    自己的标题与布局，否则 ``sync_slides`` 会因 layout_id 不符把这份副本清空重生成。
    """
    existing = next(
        (page for page in outline.pages if str(page.get("id")) == str(source.outline_page_id)),
        None,
    )
    if existing is not None:
        return {**existing, "id": str(uuid.uuid4())}
    fallback = blank_outline_page().model_dump(mode="json")
    return {**fallback, "title": source.title, "layout_id": source.layout_id}


def _inserted(slides: list[Slide], slide: Slide, after: Slide | None) -> list[Slide]:
    if after is None:
        return [*slides, slide]
    index = next((i for i, item in enumerate(slides) if item.id == after.id), -1)
    if index < 0:
        return [*slides, slide]
    return [*slides[: index + 1], slide, *slides[index + 1 :]]


def _require_outline(project: Project) -> ProjectOutline:
    if project.outline is None:
        raise PageOperationError("outline_missing", "尚未生成大纲，无法调整页面")
    return project.outline


def _ensure_page_bounds(count: int) -> None:
    if count < MIN_DECK_PAGE_COUNT or count > MAX_DECK_PAGE_COUNT:
        raise PageOperationError(
            "page_limit",
            f"页数需在 {MIN_DECK_PAGE_COUNT}–{MAX_DECK_PAGE_COUNT} 页之间",
        )
