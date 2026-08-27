import uuid

from pydantic import TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.domain.content import Block
from app.domain.content import Slide as ContentSlide
from app.domain.flex_layout import FlexContainer
from app.domain.outline import OutlinePage
from app.domain.theme import Theme
from app.domain.validation import validate_slide
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import DeckEvent, DeckPublic, DeckStatus, SlidePublic
from app.services.events import EventStream

deck_events: EventStream[DeckEvent] = EventStream("deck", DeckEvent)

CANCEL_TTL_SECONDS = 60 * 30
_blocks_adapter = TypeAdapter(list[Block])


def to_content_slide(slide: Slide) -> ContentSlide:
    """ORM 行 → 领域 Slide（含 flex 布局树）。"""
    layout_tree = (
        FlexContainer.model_validate(slide.layout_tree) if slide.layout_tree is not None else None
    )
    # 有布局树却标成 fixed 时按 flex 解析，避免导出/校验走错几何路径
    if layout_tree is not None:
        mode: str = "flex"
    elif slide.layout_mode in ("fixed", "flex"):
        mode = slide.layout_mode
    else:
        mode = "flex"
    return ContentSlide(
        id=str(slide.id),
        layout_id=slide.layout_id,
        blocks=_blocks_adapter.validate_python(slide.blocks),
        speaker_notes=slide.speaker_notes,
        revision=slide.revision,
        layout_mode=mode,  # type: ignore[arg-type]
        layout_tree=layout_tree,
    )


def outline_pages(project: Project) -> list[OutlinePage]:
    if project.outline is None:
        return []
    return [OutlinePage.model_validate(page) for page in project.outline.pages]


async def load_slides(session: AsyncSession, project_id: uuid.UUID) -> list[Slide]:
    result = await session.execute(
        select(Slide).where(Slide.project_id == project_id).order_by(Slide.position)
    )
    return list(result.scalars())


def refresh_slide_issues(
    slide: Slide,
    *,
    theme_id: str | None = None,
    theme: Theme | None = None,
) -> None:
    """按当前 blocks/layout/主题重算结构与溢出告警并写回 JSONB。"""
    content = to_content_slide(slide)
    slide.issues = [
        issue.model_dump()
        for issue in validate_slide(content, theme_id=theme_id, theme=theme)
    ]


async def sync_slides(
    session: AsyncSession,
    project: Project,
    *,
    regenerate_all: bool = False,
) -> list[Slide]:
    """让页面行与已确认的大纲对齐，并返回待生成的页。

    以大纲页 id 为幂等键：重复点生成不会造出重复页，已就绪的页默认保留，
    因此中断后再点一次就是断点续跑。只有布局被改过或用户要求整份重做时，
    才把对应页重置回待生成。
    """
    pages = outline_pages(project)
    existing = {slide.outline_page_id: slide for slide in await load_slides(session, project.id)}
    page_ids = {page.id for page in pages}

    stale = [slide_id for slide_id in existing if slide_id not in page_ids]
    if stale:
        await session.execute(
            delete(Slide).where(Slide.project_id == project.id, Slide.outline_page_id.in_(stale))
        )

    project_mode = project.layout_mode if project.layout_mode in ("fixed", "flex") else "flex"

    pending: list[Slide] = []
    for position, page in enumerate(pages, start=1):
        slide = existing.get(page.id)
        if slide is None:
            slide = Slide(
                project_id=project.id,
                outline_page_id=page.id,
                position=position,
                layout_id=page.layout_id,
                title=page.title,
                status="pending",
                blocks=[],
                issues=[],
                layout_mode=project_mode,
                layout_tree=None,
            )
            session.add(slide)
        else:
            slide.position = position
            slide.title = page.title
            if regenerate_all or slide.layout_id != page.layout_id:
                slide.layout_id = page.layout_id
                reset_slide_for_regeneration(slide, layout_mode=project_mode)
            # flex 项目下，非 flex 或缺布局树的 ready 页重置为待生成
            elif (
                project_mode == "flex"
                and slide.status == "ready"
                and (slide.layout_mode != "flex" or slide.layout_tree is None)
            ):
                reset_slide_for_regeneration(slide, layout_mode="flex")

        if slide.status != "ready":
            reset_slide_for_regeneration(slide, layout_mode=project_mode)
            pending.append(slide)

    await session.flush()
    return pending


def reset_slide_for_regeneration(slide: Slide, *, layout_mode: str = "flex") -> None:
    """把一页退回待生成：清空内容与布局树，并归正 layout_mode。"""
    slide.status = "pending"
    slide.blocks = []
    slide.issues = []
    slide.error = None
    slide.layout_mode = layout_mode if layout_mode in ("fixed", "flex") else "flex"
    slide.layout_tree = None


def deck_status(slides: list[Slide], *, project_status: str | None = None) -> DeckStatus:
    """汇总整份 deck 状态。

    任务入队后、worker 领走页之前，页仍是 pending；页与页之间也会短暂没有
    generating 行。这两种窗口必须靠 project.status == generating 识别，否则
    前端不会挂 SSE，取消接口也会误判为「没有任务」。
    """
    if not slides:
        return "idle"
    if any(slide.status == "generating" for slide in slides) or (
        project_status == "generating" and any(slide.status == "pending" for slide in slides)
    ):
        return "generating"
    if all(slide.status == "ready" for slide in slides):
        return "ready"
    return "partial"


def to_deck_public(project: Project, slides: list[Slide]) -> DeckPublic:
    return DeckPublic(
        project_id=project.id,
        title=project.title,
        theme_id=project.theme_id,
        status=deck_status(slides, project_status=project.status),
        total=len(slides),
        ready=sum(1 for slide in slides if slide.status == "ready"),
        failed=sum(1 for slide in slides if slide.status == "failed"),
        slides=[SlidePublic.model_validate(slide) for slide in slides],
    )


def cancel_key(project_id: uuid.UUID) -> str:
    return f"deck:{project_id}:cancel"


async def request_cancel(project_id: uuid.UUID) -> None:
    """取消用 Redis 标记而不是终止任务。

    编排任务在每页开始前检查标记，正在生成的那一页会跑完再停：
    强杀会留下 generating 状态的孤儿行，反而更难恢复。
    """
    await get_redis().set(cancel_key(project_id), "1", ex=CANCEL_TTL_SECONDS)


async def clear_cancel(project_id: uuid.UUID) -> None:
    await get_redis().delete(cancel_key(project_id))


async def is_cancelled(project_id: uuid.UUID) -> bool:
    return await get_redis().exists(cancel_key(project_id)) == 1
