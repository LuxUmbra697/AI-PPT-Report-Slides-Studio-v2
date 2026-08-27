from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from app.domain.content import Deck
from app.domain.layout import Layout, load_layouts
from app.domain.sample import load_sample_deck
from app.domain.theme import Theme, load_themes
from app.domain.validation import StructureIssue, validate_deck
from app.render.pptx import PPTX_MEDIA_TYPE, render_deck_to_pptx

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
