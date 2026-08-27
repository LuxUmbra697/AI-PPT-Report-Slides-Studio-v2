"""灵活布局预设皮肤：由容器 preset + 子区域外框生成装饰几何。"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import BaseModel

from app.domain.flex_layout import FlexContainer, GroupPreset
from app.domain.flex_solve import SkinFrame, solve_with_frames
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect

SkinKind = Literal[
    "fill_box",
    "outline_box",
    "side_line",
    "number_badge",
    "timeline_axis",
    "timeline_dot",
]

BOX_RADIUS_PT = 8.0
SIDE_LINE_WIDTH_PT = 4.0
BADGE_SIZE_PT = 18.0
BADGE_PAD_PT = 4.0
TIMELINE_AXIS_WIDTH_PT = 2.0
TIMELINE_DOT_SIZE_PT = 10.0
TIMELINE_LEFT_PT = 8.0


class SkinDecoration(BaseModel):
    kind: SkinKind
    rect: Rect
    color_token: str
    text: str | None = None
    radius_pt: float = 0


def iter_skin_decorations(tree: FlexContainer) -> list[SkinDecoration]:
    """遍历布局树，为带 preset 的容器子区域生成皮肤装饰。

    装饰使用 inset 前的外框；内容几何已由 solver 内缩。
    """
    _, frames = solve_with_frames(tree)
    return decorations_from_frames(frames)


def decorations_from_frames(frames: list[SkinFrame]) -> list[SkinDecoration]:
    if not frames:
        return []

    by_container: dict[tuple[str, GroupPreset], list[SkinFrame]] = defaultdict(list)
    for frame in frames:
        by_container[(frame.container_id, frame.preset)].append(frame)

    decorations: list[SkinDecoration] = []
    for (_container_id, preset), group in by_container.items():
        group = sorted(group, key=lambda f: f.child_index)
        if preset == "solid_boxes":
            decorations.extend(_solid_boxes(group))
        elif preset == "outline_boxes":
            decorations.extend(_outline_boxes(group))
        elif preset == "side_line":
            decorations.extend(_side_lines(group))
        elif preset == "numbered_steps":
            decorations.extend(_numbered_steps(group))
        elif preset == "timeline":
            decorations.extend(_timeline(group))
    return decorations


def _solid_boxes(frames: list[SkinFrame]) -> list[SkinDecoration]:
    return [
        SkinDecoration(
            kind="fill_box",
            rect=frame.rect,
            color_token="surface",
            radius_pt=BOX_RADIUS_PT,
        )
        for frame in frames
    ]


def _outline_boxes(frames: list[SkinFrame]) -> list[SkinDecoration]:
    return [
        SkinDecoration(
            kind="outline_box",
            rect=frame.rect,
            color_token="line",
            radius_pt=BOX_RADIUS_PT,
        )
        for frame in frames
    ]


def _side_lines(frames: list[SkinFrame]) -> list[SkinDecoration]:
    w = SIDE_LINE_WIDTH_PT / CANVAS_WIDTH_PT
    return [
        SkinDecoration(
            kind="side_line",
            rect=Rect(x=frame.rect.x, y=frame.rect.y, w=w, h=frame.rect.h),
            color_token="accent",
        )
        for frame in frames
    ]


def _numbered_steps(frames: list[SkinFrame]) -> list[SkinDecoration]:
    size_x = BADGE_SIZE_PT / CANVAS_WIDTH_PT
    size_y = BADGE_SIZE_PT / CANVAS_HEIGHT_PT
    pad_x = BADGE_PAD_PT / CANVAS_WIDTH_PT
    pad_y = BADGE_PAD_PT / CANVAS_HEIGHT_PT
    result: list[SkinDecoration] = []
    for frame in frames:
        result.append(
            SkinDecoration(
                kind="number_badge",
                rect=Rect(
                    x=frame.rect.x + pad_x,
                    y=frame.rect.y + pad_y,
                    w=size_x,
                    h=size_y,
                ),
                color_token="accent",
                text=str(frame.child_index + 1),
                radius_pt=BADGE_SIZE_PT / 2,
            )
        )
    return result


def _timeline(frames: list[SkinFrame]) -> list[SkinDecoration]:
    if not frames:
        return []

    left = TIMELINE_LEFT_PT / CANVAS_WIDTH_PT
    axis_w = TIMELINE_AXIS_WIDTH_PT / CANVAS_WIDTH_PT
    dot = TIMELINE_DOT_SIZE_PT
    dot_x = dot / CANVAS_WIDTH_PT
    dot_y = dot / CANVAS_HEIGHT_PT

    axis_center_x = frames[0].rect.x + left
    y0 = min(f.rect.y for f in frames)
    y1 = max(f.rect.y + f.rect.h for f in frames)

    decorations: list[SkinDecoration] = [
        SkinDecoration(
            kind="timeline_axis",
            rect=Rect(
                x=max(0.0, axis_center_x - axis_w / 2),
                y=y0,
                w=axis_w,
                h=max(y1 - y0, 1e-9),
            ),
            color_token="accent",
        )
    ]

    for frame in frames:
        cx = axis_center_x
        cy = frame.rect.y + frame.rect.h / 2
        decorations.append(
            SkinDecoration(
                kind="timeline_dot",
                rect=Rect(
                    x=max(0.0, cx - dot_x / 2),
                    y=max(0.0, cy - dot_y / 2),
                    w=dot_x,
                    h=dot_y,
                ),
                color_token="accent",
                radius_pt=dot / 2,
            )
        )
    return decorations
