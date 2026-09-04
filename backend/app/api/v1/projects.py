import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.domain.theme import (
    dump_overrides,
    empty_overrides,
    fonts_are_whitelisted,
    load_themes,
    resolve_project_theme,
)
from app.ingest.base import UnsupportedDocument
from app.ingest.upload import UploadRejected
from app.models.project import Project, ProjectSource
from app.models.user import User
from app.schemas.project import (
    HtmlStyleGenerateRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectPublic,
    ProjectThemeUpdate,
    ProjectUpdate,
    SourcePublic,
    TextSourceCreate,
)
from app.services.deck import load_slides, refresh_slide_issues
from app.services.html_style import generate_html_style
from app.services.sources import add_document_source, add_text_source, delete_source
from app.services.template_library import ExternalTemplatePublic, get_external_template

router = APIRouter(prefix="/projects", tags=["projects"])
_HTML_COMPAT_THEME_ID = "ivory"

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _ensure_known_theme(theme_id: str | None) -> None:
    if theme_id is not None and theme_id not in load_themes():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"未知主题：{theme_id}",
        )


def _get_external_template_or_422(template_id: str) -> ExternalTemplatePublic:
    template = get_external_template(template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="外部 PPT 模板不存在，可能已从 Template 文件夹移除",
        )
    return template


def _apply_external_template(project: Project, template: ExternalTemplatePublic) -> None:
    """将外部 PPT 的解析风格落为项目的原生主题覆盖项。"""

    project.external_template_id = template.id
    project.theme_id = template.style_profile.base_theme_id
    project.theme_overrides = dump_overrides(template.style_profile.overrides)


def _ensure_outline_unlocked(project: Project) -> None:
    # 已确认大纲对应一组确定的输入与参数；允许它们静默变化会让确认失去意义。
    if project.outline is not None and project.outline.status == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请先取消确认大纲",
        )


async def get_owned_project(
    project_id: Annotated[uuid.UUID, Path()],
    session: SessionDep,
    current_user: CurrentUser,
) -> Project:
    """按用户隔离取项目。

    别人的项目一律返回 404 而非 403，否则响应码本身就泄露了
    "该 id 存在" 这一信息。
    """
    result = await session.execute(
        select(Project).where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


OwnedProject = Annotated[Project, Depends(get_owned_project)]


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate, session: SessionDep, current_user: CurrentUser
) -> Project:
    data = body.model_dump()
    # HTML 报告不使用 PPT 模板或预置网页样式。theme_id 是历史共用表结构中的
    # 非空兼容列，固定为内部占位值，直出网页的生成、预览和导出均不会读取它。
    if data["output_format"] == "html":
        if data.get("external_template_id"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="HTML 报告不支持外部 PPT 模板",
            )
        data["theme_id"] = _HTML_COMPAT_THEME_ID
        data["external_template_id"] = None
        data["theme_overrides"] = empty_overrides()
        data["layout_mode"] = "flex"
        data["html_style"] = {}
    else:
        _ensure_known_theme(body.theme_id)
        template_id = data.get("external_template_id")
        if template_id:
            template = _get_external_template_or_422(template_id)
            data["theme_id"] = template.style_profile.base_theme_id
            data["theme_overrides"] = dump_overrides(template.style_profile.overrides)

    project = Project(user_id=current_user.id, **data)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("", response_model=list[ProjectPublic])
async def list_projects(session: SessionDep, current_user: CurrentUser) -> list[Project]:
    result = await session.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .order_by(Project.updated_at.desc())
    )
    return list(result.scalars())


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project: OwnedProject) -> Project:
    return project


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    body: ProjectUpdate, project: OwnedProject, session: SessionDep
) -> Project:
    _ensure_outline_unlocked(project)

    data = body.model_dump(exclude_unset=True)
    if "output_format" in data and data["output_format"] != project.output_format:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="项目类型创建后不可切换，请新建 PPT 或 HTML 报告项目",
        )
    if project.output_format == "html" and any(
        field in data for field in ("theme_id", "external_template_id", "layout_mode")
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HTML 报告不使用 PPT 主题、模板或版式，请填写 HTML 风格提示词",
        )
    if "theme_id" in data:
        _ensure_known_theme(data["theme_id"])
    if "theme_id" in data:
        if data["theme_id"] != project.theme_id or project.external_template_id is not None:
            project.theme_overrides = empty_overrides()
        # 普通项目设置为内置主题时，不能留下会误导用户的外部模板标记；即便底座
        # theme_id 恰好相同，用户的“切换到内置模板”意图也应当生效。
        project.external_template_id = None
    if "external_template_id" in data and data["external_template_id"]:
        template = _get_external_template_or_422(data["external_template_id"])
        _apply_external_template(project, template)
        data.pop("theme_id", None)
        data.pop("external_template_id", None)
    for field, value in data.items():
        setattr(project, field, value)

    await session.commit()
    await session.refresh(project)
    return project


@router.patch("/{project_id}/theme", response_model=ProjectDetail)
async def update_project_theme(
    body: ProjectThemeUpdate, project: OwnedProject, session: SessionDep
) -> Project:
    """更新主题预设或细粒度覆盖；大纲确认后仍可用。"""
    if project.output_format == "html":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HTML 报告不使用 PPT 主题、模板或主题覆盖",
        )
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="请提供 theme_id、external_template_id 或 overrides",
        )

    if "theme_id" in fields and body.theme_id is not None:
        _ensure_known_theme(body.theme_id)
        if body.theme_id != project.theme_id:
            project.theme_id = body.theme_id
            project.theme_overrides = empty_overrides()
        # 选内置预设即明确取消 Template/ 中参考文件的关联。
        project.external_template_id = None

    if "external_template_id" in fields:
        if body.external_template_id is None:
            project.external_template_id = None
        else:
            _apply_external_template(
                project, _get_external_template_or_422(body.external_template_id)
            )

    if "overrides" in fields:
        if body.overrides is None:
            project.theme_overrides = empty_overrides()
        else:
            if body.overrides.fonts is not None and not fonts_are_whitelisted(body.overrides.fonts):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="字体须选自系统提供的字体对",
                )
            project.theme_overrides = dump_overrides(body.overrides)

    theme = resolve_project_theme(project)
    slides = await load_slides(session, project.id)
    for slide in slides:
        if slide.status == "ready" and slide.blocks:
            refresh_slide_issues(slide, theme=theme)

    await session.commit()
    await session.refresh(project)
    return project


@router.post("/{project_id}/html-style/generate", response_model=ProjectDetail)
async def generate_project_html_style(
    body: HtmlStyleGenerateRequest, project: OwnedProject, session: SessionDep
) -> Project:
    """为 PPT 的 HTML 导出生成兼容样式配置。

    这是视觉层操作，和切换主题一样不应迫使用户取消已确认的大纲。
    """

    if project.output_format == "html":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HTML 报告由 AI 直接生成完整网页，不使用预置样式配置",
        )

    prompt = body.prompt.strip() if body.prompt is not None else project.html_style_prompt
    project.html_style_prompt = prompt or None
    profile = await generate_html_style(resolve_project_theme(project), project.html_style_prompt)
    project.html_style = profile.model_dump(mode="json")
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project(project: OwnedProject, session: SessionDep) -> None:
    await session.delete(project)
    await session.commit()


@router.post(
    "/{project_id}/sources",
    response_model=SourcePublic,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_source(
    body: TextSourceCreate, project: OwnedProject, session: SessionDep
) -> ProjectSource:
    _ensure_outline_unlocked(project)
    return await add_text_source(session, project, body)


@router.post(
    "/{project_id}/sources/upload",
    response_model=SourcePublic,
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    project: OwnedProject,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> ProjectSource:
    _ensure_outline_unlocked(project)
    data = await file.read()
    try:
        return await add_document_source(
            session, project, file.filename or "", file.content_type, data
        )
    except (UploadRejected, UnsupportedDocument) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


@router.delete(
    "/{project_id}/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_source(source_id: uuid.UUID, project: OwnedProject, session: SessionDep) -> None:
    _ensure_outline_unlocked(project)
    result = await session.execute(
        select(ProjectSource).where(
            ProjectSource.id == source_id, ProjectSource.project_id == project.id
        )
    )
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="输入材料不存在")

    await delete_source(session, source)
