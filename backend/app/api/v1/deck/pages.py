import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deck._shared import SessionDep, _ensure_idle, _find_slide
from app.api.v1.projects import OwnedProject
from app.models.project import Project
from app.schemas.deck import DeckPageResult, SlideInsertRequest, SlideOrderRequest, SlidePublic
from app.services.deck import load_slides, to_deck_public
from app.services.deck_pages import (
    PageOperationError,
    delete_page,
    duplicate_page,
    insert_blank_page,
    neighbour_slide_id,
)

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])

_PAGE_ERROR_STATUS: dict[str, int] = {
    "page_limit": status.HTTP_422_UNPROCESSABLE_CONTENT,
    "outline_missing": status.HTTP_409_CONFLICT,
    "last_page": status.HTTP_400_BAD_REQUEST,
}


def _page_error(error: PageOperationError) -> HTTPException:
    return HTTPException(
        status_code=_PAGE_ERROR_STATUS[error.code],
        detail=error.message,
    )


async def _page_result(
    session: AsyncSession,
    project: Project,
    slide_id: uuid.UUID | None,
) -> DeckPageResult:
    slides = await load_slides(session, project.id)
    return DeckPageResult(deck=to_deck_public(project, slides), slide_id=slide_id)


@router.put("/slides/order", response_model=list[SlidePublic])
async def reorder_slides(
    body: SlideOrderRequest,
    project: OwnedProject,
    session: SessionDep,
) -> list[SlidePublic]:
    slides = await load_slides(session, project.id)
    if any(slide.status == "generating" for slide in slides):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面正在生成中，请稍后再调整顺序",
        )

    current_ids = {slide.id for slide in slides}
    requested = body.slide_ids
    if len(requested) != len(set(requested)) or set(requested) != current_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面列表已变化，请刷新后重试",
        )

    by_id = {slide.id: slide for slide in slides}
    # position 无唯一约束，可直接按目标下标重写
    for position, slide_id in enumerate(requested, start=1):
        slide = by_id[slide_id]
        slide.position = position
        slide.revision += 1

    await session.commit()
    ordered = await load_slides(session, project.id)
    return [SlidePublic.model_validate(slide) for slide in ordered]


@router.post(
    "/slides",
    response_model=DeckPageResult,
    status_code=status.HTTP_201_CREATED,
)
async def insert_slide(
    body: SlideInsertRequest,
    project: OwnedProject,
    session: SessionDep,
) -> DeckPageResult:
    """插入一张空白页，内容在本地生成，无需再跑一遍 AI。"""
    slides = await load_slides(session, project.id)
    _ensure_idle(slides)
    after = _find_slide(slides, body.after_slide_id) if body.after_slide_id else None
    try:
        created = await insert_blank_page(session, project, slides, after=after)
    except PageOperationError as error:
        raise _page_error(error) from error
    return await _page_result(session, project, created.id)


@router.post(
    "/slides/{slide_id}/duplicate",
    response_model=DeckPageResult,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_slide(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
) -> DeckPageResult:
    slides = await load_slides(session, project.id)
    _ensure_idle(slides)
    source = _find_slide(slides, slide_id)
    try:
        created = await duplicate_page(session, project, slides, source)
    except PageOperationError as error:
        raise _page_error(error) from error
    return await _page_result(session, project, created.id)


@router.delete("/slides/{slide_id}", response_model=DeckPageResult)
async def delete_slide(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
) -> DeckPageResult:
    slides = await load_slides(session, project.id)
    _ensure_idle(slides)
    target = _find_slide(slides, slide_id)
    focus = neighbour_slide_id(slides, target)
    try:
        await delete_page(session, project, slides, target)
    except PageOperationError as error:
        raise _page_error(error) from error
    return await _page_result(session, project, focus)
