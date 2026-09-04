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
from app.services.html_document import (
    HtmlMediaBundleError,
    bundle_html_for_export,
    generated_document,
)
from app.services.html_style import resolve_html_style
from app.services.multiformat_export import (
    HTML_MEDIA_TYPE,
    MARKDOWN_MEDIA_TYPE,
    PDF_MEDIA_TYPE,
    render_deck_to_html,
    render_deck_to_markdown,
    render_deck_to_pdf,
)
from app.services.quality import build_quality_report, project_to_content_deck

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


def _ensure_ppt_project(project: OwnedProject) -> None:
    if project.output_format == "html":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HTML 报告只支持 HTML 导出，以保留动效、交互与丰富视觉内容",
        )


@router.get("", response_model=DeckPublic)
async def get_deck(project: OwnedProject, session: SessionDep) -> DeckPublic:
    slides = await load_slides(session, project.id)
    return to_deck_public(project, slides)


@router.get("/quality", response_model=ExportCheckReport)
async def get_deck_quality(project: OwnedProject, session: SessionDep) -> ExportCheckReport:
    """导出前质量报告：分级 issues 与是否允许导出。检查逻辑见 build_quality_report。"""
    slides = await load_slides(session, project.id)
    return build_quality_report(project, slides)


async def _exportable_deck(project: OwnedProject, session: SessionDep):
    """所有格式共享同一份完成态与质量门槛，避免不同导出结果互相矛盾。"""

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
    return project_to_content_deck(project, slides)


def _attachment(payload: bytes, *, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(payload),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/export")
async def export_deck(project: OwnedProject, session: SessionDep) -> StreamingResponse:
    """同步导出项目 PPTX：检查 → 渲染 → 回读验证 → 返回文件流。"""
    _ensure_ppt_project(project)
    deck = await _exportable_deck(project, session)
    try:
        buffer = render_deck_to_pptx(
            deck,
            theme=resolve_project_theme(project),
            external_template_id=project.external_template_id,
        )
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

    return _attachment(payload, filename=f"{project.title}.pptx", media_type=PPTX_MEDIA_TYPE)


@router.get("/export/html")
async def export_deck_html(project: OwnedProject, session: SessionDep) -> StreamingResponse:
    """导出离线可打开、带导航与入场动效的单文件 HTML 展示。"""

    if project.output_format == "html":
        if project.html_report_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="HTML 报告尚未生成完成，无法导出",
            )
        document = generated_document(project)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="这是旧版 HTML 报告，请重新生成以获得 AI 直出网页",
            )
        try:
            document = await bundle_html_for_export(document)
        except HtmlMediaBundleError as error:
            logger.warning("项目 %s HTML 离线资源打包失败: %s", project.id, error)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        return _attachment(
            document.encode("utf-8"),
            filename=f"{project.title}.html",
            media_type=HTML_MEDIA_TYPE,
        )

    deck = await _exportable_deck(project, session)
    try:
        payload = render_deck_to_html(
            deck,
            theme=resolve_project_theme(project),
            style_profile=resolve_html_style(
                resolve_project_theme(project), project.html_style_prompt, project.html_style
            ),
        )
    except Exception as error:
        logger.exception("项目 %s HTML 导出失败", project.id)
        raise HTTPException(status_code=500, detail=f"HTML 渲染失败：{error}") from error
    return _attachment(payload, filename=f"{project.title}.html", media_type=HTML_MEDIA_TYPE)


@router.get("/export/markdown")
async def export_deck_markdown(project: OwnedProject, session: SessionDep) -> StreamingResponse:
    """导出可继续编辑与版本管理的 Markdown 文稿。"""

    _ensure_ppt_project(project)

    deck = await _exportable_deck(project, session)
    return _attachment(
        render_deck_to_markdown(deck),
        filename=f"{project.title}.md",
        media_type=MARKDOWN_MEDIA_TYPE,
    )


@router.get("/export/pdf")
async def export_deck_pdf(project: OwnedProject, session: SessionDep) -> StreamingResponse:
    """导出静态阅读版 PDF；HTML 动效会自动降级。"""

    _ensure_ppt_project(project)

    deck = await _exportable_deck(project, session)
    try:
        payload = render_deck_to_pdf(deck, theme=resolve_project_theme(project))
    except Exception as error:
        logger.exception("项目 %s PDF 导出失败", project.id)
        raise HTTPException(status_code=500, detail=f"PDF 渲染失败：{error}") from error
    return _attachment(payload, filename=f"{project.title}.pdf", media_type=PDF_MEDIA_TYPE)
