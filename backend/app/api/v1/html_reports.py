"""独立 HTML 报告任务及已完成报告的认证预览。"""

from __future__ import annotations

import uuid
from typing import Annotated

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_queue
from app.api.v1.projects import OwnedProject
from app.core.db import get_session
from app.schemas.project import HtmlReportGenerateRequest, HtmlReportPublic
from app.services.html_document import generated_document, with_preview_hash_navigation_guard
from app.services.multiformat_export import HTML_MEDIA_TYPE

router = APIRouter(prefix="/projects/{project_id}/html-report", tags=["html report"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
QueueDep = Annotated[ArqRedis, Depends(get_queue)]


def _ensure_html_project(project: OwnedProject) -> None:
    if project.output_format != "html":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前项目不是 HTML 报告项目",
        )


@router.get("", response_model=HtmlReportPublic)
async def get_html_report(project: OwnedProject) -> HtmlReportPublic:
    _ensure_html_project(project)
    return HtmlReportPublic(
        status=project.html_report_status,
        error=project.html_report_error,
        job_id=project.html_report_job_id,
        has_document=generated_document(project) is not None,
    )


@router.post("/generate", response_model=HtmlReportPublic, status_code=status.HTTP_202_ACCEPTED)
async def generate_html_report(
    body: HtmlReportGenerateRequest,
    project: OwnedProject,
    session: SessionDep,
    queue: QueueDep,
) -> HtmlReportPublic:
    _ensure_html_project(project)
    if project.outline is None or project.outline.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先确认大纲再生成 HTML 报告",
        )
    if project.html_report_status == "generating":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="HTML 报告正在生成")
    if project.html_report_status == "ready" and not body.regenerate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HTML 报告已生成，可选择重新生成",
        )

    job_id = f"html-report-{project.id}-{uuid.uuid4().hex}"
    previous_status = project.status
    previous_report_status = project.html_report_status
    project.html_report_status = "generating"
    project.html_report_job_id = job_id
    project.html_report_error = None
    project.status = "generating"
    await session.commit()
    try:
        job = await queue.enqueue_job(
            "generate_html_report", str(project.id), job_id, _job_id=job_id
        )
    except RedisError as error:
        project.html_report_status = previous_report_status
        project.status = previous_status
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="任务队列暂时不可用",
        ) from error
    if job is None:
        project.html_report_status = previous_report_status
        project.status = previous_status
        await session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已存在")
    return HtmlReportPublic(status="generating", job_id=job_id, has_document=False)


@router.get("/render")
async def render_html_report(project: OwnedProject) -> Response:
    _ensure_html_project(project)
    if project.html_report_status != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="HTML 报告尚未生成完成")
    payload = generated_document(project)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="这是旧版 HTML 报告，请重新生成以获得 AI 直出网页",
        )
    return Response(
        content=with_preview_hash_navigation_guard(payload),
        media_type=HTML_MEDIA_TYPE,
    )
