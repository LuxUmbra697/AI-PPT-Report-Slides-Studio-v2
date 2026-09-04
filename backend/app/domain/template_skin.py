"""模板级页面骨架：让主题不只换颜色，也真正改变正文组件的组织方式。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from app.domain.flex_skin import SkinDecoration
from app.domain.geometry import Rect

if TYPE_CHECKING:
    from app.domain.theme import Theme


def iter_template_decorations(
    theme: Theme,
    layout_id: str,
    occupied: Sequence[Rect],
) -> list[SkinDecoration]:
    """按主题视觉家族生成网页与 PPTX 共用的结构装饰。"""
    if layout_id == "cover":
        return _cover_decorations(theme.visual.cover_variant)

    body = _body_rects(occupied)
    variant = theme.visual.content_variant
    if variant == "cards":
        return _cards(body)
    if variant == "notebook":
        return _notebook(body)
    if variant == "dashboard":
        return _dashboard(body)
    if variant == "magazine":
        return _magazine(body)
    if variant == "panel":
        return _panel(body)
    return _clean(occupied)


def _body_rects(rects: Sequence[Rect]) -> list[Rect]:
    """去掉页首短标题框，剩余区域作为模板内容组件。"""
    body = [rect for rect in rects if rect.y >= 0.2 or rect.h >= 0.24]
    return sorted(body or list(rects), key=lambda rect: (rect.y, rect.x))


def _expand(rect: Rect, dx: float = 0.012, dy: float = 0.018) -> Rect:
    x = max(0.025, rect.x - dx)
    y = max(0.03, rect.y - dy)
    right = min(0.975, rect.right + dx)
    bottom = min(0.97, rect.bottom + dy)
    return Rect(x=x, y=y, w=max(0.001, right - x), h=max(0.001, bottom - y))


def _cover_decorations(variant: str) -> list[SkinDecoration]:
    if variant == "split":
        return [
            SkinDecoration(
                kind="fill_box",
                rect=Rect(x=0.61, y=0.0, w=0.39, h=1.0),
                color_token="surface",
            ),
            SkinDecoration(
                kind="side_line",
                rect=Rect(x=0.595, y=0.08, w=0.004, h=0.84),
                color_token="accent",
            ),
        ]
    if variant == "framed":
        return [
            SkinDecoration(
                kind="outline_box",
                rect=Rect(x=0.045, y=0.08, w=0.91, h=0.84),
                color_token="line_strong",
                radius_pt=10,
            ),
            SkinDecoration(
                kind="outline_box",
                rect=Rect(x=0.062, y=0.11, w=0.876, h=0.78),
                color_token="line",
                radius_pt=7,
            ),
        ]
    if variant == "poster":
        return [
            SkinDecoration(
                kind="side_line",
                rect=Rect(x=0.075, y=0.1, w=0.008, h=0.8),
                color_token="accent",
            ),
            SkinDecoration(
                kind="side_line",
                rect=Rect(x=0.1, y=0.875, w=0.35, h=0.006),
                color_token="line_strong",
            ),
        ]
    if variant == "spotlight":
        return [
            SkinDecoration(
                kind="timeline_dot",
                rect=Rect(x=0.66, y=0.16, w=0.24, h=0.42),
                color_token="accent_soft",
            ),
            SkinDecoration(
                kind="timeline_dot",
                rect=Rect(x=0.745, y=0.35, w=0.12, h=0.21),
                color_token="surface",
            ),
        ]
    if variant == "ribbon":
        return [
            SkinDecoration(
                kind="fill_box",
                rect=Rect(x=0.0, y=0.79, w=0.72, h=0.12),
                color_token="accent_soft",
                radius_pt=8,
            ),
            SkinDecoration(
                kind="side_line",
                rect=Rect(x=0.0, y=0.91, w=0.48, h=0.012),
                color_token="accent",
            ),
        ]
    return [
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=0.07, y=0.2, w=0.006, h=0.5),
            color_token="accent",
        )
    ]


def _cards(rects: Sequence[Rect]) -> list[SkinDecoration]:
    result: list[SkinDecoration] = []
    for rect in rects:
        frame = _expand(rect)
        result.extend(
            [
                SkinDecoration(
                    kind="fill_box",
                    rect=frame,
                    color_token="surface",
                    radius_pt=14,
                ),
                SkinDecoration(
                    kind="outline_box",
                    rect=frame,
                    color_token="line",
                    radius_pt=14,
                ),
            ]
        )
    return result


def _dashboard(rects: Sequence[Rect]) -> list[SkinDecoration]:
    result: list[SkinDecoration] = []
    for index, rect in enumerate(rects):
        frame = _expand(rect, 0.01, 0.014)
        result.extend(
            [
                SkinDecoration(
                    kind="outline_box",
                    rect=frame,
                    color_token="line_strong",
                    radius_pt=5,
                ),
                SkinDecoration(
                    kind="fill_box",
                    rect=Rect(
                        x=frame.x + 0.012,
                        y=frame.y,
                        w=min(0.075, frame.w * 0.28),
                        h=min(0.012, frame.h),
                    ),
                    color_token="accent" if index % 2 == 0 else "accent_soft",
                    radius_pt=3,
                ),
            ]
        )
    return result


def _notebook(rects: Sequence[Rect]) -> list[SkinDecoration]:
    if not rects:
        return []
    frame = _expand(_bounds(rects), 0.016, 0.02)
    result = [
        SkinDecoration(
            kind="fill_box",
            rect=frame,
            color_token="surface",
            radius_pt=8,
        ),
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=frame.x + 0.038, y=frame.y, w=0.004, h=frame.h),
            color_token="accent_soft",
        ),
    ]
    for index in range(4):
        result.append(
            SkinDecoration(
                kind="timeline_dot",
                rect=Rect(
                    x=max(0.002, frame.x - 0.006),
                    y=frame.y + frame.h * (index + 1) / 5 - 0.008,
                    w=0.012,
                    h=0.016,
                ),
                color_token="line_strong",
            )
        )
    return result


def _magazine(rects: Sequence[Rect]) -> list[SkinDecoration]:
    if not rects:
        return []
    frame = _expand(_bounds(rects), 0.015, 0.015)
    return [
        SkinDecoration(
            kind="fill_box",
            rect=Rect(x=frame.x, y=frame.y, w=min(0.13, frame.w), h=frame.h),
            color_token="accent_soft",
        ),
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=frame.x, y=frame.y, w=0.008, h=frame.h),
            color_token="accent",
        ),
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=frame.x, y=frame.y, w=frame.w, h=0.006),
            color_token="line_strong",
        ),
    ]


def _panel(rects: Sequence[Rect]) -> list[SkinDecoration]:
    if not rects:
        return []
    frame = _expand(_bounds(rects), 0.02, 0.025)
    inner = _expand(_bounds(rects), 0.008, 0.012)
    return [
        SkinDecoration(
            kind="outline_box",
            rect=frame,
            color_token="line_strong",
            radius_pt=6,
        ),
        SkinDecoration(
            kind="outline_box",
            rect=inner,
            color_token="line",
            radius_pt=4,
        ),
        SkinDecoration(
            kind="fill_box",
            rect=Rect(x=frame.x + 0.025, y=frame.y, w=0.11, h=0.012),
            color_token="accent",
            radius_pt=3,
        ),
    ]


def _clean(rects: Sequence[Rect]) -> list[SkinDecoration]:
    if not rects:
        return []
    title = min(rects, key=lambda rect: rect.y)
    y = min(0.94, title.bottom + 0.018)
    return [
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=title.x, y=y, w=min(0.16, title.w), h=0.005),
            color_token="accent",
        )
    ]


def _bounds(rects: Sequence[Rect]) -> Rect:
    left = min(rect.x for rect in rects)
    top = min(rect.y for rect in rects)
    right = max(rect.right for rect in rects)
    bottom = max(rect.bottom for rect in rects)
    return Rect(x=left, y=top, w=right - left, h=bottom - top)
