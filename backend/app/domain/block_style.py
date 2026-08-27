"""单个内容块相对主题的样式覆盖。

只改视觉表现，不动槽位几何。合并结果仍是普通 TextStyle / ResolvedBox，
Web、PPTX、溢出校验共用同一套逻辑。

本模块刻意不在顶层依赖 theme/layout，避免 content → block_style → theme → layout → content 环。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from app.domain.layout import TextStyleName
    from app.domain.theme import TextStyle, Theme


def _normalize_color_value(value: str) -> str:
    from app.domain.theme import normalize_color_value

    return normalize_color_value(value)


class BlockStyle(BaseModel):
    """单个元素相对主题的样式覆盖。"""

    size_pt: float | None = Field(default=None, ge=8, le=72)
    color: str | None = None
    weight: int | None = Field(default=None, ge=300, le=900)
    italic: bool | None = None
    align: Literal["left", "center", "right"] | None = None
    # 令牌 / #RRGGBB / "none"；none 表示显式无填充
    fill: str | None = None
    radius_pt: float | None = Field(default=None, ge=0, le=48)
    border_color: str | None = None
    border_width_pt: float | None = Field(default=None, ge=0, le=6)
    padding_pt: float | None = Field(default=None, ge=0, le=48)

    @field_validator("color", "border_color")
    @classmethod
    def color_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_color_value(value)

    @field_validator("fill")
    @classmethod
    def fill_value(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value == "none":
            return "none"
        return _normalize_color_value(value)

    def is_empty(self) -> bool:
        return self.model_dump(exclude_none=True) == {}


class ResolvedBox(BaseModel):
    """容器解析结果，两端与导出共用。"""

    fill: str | None
    radius_pt: float
    border_width_pt: float
    border_color: str | None
    padding_pt: float

    @property
    def has_fill(self) -> bool:
        return self.fill is not None

    @property
    def has_border(self) -> bool:
        return self.border_width_pt > 0 and self.border_color is not None

    @property
    def has_chrome(self) -> bool:
        return self.has_fill or self.has_border or self.padding_pt > 0


def merge_text_style(
    theme: Theme,
    name: TextStyleName,
    style: BlockStyle | None,
) -> TextStyle:
    from app.domain.theme import TextStyle

    base = theme.text_style(name)
    if style is None:
        return base.model_copy(deep=True)

    data = base.model_dump()
    if style.size_pt is not None:
        data["size_pt"] = style.size_pt
    if style.color is not None:
        data["color"] = style.color
    if style.weight is not None:
        data["weight"] = style.weight
    if style.italic is not None:
        data["italic"] = style.italic
    return TextStyle.model_validate(data)


def resolve_box(theme: Theme, style: BlockStyle | None) -> ResolvedBox:
    if style is None:
        return ResolvedBox(
            fill=None,
            radius_pt=0,
            border_width_pt=0,
            border_color=None,
            padding_pt=0,
        )

    fill: str | None = None
    if style.fill is not None and style.fill != "none":
        fill = theme.color(style.fill)

    border_color: str | None = None
    border_width = style.border_width_pt or 0.0
    if style.border_color is not None and border_width > 0:
        border_color = theme.color(style.border_color)

    return ResolvedBox(
        fill=fill,
        radius_pt=style.radius_pt or 0.0,
        border_width_pt=border_width if border_color is not None else 0.0,
        border_color=border_color,
        padding_pt=style.padding_pt or 0.0,
    )


def content_rect_pt(
    width_pt: float,
    height_pt: float,
    *,
    padding_pt: float,
) -> tuple[float, float]:
    """扣掉内边距后的可用宽高，供溢出度量使用。"""
    pad = max(0.0, padding_pt) * 2
    return max(1.0, width_pt - pad), max(1.0, height_pt - pad)
