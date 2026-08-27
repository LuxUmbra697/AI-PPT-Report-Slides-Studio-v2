from __future__ import annotations

import json
import re
from copy import deepcopy
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.paths import THEMES_DIR
from app.domain.ambient import AmbientMotif
from app.domain.color import (
    COLOR_TOKENS,
    ColorToken,
    is_hex_color,
    normalize_color_value,
)
from app.domain.layout import TextStyleName

if TYPE_CHECKING:
    from app.models.project import Project

__all__ = [
    "COLOR_TOKENS",
    "ColorToken",
    "Fonts",
    "Palette",
    "Shape",
    "TextStyle",
    "Theme",
    "ThemeOverrides",
    "dump_overrides",
    "empty_overrides",
    "font_presets",
    "fonts_are_whitelisted",
    "get_theme",
    "is_hex_color",
    "load_themes",
    "merge_theme",
    "normalize_color_value",
    "resolve_project_theme",
    "resolve_theme",
]

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
_SIZE_STYLE_NAMES: tuple[TextStyleName, ...] = ("display", "title", "body", "bullet")
_MIN_SIZE_PT = 8.0
_MAX_SIZE_PT = 72.0


class Palette(BaseModel):
    background: str
    surface: str
    ink: str
    ink_soft: str
    ink_muted: str
    accent: str
    accent_soft: str
    line: str
    line_strong: str
    chart_series: list[str]


class FontFamily(BaseModel):
    """Web 与 PPTX 分别声明字体名。

    浏览器可用 webfont，而 PPTX 只能引用观众机器上已安装的字体，
    两者无法统一，因此显式分开声明，而不是让某一端将就另一端。
    """

    web: str
    pptx_latin: str
    pptx_east_asian: str


# emoji 字体默认值。给默认而不是要求每份主题都写，是因为它跟主题气质无关：
# 只有装了对应字体的机器才画得出彩色 emoji，换个字体名解决不了审美问题。
DEFAULT_EMOJI_FONT = FontFamily(
    web='"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif',
    pptx_latin="Segoe UI Emoji",
    pptx_east_asian="Segoe UI Emoji",
)


class Fonts(BaseModel):
    display: FontFamily
    body: FontFamily
    # emoji 必须单独成 run 并指定专用字体，否则中文正文字体里没有这些码位，
    # PowerPoint 会退化成方框或黑白轮廓。
    emoji: FontFamily = DEFAULT_EMOJI_FONT


class TextStyle(BaseModel):
    font: Literal["display", "body"]
    size_pt: float
    line_height: float
    weight: int
    letter_spacing_pt: float
    # 主题内是色令牌；元素覆盖后可能是 #RRGGBB
    color: str
    italic: bool = False

    @field_validator("color")
    @classmethod
    def token_or_hex(cls, value: str) -> str:
        return normalize_color_value(value)


class Shape(BaseModel):
    radius_pt: float
    border_width_pt: float
    bullet_marker: Literal["rule", "dot", "index"]


class Theme(BaseModel):
    id: str
    name: str
    description: str
    palette: Palette
    fonts: Fonts
    text_styles: dict[TextStyleName, TextStyle]
    shape: Shape
    # 氛围层：每页自动铺的装饰母题，换主题就换一套气质
    ambient: list[AmbientMotif] = []

    def color(self, token: str) -> str:
        # 元素覆盖可能把 color 写成 hex，渲染时透传即可
        if is_hex_color(token):
            return token.upper()
        value = getattr(self.palette, token, None)
        if not isinstance(value, str):
            raise KeyError(f"主题 {self.id} 不存在颜色令牌：{token}")
        return value

    def text_style(self, name: TextStyleName) -> TextStyle:
        try:
            return self.text_styles[name]
        except KeyError as error:
            raise KeyError(f"主题 {self.id} 未定义文本样式：{name}") from error

    def font_family(self, style: TextStyle) -> FontFamily:
        return self.fonts.display if style.font == "display" else self.fonts.body


class PaletteOverride(BaseModel):
    background: str | None = None
    surface: str | None = None
    ink: str | None = None
    ink_soft: str | None = None
    ink_muted: str | None = None
    accent: str | None = None
    accent_soft: str | None = None
    line: str | None = None
    line_strong: str | None = None

    @field_validator(
        "background",
        "surface",
        "ink",
        "ink_soft",
        "ink_muted",
        "accent",
        "accent_soft",
        "line",
        "line_strong",
    )
    @classmethod
    def hex_color(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HEX.match(value):
            raise ValueError("颜色必须是 #RRGGBB")
        return value.upper()


class TextStyleSizeOverride(BaseModel):
    size_pt: float | None = None

    @field_validator("size_pt")
    @classmethod
    def size_range(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value < _MIN_SIZE_PT or value > _MAX_SIZE_PT:
            raise ValueError(f"字号须在 {_MIN_SIZE_PT:g}–{_MAX_SIZE_PT:g} pt")
        return value


class ShapeOverride(BaseModel):
    radius_pt: float | None = Field(default=None, ge=0, le=48)
    bullet_marker: Literal["rule", "dot", "index"] | None = None


class ThemeOverrides(BaseModel):
    """相对预设主题的安全子集覆盖。"""

    palette: PaletteOverride | None = None
    fonts: Fonts | None = None
    text_styles: dict[str, TextStyleSizeOverride] | None = None
    shape: ShapeOverride | None = None

    @field_validator("text_styles")
    @classmethod
    def allowed_styles(
        cls, value: dict[str, TextStyleSizeOverride] | None
    ) -> dict[str, TextStyleSizeOverride] | None:
        if value is None:
            return None
        allowed = set(_SIZE_STYLE_NAMES)
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"不支持覆盖的文本样式：{', '.join(sorted(unknown))}")
        return value


@lru_cache
def load_themes() -> dict[str, Theme]:
    themes: dict[str, Theme] = {}
    for path in sorted(THEMES_DIR.glob("*.json")):
        theme = Theme.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if theme.id != path.stem:
            raise ValueError(f"主题 id 与文件名不一致：{path.name} 内声明为 {theme.id}")
        themes[theme.id] = theme
    if not themes:
        raise RuntimeError(f"未在 {THEMES_DIR} 找到任何主题定义")
    return themes


def get_theme(theme_id: str) -> Theme:
    try:
        return load_themes()[theme_id]
    except KeyError as error:
        raise KeyError(f"未知主题：{theme_id}") from error


def font_presets() -> dict[str, Fonts]:
    """精选字体对：直接复用各预设主题的 fonts。"""
    return {
        theme_id: theme.fonts.model_copy(deep=True) for theme_id, theme in load_themes().items()
    }


def fonts_are_whitelisted(fonts: Fonts) -> bool:
    dump = fonts.model_dump()
    return any(preset.model_dump() == dump for preset in font_presets().values())


def merge_theme(base: Theme, overrides: ThemeOverrides | dict[str, Any] | None) -> Theme:
    if not overrides:
        return base.model_copy(deep=True)

    parsed = (
        overrides
        if isinstance(overrides, ThemeOverrides)
        else ThemeOverrides.model_validate(overrides)
    )
    data = base.model_dump()

    if parsed.palette is not None:
        palette_patch = parsed.palette.model_dump(exclude_none=True)
        data["palette"].update(palette_patch)
        # 强调色变更时同步图表主色，避免图表仍是旧 accent
        if "accent" in palette_patch:
            series = list(data["palette"]["chart_series"])
            if series:
                series[0] = palette_patch["accent"]
            else:
                series = [palette_patch["accent"]]
            data["palette"]["chart_series"] = series

    if parsed.fonts is not None:
        data["fonts"] = parsed.fonts.model_dump()

    if parsed.text_styles:
        for name, style_patch in parsed.text_styles.items():
            if name not in data["text_styles"]:
                continue
            patch = style_patch.model_dump(exclude_none=True)
            data["text_styles"][name].update(patch)

    if parsed.shape is not None:
        data["shape"].update(parsed.shape.model_dump(exclude_none=True))

    return Theme.model_validate(data)


def resolve_theme(theme_id: str, overrides: ThemeOverrides | dict[str, Any] | None = None) -> Theme:
    return merge_theme(get_theme(theme_id), overrides)


def resolve_project_theme(project: Project) -> Theme:
    raw = getattr(project, "theme_overrides", None) or {}
    return resolve_theme(project.theme_id, raw)


def empty_overrides() -> dict[str, Any]:
    return {}


def dump_overrides(overrides: ThemeOverrides) -> dict[str, Any]:
    """持久化时去掉空嵌套，保持 JSON 紧凑。"""
    return deepcopy(overrides.model_dump(exclude_none=True))
