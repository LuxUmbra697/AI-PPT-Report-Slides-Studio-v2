import asyncio
import uuid
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.domain.content import Slide as SlideContent
from app.domain.outline import OutlinePage
from app.domain.page_rhythm import allows_callout, skeleton_hint
from app.domain.validation import StructureIssue
from app.images.pipeline import ImagePipeline, create_image_pipeline
from app.llm.base import OutlineSourceSection, SlideGenerationInput, SlideGenerator
from app.llm.errors import LLMNotConfiguredError
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import DeckEvent
from app.services.deck import (
    clear_cancel,
    deck_events,
    deck_status,
    is_cancelled,
    load_slides,
    outline_pages,
)
from app.services.slide_images import resolve_slide_images
from app.worker.context import create_slide_generator
from app.workflows.slide import build_slide_workflow, run_slide_workflow


async def generate_deck(ctx: dict[str, Any], project_id: str, slide_ids: list[str]) -> None:
    """并发生成指定页面。

    编排任务只做三件事：限流、逐页派发、汇报进度。真正的生成逻辑在
    单页工作流里，因此「整份生成」和「单页重试」走的是同一条代码路径。
    """
    project_uuid = uuid.UUID(project_id)
    targets = [uuid.UUID(value) for value in slide_ids]
    context = await _load_context(project_uuid)
    if context is None:
        return

    generator: SlideGenerator = ctx.get("slide_generator") or create_slide_generator()
    workflow = build_slide_workflow(generator)
    owned_client: httpx.AsyncClient | None = None
    pipeline: ImagePipeline | None = ctx.get("image_pipeline")
    if pipeline is None:
        owned_client = httpx.AsyncClient(trust_env=False, proxy=None)
        pipeline = create_image_pipeline(owned_client)
    semaphore = asyncio.Semaphore(get_settings().slide_concurrency)
    cancelled = False

    async def run_one(slide_id: uuid.UUID) -> None:
        nonlocal cancelled
        async with semaphore:
            # 取消只在每页开始前生效：正在跑的那一页让它跑完，
            # 中途丢弃既浪费了已花的费用，也会留下半截状态。
            if cancelled or await is_cancelled(project_uuid):
                cancelled = True
                return
            await _generate_one(project_uuid, slide_id, context, workflow, pipeline)

    try:
        await asyncio.gather(*(run_one(slide_id) for slide_id in targets))
    finally:
        if owned_client is not None:
            await owned_client.aclose()
    await _finish(project_uuid, cancelled=cancelled)


async def _generate_one(
    project_id: uuid.UUID,
    slide_id: uuid.UUID,
    context: "DeckContext",
    workflow,
    pipeline: ImagePipeline,
) -> None:
    page = context.pages.get(slide_id)
    if page is None:
        return

    if not await _mark_generating(slide_id):
        return
    await _publish(project_id, "slide_started", f"正在生成第 {page.position} 页", slide_id, page)

    from app.domain.content_density import normalize_page_role

    page_role = normalize_page_role(getattr(page.page, "page_role", None))
    visual_hint = getattr(page.page, "visual", None)
    payload = SlideGenerationInput(
        deck_title=context.title,
        audience=context.audience,
        tone=context.tone,
        position=page.position,
        total_pages=context.total,
        page_title=page.page.title,
        objective=page.page.objective,
        key_points=page.page.key_points,
        layout_id=page.page.layout_id,
        layout_mode=context.layout_mode,
        content_density=context.content_density,
        page_role=page_role,
        sections=[
            context.sections[ref] for ref in page.page.source_refs if ref in context.sections
        ],
        neighbor_titles=context.neighbor_titles(page.position),
        visual_hint=visual_hint,
        # 跨页多样性必须提前分配：各页并发生成，看不到彼此的版式
        skeleton_hint=skeleton_hint(
            page.position, page_role=page_role, has_visual=bool(visual_hint)
        ),
        allow_callout=allows_callout(page.position),
    )

    try:
        slide, issues = await run_slide_workflow(
            workflow,
            payload,
            slide_id,
            theme_id=context.theme_id,
            theme_overrides=context.theme_overrides,
        )
    except Exception as error:
        await _save_failed(slide_id, _public_error(error))
        await _publish(project_id, "slide_failed", f"第 {page.position} 页生成失败", slide_id, page)
        return

    slide = await resolve_slide_images(
        pipeline,
        user_id=context.user_id,
        project_id=project_id,
        deck_title=context.title,
        page_title=page.page.title,
        slide=slide,
    )
    await _save_ready(slide_id, slide, issues, intended_mode=context.layout_mode)
    await _publish(project_id, "slide_completed", f"第 {page.position} 页已完成", slide_id, page)


class DeckContext:
    """一次编排里所有页共享的只读上下文，避免每页重新查库。"""

    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        title: str,
        audience: str | None,
        tone: str,
        theme_id: str,
        theme_overrides: dict,
        layout_mode: str,
        content_density: str,
        sections: dict[str, OutlineSourceSection],
        pages: dict[uuid.UUID, "SlideTarget"],
        ordered_titles: list[str],
    ) -> None:
        from app.domain.content_density import normalize_density

        self.user_id = user_id
        self.title = title
        self.audience = audience
        self.tone = tone
        self.theme_id = theme_id
        self.theme_overrides = theme_overrides
        self.layout_mode = layout_mode if layout_mode in ("fixed", "flex") else "flex"
        self.content_density = normalize_density(content_density)
        self.sections = sections
        self.pages = pages
        self.total = len(ordered_titles)
        self._ordered_titles = ordered_titles

    def neighbor_titles(self, position: int) -> list[str]:
        start = max(0, position - 2)
        return self._ordered_titles[start : position + 1]


class SlideTarget:
    def __init__(self, position: int, page: OutlinePage) -> None:
        self.position = position
        self.page = page


async def _load_context(project_id: uuid.UUID) -> DeckContext | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.sources), selectinload(Project.outline))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if project is None or project.outline is None or project.outline.status != "confirmed":
            return None

        pages = outline_pages(project)
        by_page_id = {page.id: (index, page) for index, page in enumerate(pages, start=1)}

        slides = await load_slides(session, project_id)
        targets = {
            slide.id: SlideTarget(*by_page_id[slide.outline_page_id])
            for slide in slides
            if slide.outline_page_id in by_page_id
        }

        sections = {
            f"S{source_index}:{section_index}": OutlineSourceSection(
                ref=f"S{source_index}:{section_index}",
                heading=section.get("heading"),
                level=section.get("level", 0),
                text=section.get("text", ""),
                locator=section.get("locator", ""),
            )
            for source_index, source in enumerate(project.sources, start=1)
            for section_index, section in enumerate(source.sections, start=1)
        }

        return DeckContext(
            user_id=project.user_id,
            title=project.title,
            audience=project.audience,
            tone=project.tone,
            theme_id=project.theme_id,
            theme_overrides=dict(project.theme_overrides or {}),
            layout_mode=getattr(project, "layout_mode", None) or "flex",
            content_density=getattr(project, "content_density", None) or "medium",
            sections=sections,
            pages=targets,
            ordered_titles=[page.title for page in pages],
        )


async def _mark_generating(slide_id: uuid.UUID) -> bool:
    async with async_session_factory() as session:
        slide = await session.get(Slide, slide_id, with_for_update=True)
        if slide is None or slide.status == "ready":
            return False
        slide.status = "generating"
        slide.error = None
        await session.commit()
        return True


async def _save_ready(
    slide_id: uuid.UUID,
    content: SlideContent,
    issues: list[StructureIssue],
    *,
    intended_mode: str,
) -> None:
    async with async_session_factory() as session:
        slide = await session.get(Slide, slide_id, with_for_update=True)
        if slide is None:
            return
        slide.blocks = [block.model_dump(mode="json") for block in content.blocks]
        slide.speaker_notes = content.speaker_notes
        # 以项目编排意图为准，避免内容默认值把 flex 页落成 fixed
        mode = intended_mode if intended_mode in ("fixed", "flex") else content.layout_mode
        if mode == "flex":
            slide.layout_mode = "flex"
            slide.layout_tree = (
                content.layout_tree.model_dump(mode="json")
                if content.layout_tree is not None
                else None
            )
        else:
            slide.layout_mode = "fixed"
            slide.layout_tree = None
        # 修复一轮后仍留下的问题不阻断生成，交给后续质量检查统一收口
        slide.issues = [issue.model_dump(mode="json") for issue in issues]
        slide.status = "ready"
        slide.error = None
        slide.revision += 1
        await session.commit()


async def _save_failed(slide_id: uuid.UUID, message: str) -> None:
    async with async_session_factory() as session:
        slide = await session.get(Slide, slide_id, with_for_update=True)
        if slide is None:
            return
        slide.status = "failed"
        slide.error = message
        await session.commit()


async def _publish(
    project_id: uuid.UUID,
    event_type: str,
    message: str,
    slide_id: uuid.UUID | None,
    page: SlideTarget | None,
) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        slides = await load_slides(session, project_id)
        status = deck_status(
            slides,
            project_status=project.status if project is not None else None,
        )

    total = len(slides)
    ready = sum(1 for slide in slides if slide.status == "ready")
    failed = sum(1 for slide in slides if slide.status == "failed")
    await deck_events.publish(
        project_id,
        DeckEvent(
            type=event_type,  # type: ignore[arg-type]
            status=status,
            progress=int((ready + failed) * 100 / total) if total else 0,
            message=message,
            slide_id=slide_id,
            position=page.position if page else None,
            ready=ready,
            failed=failed,
            total=total,
        ),
    )


async def _finish(project_id: uuid.UUID, *, cancelled: bool) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        slides = await load_slides(session, project_id)
        # 收尾时不再把 project.generating 算进去：任务已结束，剩余 pending 应落为 partial
        status = deck_status(slides)
        if project is not None:
            project.status = "ready" if status == "ready" else "outline_ready"
            await session.commit()

    if cancelled:
        await clear_cancel(project_id)

    failed = sum(1 for slide in slides if slide.status == "failed")
    ready = sum(1 for slide in slides if slide.status == "ready")
    total = len(slides)
    if cancelled:
        message = "生成已取消，已完成的页面保留"
        event_type = "cancelled"
    elif failed:
        message = f"生成结束，{failed} 页失败，可单独重试"
        event_type = "completed"
    else:
        message = "全部页面已生成"
        event_type = "completed"

    await deck_events.publish(
        project_id,
        DeckEvent(
            type=event_type,  # type: ignore[arg-type]
            status=status,
            progress=100,
            message=message,
            ready=ready,
            failed=failed,
            total=total,
        ),
    )


def _public_error(error: Exception) -> str:
    if isinstance(error, LLMNotConfiguredError):
        return str(error)
    # 不把供应商响应或输入材料落库，避免错误信息成为敏感数据旁路
    return "页面生成失败，请重试"
