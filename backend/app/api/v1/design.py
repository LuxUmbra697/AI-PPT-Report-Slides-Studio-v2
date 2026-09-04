from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse

from app.domain.content import Deck
from app.domain.layout import Layout, load_layouts
from app.domain.sample import load_sample_deck
from app.domain.theme import Theme, load_themes
from app.domain.validation import StructureIssue, validate_deck
from app.render.pptx import PPTX_MEDIA_TYPE, render_deck_to_pptx
from app.services.template_library import (
    ExternalTemplatePublic,
    TemplateInspection,
    get_external_template_asset,
    get_external_template_inspection,
    list_external_templates,
    refresh_external_templates,
)

router = APIRouter(prefix="/design", tags=["design"])


@router.get("/layouts", response_model=list[Layout])
def list_layouts() -> list[Layout]:
    """下发布局定义。

    前端本可直接读 shared/ 下的同一批文件，这个接口的作用是让两端
    在运行时校验读到的是同一份数据，也让 OpenAPI 里带上布局的类型定义。
    """
    return list(load_layouts().values())


@router.get("/themes", response_model=list[Theme])
def list_themes() -> list[Theme]:
    return list(load_themes().values())


@router.get("/external-templates", response_model=list[ExternalTemplatePublic])
def list_templates_from_directory() -> list[ExternalTemplatePublic]:
    """列出 ``Template/`` 目录中的 PPTX 参考模板。

    GET 只读取本地文件结构与已有缓存，不能意外触发付费模型调用；需要重新理解
    图片和文案时，由前端明确调用下方 refresh 接口。
    """

    return list_external_templates()


@router.post("/external-templates/refresh", response_model=list[ExternalTemplatePublic])
async def refresh_templates_from_directory() -> list[ExternalTemplatePublic]:
    return await refresh_external_templates(force=True)


@router.get("/external-templates/{template_id}/inspection", response_model=TemplateInspection)
def inspect_template_from_directory(template_id: str) -> TemplateInspection:
    """逐页返回坐标、图层、组件和已缓存的 AI 语义，不会触发新的模型调用。"""

    inspection = get_external_template_inspection(template_id)
    if inspection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到外部模板：{template_id}",
        )
    return inspection


@router.get("/external-templates/{template_id}/assets/{asset_id}")
def get_template_asset_from_directory(template_id: str, asset_id: str) -> Response:
    """Serve one whitelisted source asset for the selected template visual layer."""

    asset = get_external_template_asset(template_id, asset_id)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未找到外部模板图片资产",
        )
    content_type, payload = asset
    return Response(
        content=payload,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/sample-deck", response_model=Deck)
def get_sample_deck(theme_id: str | None = Query(default=None)) -> Deck:
    deck = load_sample_deck()
    if theme_id is None:
        return deck

    if theme_id not in load_themes():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知主题：{theme_id}",
        )
    # 换主题只替换 theme_id，内容与页序原样保留
    return deck.model_copy(update={"theme_id": theme_id})


@router.get("/sample-deck/issues", response_model=list[StructureIssue])
def get_sample_deck_issues() -> list[StructureIssue]:
    return validate_deck(load_sample_deck())


@router.get("/sample-deck/pptx")
def export_sample_deck(theme_id: str | None = Query(default=None)) -> StreamingResponse:
    deck = load_sample_deck()
    if theme_id is not None and theme_id not in load_themes():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未知主题：{theme_id}",
        )

    buffer = render_deck_to_pptx(deck, theme_id)
    # 文件名含中文，必须用 RFC 5987 的 filename* 形式，否则部分浏览器会存成乱码
    filename = quote(f"{deck.title}.pptx")
    return StreamingResponse(
        buffer,
        media_type=PPTX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
