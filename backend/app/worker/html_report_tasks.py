"""HTML 项目的独立正文任务：确认大纲后直接写报告，不创建 PPT Slide。"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.db import async_session_factory
from app.images.base import ImageRequest
from app.images.validate import ImageRejected, validate_image
from app.llm.base import OutlineSourceSection
from app.llm.html_report import (
    DeepSeekHtmlDocumentGenerator,
    HtmlReportGenerationInput,
    HtmlReportImageAsset,
    HtmlReportOutlineItem,
)
from app.models.project import Project
from app.services.deck import outline_pages
from app.services.html_document import DOCUMENT_KEY
from app.services.media import media_url, store_image
from app.worker.context import create_html_document_generator
from app.worker.retry import retry_after_failure

logger = logging.getLogger(__name__)


async def generate_html_report(ctx: dict[str, Any], project_id: str, job_id: str) -> None:
    project_uuid = uuid.UUID(project_id)
    loaded = await _load_payload(project_uuid, job_id)
    if loaded is None:
        return
    payload, user_id = loaded

    # 图片不是让浏览器或模型临时热链：先由服务端取得、校验、写入项目媒体，再把
    # 稳定 URL 交给网页模型。单张失败不应拖垮整份 HTML 正文。
    assets = await _prepare_image_assets(ctx, payload, user_id, project_uuid)
    payload = payload.model_copy(update={"image_assets": assets})

    generator: DeepSeekHtmlDocumentGenerator = (
        ctx.get("html_document_generator") or create_html_document_generator()
    )
    try:
        document = await generator.generate(payload)
    except Exception as error:
        retry = retry_after_failure(ctx, error)
        if retry is not None:
            logger.warning(
                "HTML report generation attempt %s failed for project %s; retrying: %s",
                ctx.get("job_try", 1),
                project_id,
                error,
            )
            raise retry from error
        logger.exception(
            "HTML report generation failed after all attempts for project %s",
            project_id,
        )
        await _save_failed(project_uuid, job_id, _public_error(error))
        return
    await _save_ready(
        project_uuid,
        job_id,
        {
            DOCUMENT_KEY: document,
            "image_assets": [asset.model_dump() for asset in assets],
        },
    )


async def _load_payload(
    project_id: uuid.UUID, job_id: str
) -> tuple[HtmlReportGenerationInput, uuid.UUID] | None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project)
            .options(selectinload(Project.sources), selectinload(Project.outline))
            .where(Project.id == project_id)
        )
        project = result.scalar_one_or_none()
        if (
            project is None
            or project.output_format != "html"
            or project.outline is None
            or project.outline.status != "confirmed"
            or project.html_report_status != "generating"
            or project.html_report_job_id != job_id
        ):
            return None

        pages = outline_pages(project)
        payload = HtmlReportGenerationInput(
            title=project.title,
            audience=project.audience,
            tone=project.tone,
            style_prompt=project.html_style_prompt,
            outline=[
                HtmlReportOutlineItem(
                    title=page.title,
                    objective=page.objective,
                    key_points=page.key_points,
                    source_refs=page.source_refs,
                )
                for page in pages
            ],
            sections=[
                OutlineSourceSection(
                    ref=f"S{source_index}:{section_index}",
                    heading=section.get("heading"),
                    level=section.get("level", 0),
                    text=section.get("text", ""),
                    locator=section.get("locator", ""),
                )
                for source_index, source in enumerate(project.sources, start=1)
                for section_index, section in enumerate(source.sections, start=1)
            ],
        )
        return payload, project.user_id


async def _prepare_image_assets(
    ctx: dict[str, Any],
    payload: HtmlReportGenerationInput,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
) -> list[HtmlReportImageAsset]:
    pipeline = ctx.get("image_pipeline")
    if pipeline is None or not getattr(pipeline, "enabled", False):
        return []

    requested_count = min(max(get_settings().html_report_image_count, 0), 3)
    if requested_count == 0:
        return []

    selected_items = _select_image_outline_items(payload.outline, requested_count)
    assets: list[HtmlReportImageAsset] = []
    for index, item in enumerate(selected_items, start=1):
        style = payload.style_prompt or "根据报告主题自主设计，信息清晰、适合网页阅读"
        request = ImageRequest(
            prompt=(
                f"为中文 HTML 报告《{payload.title}》制作第 {index} 张网页主视觉，"
                f"章节是《{item.title}》，目标：{item.objective}。视觉风格：{style}。"
                "画面要有叙事感与留白，不要 PPT 页面、不要文字、不要水印、不要品牌标识。"
            ),
            query=f"{payload.title} {item.title}",
            aspect_ratio=16 / 9,
        )
        try:
            image = await pipeline.fetch(request)
            if image is None:
                continue
            extension, _ = validate_image(image.data)
            key = store_image(
                user_id=user_id,
                project_id=project_id,
                data=image.data,
                extension=extension,
            )
            assets.append(
                HtmlReportImageAsset(
                    url=media_url(key),
                    alt=f"《{payload.title}》：{item.title}配图",
                    source=image.source,
                    credit=image.credit,
                )
            )
        except (ImageRejected, OSError, ValueError) as error:
            logger.warning("HTML report image %s for %s was skipped: %s", index, project_id, error)
        except Exception:
            logger.exception(
                "HTML report image %s for %s failed and was skipped", index, project_id
            )
    return assets


def _select_image_outline_items(
    items: list[HtmlReportOutlineItem], count: int
) -> list[HtmlReportOutlineItem]:
    if count >= len(items):
        return items
    if count == 1:
        return [items[0]]
    # 首章 + 中后部章节的离散采样，避免多张图围绕同一段内容。
    indexes = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    return [items[index] for index in indexes]


async def _save_ready(project_id: uuid.UUID, job_id: str, data: dict) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        project = result.scalar_one_or_none()
        if project is None or project.html_report_job_id != job_id:
            return
        project.html_report_data = data
        project.html_report_status = "ready"
        project.html_report_error = None
        project.status = "ready"
        await session.commit()


async def _save_failed(project_id: uuid.UUID, job_id: str, message: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        project = result.scalar_one_or_none()
        if project is None or project.html_report_job_id != job_id:
            return
        project.html_report_status = "failed"
        project.html_report_error = message
        project.status = "outline_ready"
        await session.commit()


def _public_error(error: Exception) -> str:
    from app.llm.errors import InvalidModelOutputError, LLMNotConfiguredError

    if isinstance(error, LLMNotConfiguredError):
        return str(error)
    if isinstance(error, InvalidModelOutputError):
        return "AI 返回的报告结构不完整，已自动重试 3 次仍未成功，请重新生成。"
    return "HTML 报告生成失败，已自动重试 3 次仍未成功，请稍后重新生成。"
