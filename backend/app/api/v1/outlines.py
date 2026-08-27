import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_queue
from app.api.sse import event_stream_response
from app.api.v1.projects import OwnedProject
from app.core.db import get_session
from app.domain.layout import load_layouts
from app.models.project import Project, ProjectOutline
from app.schemas.outline import (
    OutlineEvent,
    OutlineGenerateAccepted,
    OutlinePublic,
    OutlineRevisionRequest,
    OutlineUpdate,
)
from app.services.outline_inputs import migrate_outline_signature, outline_input_matches
from app.services.outline_progress import outline_events, publish_outline_event

router = APIRouter(prefix="/projects/{project_id}/outline", tags=["outline"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


def _outline_or_404(project: Project) -> ProjectOutline:
    if project.outline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未生成大纲")
    return project.outline


def _ensure_revision(outline: ProjectOutline, revision: int) -> None:
    if outline.revision != revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="大纲已被其他操作更新，请刷新后重试",
        )


def _ensure_draft(outline: ProjectOutline) -> None:
    if outline.status != "draft":
        detail = "请先取消确认" if outline.status == "confirmed" else "当前大纲不可编辑"
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _validate_pages(project: Project, pages: list) -> None:
    valid_layouts = load_layouts()
    invalid = sorted({page.layout_id for page in pages if page.layout_id not in valid_layouts})
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"大纲包含未知布局：{'、'.join(invalid)}",
        )
    if len(pages) != project.page_count:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"大纲必须包含 {project.page_count} 页",
        )


@router.get("", response_model=OutlinePublic)
async def get_outline(project: OwnedProject) -> ProjectOutline:
    return _outline_or_404(project)


@router.post(
    "/generate",
    response_model=OutlineGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_outline(
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> OutlineGenerateAccepted:
    if not project.sources or not any(source.char_count > 0 for source in project.sources):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请先添加可用于生成大纲的输入材料",
        )
    if project.outline is not None and project.outline.status == "confirmed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请先取消确认")
    if project.outline is not None and project.outline.status == "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="大纲正在生成")

    job_id = f"outline-{project.id}-{uuid.uuid4().hex}"
    outline = project.outline
    if outline is None:
        outline = ProjectOutline(project_id=project.id)
        session.add(outline)
    outline.status = "generating"
    outline.error = None
    outline.job_id = job_id
    await session.commit()

    try:
        job = await queue.enqueue_job(
            "generate_outline",
            str(project.id),
            job_id,
            _job_id=job_id,
        )
    except RedisError as error:
        outline.status = "failed"
        outline.error = "任务队列暂时不可用"
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂时不可用",
        ) from error

    if job is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已存在")

    await publish_outline_event(
        project.id,
        OutlineEvent(
            type="progress",
            status="generating",
            progress=0,
            message="任务已进入队列",
            revision=outline.revision,
        ),
    )
    return OutlineGenerateAccepted(job_id=job_id)


@router.patch("", response_model=OutlinePublic)
async def update_outline(
    body: OutlineUpdate,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    _ensure_draft(outline)
    _ensure_revision(outline, body.revision)
    _validate_pages(project, body.pages)

    outline.pages = [page.model_dump(mode="json") for page in body.pages]
    outline.revision += 1
    await session.commit()
    await session.refresh(outline)
    return outline


@router.post("/confirm", response_model=OutlinePublic)
async def confirm_outline(
    body: OutlineRevisionRequest,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    _ensure_draft(outline)
    _ensure_revision(outline, body.revision)
    if not outline_input_matches(project, outline.input_signature):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="生成大纲后输入材料或设置已变化，请重新生成",
        )
    # 匹配到 legacy 签名时升级为当前指纹
    migrated = migrate_outline_signature(project, outline.input_signature)
    if migrated is not None:
        outline.input_signature = migrated
    _validate_pages(project, [*map(_page_from_dict, outline.pages)])

    outline.status = "confirmed"
    outline.revision += 1
    project.status = "outline_ready"
    await session.commit()
    await session.refresh(outline)
    return outline


@router.post("/unconfirm", response_model=OutlinePublic)
async def unconfirm_outline(
    body: OutlineRevisionRequest,
    project: OwnedProject,
    session: SessionDep,
) -> ProjectOutline:
    outline = _outline_or_404(project)
    if outline.status != "confirmed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="大纲尚未确认")
    _ensure_revision(outline, body.revision)

    outline.status = "draft"
    outline.revision += 1
    project.status = "draft"
    await session.commit()
    await session.refresh(outline)
    return outline


def _page_from_dict(data: dict):
    from app.domain.outline import OutlinePage

    return OutlinePage.model_validate(data)


@router.get("/events")
async def stream_outline_events(
    request: Request,
    project: OwnedProject,
) -> StreamingResponse:
    outline = _outline_or_404(project)
    settled = outline.status in {"draft", "confirmed"}
    return event_stream_response(
        request,
        stream=outline_events,
        key=project.id,
        fallback=OutlineEvent(
            type="snapshot",
            status=outline.status,
            progress=100 if settled else 0,
            message="大纲已就绪" if settled else "等待任务进度",
            revision=outline.revision,
        ),
        terminal_types={"completed", "failed"},
    )
