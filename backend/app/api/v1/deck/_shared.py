import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_queue
from app.core.db import get_session
from app.domain.flex_layout import FlexContainer
from app.domain.theme import resolve_project_theme
from app.models.project import Project
from app.models.slide import Slide
from app.schemas.deck import SlidePublic
from app.services.deck import refresh_slide_issues

SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


def _ensure_idle(slides: list[Slide]) -> None:
    if any(slide.status == "generating" for slide in slides):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="页面正在生成中")


def _find_slide(slides: list[Slide], slide_id: uuid.UUID) -> Slide:
    slide = next((item for item in slides if item.id == slide_id), None)
    if slide is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")
    return slide


def _ensure_editable(slide: Slide, revision: int) -> None:
    # 页面生成完成时会整块覆盖 blocks，此时编辑会被无声冲掉
    if slide.status == "generating":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再编辑",
        )
    if slide.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面已被其他操作更新，请刷新后重试",
        )


def _require_flex_tree(slide: Slide) -> FlexContainer:
    if slide.layout_mode != "flex" or slide.layout_tree is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前页面不是灵活布局，请先解锁",
        )
    return FlexContainer.model_validate(slide.layout_tree)


def _dump_layout_tree(tree: FlexContainer) -> dict:
    return tree.model_dump(mode="json")


async def _commit_slide_edit(
    session: AsyncSession,
    project: Project,
    slide: Slide,
) -> SlidePublic:
    refresh_slide_issues(slide, theme=resolve_project_theme(project))
    slide.revision += 1
    await session.commit()
    await session.refresh(slide)
    return SlidePublic.model_validate(slide)
