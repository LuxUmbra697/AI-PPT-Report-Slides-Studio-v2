"""统一解析页面块几何：fixed 走布局槽位，flex 走布局树 solver。"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.content import Slide
from app.domain.geometry import Rect
from app.domain.layout import get_layout


class PlacedBlock(BaseModel):
    block_id: str
    rect: Rect
    # 文本样式名（对应 TextStyleName）；用 str 避免与 layout 模块强耦合
    text_style: str | None = None


def resolve_slide_geometry(slide: Slide) -> list[PlacedBlock]:
    if slide.layout_mode == "flex":
        if slide.layout_tree is None:
            return []
        from app.domain.flex_solve import solve

        return solve(slide.layout_tree)

    layout = get_layout(slide.layout_id)
    result: list[PlacedBlock] = []
    for block in slide.blocks:
        slot = layout.slot_by_id(block.slot_id)
        if slot is not None:
            result.append(
                PlacedBlock(
                    block_id=block.id,
                    rect=slot.rect,
                    text_style=slot.text_style,
                )
            )
    return result


def placed_by_block_id(slide: Slide) -> dict[str, PlacedBlock]:
    return {p.block_id: p for p in resolve_slide_geometry(slide)}
