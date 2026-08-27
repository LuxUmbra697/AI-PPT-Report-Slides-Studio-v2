import uuid

from arq.connections import ArqRedis
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sse import event_stream_response
from app.api.v1.deck._shared import QueueDep, SessionDep, _ensure_idle
from app.api.v1.projects import OwnedProject
from app.models.project import Project
from app.schemas.deck import DeckEvent, DeckGenerateAccepted, DeckGenerateRequest
from app.services.deck import (
    clear_cancel,
    deck_events,
    deck_status,
    load_slides,
    request_cancel,
    reset_slide_for_regeneration,
    sync_slides,
)

_PREFIX = "/projects/{project_id}/deck"
router = APIRouter(prefix=_PREFIX, tags=["deck"])
events_router = APIRouter(prefix=_PREFIX, tags=["deck"])


def _ensure_confirmed(project: Project) -> None:
    if project.outline is None or project.outline.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先确认大纲再生成页面",
        )


async def _enqueue(
    queue: ArqRedis,
    session: AsyncSession,
    project: Project,
    slide_ids: list[uuid.UUID],
    *,
    previous_status: str,
) -> str:
    # 取消标记由发起方清理：新一轮生成理应从干净状态开始，
    # 放在任务里清会与「先取消再立刻重发」的时序抢跑。
    await clear_cancel(project.id)
    job_id = f"deck-{project.id}-{uuid.uuid4().hex}"
    try:
        job = await queue.enqueue_job(
            "generate_deck",
            str(project.id),
            [str(slide_id) for slide_id in slide_ids],
            _job_id=job_id,
        )
    except RedisError as error:
        # 入队前已 commit 为 generating；rollback 无效，须显式恢复原状态
        project.status = previous_status
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂时不可用",
        ) from error
    if job is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已存在")
    return job_id


@router.post(
    "/generate",
    response_model=DeckGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_deck(
    body: DeckGenerateRequest,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> DeckGenerateAccepted:
    _ensure_confirmed(project)
    _ensure_idle(await load_slides(session, project.id))

    pending = await sync_slides(session, project, regenerate_all=body.regenerate_all)
    slides = await load_slides(session, project.id)
    if not pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="所有页面均已生成，如需重做请选择整份重新生成",
        )

    pending_ids = [slide.id for slide in pending]
    previous_status = project.status
    project.status = "generating"
    await session.commit()

    job_id = await _enqueue(
        queue, session, project, pending_ids, previous_status=previous_status
    )
    await deck_events.publish(
        project.id,
        DeckEvent(
            type="slide_started",
            status="generating",
            progress=0,
            message=f"{len(pending_ids)} 页已进入队列",
            ready=sum(1 for slide in slides if slide.status == "ready"),
            total=len(slides),
        ),
    )
    return DeckGenerateAccepted(job_id=job_id, total=len(slides), pending=len(pending_ids))


@router.post(
    "/slides/{slide_id}/retry",
    response_model=DeckGenerateAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_slide(
    slide_id: uuid.UUID,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> DeckGenerateAccepted:
    _ensure_confirmed(project)
    slides = await load_slides(session, project.id)
    target = next((slide for slide in slides if slide.id == slide_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="页面不存在")
    if target.status == "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该页正在生成中")

    # 重试等价于把这一页退回待生成，走的仍是整份生成那条路径
    previous_status = project.status
    reset_slide_for_regeneration(target, layout_mode=project.layout_mode)
    project.status = "generating"
    await session.commit()

    job_id = await _enqueue(
        queue, session, project, [slide_id], previous_status=previous_status
    )
    return DeckGenerateAccepted(job_id=job_id, total=len(slides), pending=1)


@router.post("/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_deck(project: OwnedProject, session: SessionDep) -> Response:
    slides = await load_slides(session, project.id)
    if deck_status(slides, project_status=project.status) != "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前没有生成任务")
    await request_cancel(project.id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@events_router.get("/events")
async def stream_deck_events(
    request: Request,
    project: OwnedProject,
    session: SessionDep,
) -> StreamingResponse:
    slides = await load_slides(session, project.id)
    current = deck_status(slides, project_status=project.status)
    ready = sum(1 for slide in slides if slide.status == "ready")
    failed = sum(1 for slide in slides if slide.status == "failed")
    return event_stream_response(
        request,
        stream=deck_events,
        key=project.id,
        fallback=DeckEvent(
            type="snapshot",
            status=current,
            progress=int((ready + failed) * 100 / len(slides)) if slides else 0,
            message="等待生成任务",
            ready=ready,
            failed=failed,
            total=len(slides),
        ),
        terminal_types={"completed", "cancelled", "failed"},
    )
