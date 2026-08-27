import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.v1.deck._shared import SessionDep
from app.api.v1.projects import OwnedProject
from app.domain.export_check import ExportCheckReport
from app.domain.theme import resolve_project_theme
from app.render.pptx import PPTX_MEDIA_TYPE, render_deck_to_pptx
from app.render.verify import verify_pptx
from app.schemas.deck import DeckPublic
from app.services.deck import load_slides, to_deck_public
from app.services.quality import build_quality_report, project_to_content_deck

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


@router.get("", response_model=DeckPublic)
async def get_deck(project: OwnedProject, session: SessionDep) -> DeckPublic:
    slides = await load_slides(session, project.id)
    return to_deck_public(project, slides)


@router.get("/quality", response_model=ExportCheckReport)
async def get_deck_quality(project: OwnedProject, session: SessionDep) -> ExportCheckReport:
    """导出前质量报告：分级 issues 与是否允许导出。检查逻辑见 build_quality_report。"""
    slides = await load_slides(session, project.id)
    return build_quality_report(project, slides)


@router.get("/export")
async def export_deck(project: OwnedProject, session: SessionDep) -> StreamingResponse:
    """同步导出项目 PPTX：检查 → 渲染 → 回读验证 → 返回文件流。"""
    slides = await load_slides(session, project.id)
    if not slides or any(slide.status != "ready" for slide in slides):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="页面尚未全部生成完成，无法导出",
        )

    quality = build_quality_report(project, slides)
    if not quality.export_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "导出前检查未通过，存在必须修复的问题",
                "report": quality.model_dump(mode="json"),
            },
        )

    deck = project_to_content_deck(project, slides)
    try:
        buffer = render_deck_to_pptx(deck, theme=resolve_project_theme(project))
        payload = buffer.getvalue()
    except Exception as error:
        logger.exception("项目 %s 导出渲染失败", project.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PPTX 渲染失败：{error}",
        ) from error

    try:
        verified = verify_pptx(payload, deck)
    except Exception as error:
        logger.exception("项目 %s 导出回读验证异常", project.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导出回读验证失败：{error}",
        ) from error

    if not verified.passed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "导出回读验证未通过，未返回文件",
                "issues": [issue.model_dump(mode="json") for issue in verified.issues],
            },
        )

    filename = quote(f"{project.title}.pptx")
    return StreamingResponse(
        BytesIO(payload),
        media_type=PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
