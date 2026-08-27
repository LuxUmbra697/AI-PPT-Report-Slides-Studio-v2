"""颜色令牌词表与和渲染端无关的颜色计算。

放在 domain 层是因为主题、块样式、氛围层都要用它，
而它们都不该依赖任何具体渲染器。
"""

from __future__ import annotations

import re
from typing import Literal

ColorToken = Literal[
    "background",
    "surface",
    "ink",
    "ink_soft",
    "ink_muted",
    "accent",
    "accent_soft",
    "line",
    "line_strong",
]

COLOR_TOKENS: frozenset[str] = frozenset(
    {
        "background",
        "surface",
        "ink",
        "ink_soft",
        "ink_muted",
        "accent",
        "accent_soft",
        "line",
        "line_strong",
    }
)

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def is_hex_color(value: str) -> bool:
    return bool(_HEX.match(value))


def normalize_color_value(value: str) -> str:
    """色令牌原样；#RRGGBB 统一为大写。"""
    if value in COLOR_TOKENS:
        return value
    if is_hex_color(value):
        return value.upper()
    raise ValueError("颜色必须是色令牌或 #RRGGBB")


def mix_hex(foreground: str, background: str, ratio: float) -> str:
    """按比例混合两个颜色，返回不透明的 #RRGGBB。

    PPTX 里给形状设透明度需要额外的 alpha XML，且部分播放器支持不一致。
    装饰图形只需要"更浅的同色"，直接在生成时把颜色算好更稳妥，
    两端也因此不必各自实现一套 alpha 合成。
    """
    ratio = min(1.0, max(0.0, ratio))
    fg = foreground.lstrip("#")
    bg = background.lstrip("#")
    channels = (
        round(int(fg[i : i + 2], 16) * ratio + int(bg[i : i + 2], 16) * (1 - ratio))
        for i in (0, 2, 4)
    )
    return "#" + "".join(f"{channel:02X}" for channel in channels)
