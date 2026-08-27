"""将 FlexContainer 树递归求解为归一化矩形列表。

纵向按 grow 权重分配，横向按 ratios；间隙与预设内边距用画布 pt 换算为归一化。
不读取字体度量。
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.flex_layout import PRESET_INSET_PT, FlexContainer, FlexLeaf, FlexNode, GroupPreset
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, SAFE_AREA, Rect
from app.domain.slide_geometry import PlacedBlock

# 判定叶子是否贴着安全区某条边的容差，约合 2pt
_EDGE_EPS = 0.0025


class SkinFrame(BaseModel):
    """容器子区域外框（preset inset 之前），供皮肤装饰使用。"""

    container_id: str
    preset: GroupPreset
    child_index: int
    rect: Rect


def solve(root: FlexContainer, canvas: Rect | None = None) -> list[PlacedBlock]:
    placed, _ = solve_with_frames(root, canvas)
    return placed


def solve_with_frames(
    root: FlexContainer, canvas: Rect | None = None
) -> tuple[list[PlacedBlock], list[SkinFrame]]:
    area = canvas or SAFE_AREA
    frames: list[SkinFrame] = []
    placed = _solve_container(root, area, frames)
    return placed, frames


def _solve_container(
    node: FlexContainer, area: Rect, frames: list[SkinFrame]
) -> list[PlacedBlock]:
    children = node.children
    if not children:
        return []

    child_areas = _split_area(node, area)
    placed: list[PlacedBlock] = []
    for index, (child, child_area) in enumerate(zip(children, child_areas, strict=True)):
        if node.preset is not None:
            frames.append(
                SkinFrame(
                    container_id=node.id,
                    preset=node.preset,
                    child_index=index,
                    rect=child_area,
                )
            )
        content = _apply_preset_inset(node, child_area)
        placed.extend(_solve_node(child, content, frames))
    return placed


def _solve_node(
    node: FlexNode, area: Rect, frames: list[SkinFrame]
) -> list[PlacedBlock]:
    if isinstance(node, FlexLeaf):
        return [
            PlacedBlock(
                block_id=node.block_id,
                rect=_apply_offset(_apply_bleed(area, node), node),
                text_style=node.text_style,
            )
        ]
    return _solve_container(node, area, frames)


def _apply_bleed(area: Rect, leaf: FlexLeaf) -> Rect:
    """出血：把贴着安全区边界的叶子扩展到画布边缘。

    只扩展它本来就贴边的方向，中间的块不会莫名其妙变大。
    """
    if not leaf.bleed:
        return area
    left = 0.0 if area.x - SAFE_AREA.x <= _EDGE_EPS else area.x
    top = 0.0 if area.y - SAFE_AREA.y <= _EDGE_EPS else area.y
    right = 1.0 if SAFE_AREA.right - area.right <= _EDGE_EPS else area.right
    bottom = 1.0 if SAFE_AREA.bottom - area.bottom <= _EDGE_EPS else area.bottom
    return Rect(x=left, y=top, w=right - left, h=bottom - top)


def _apply_offset(area: Rect, leaf: FlexLeaf) -> Rect:
    """应用叶子的像素级平移，并钳制在画布内。

    钳制是硬约束：偏移只挪位置，不允许把块推出 16:9 画布而阻断导出。
    """
    if not leaf.offset_x_pt and not leaf.offset_y_pt:
        return area
    dx = leaf.offset_x_pt / CANVAS_WIDTH_PT
    dy = leaf.offset_y_pt / CANVAS_HEIGHT_PT
    return Rect(
        x=_clamp_start(area.x + dx, area.w),
        y=_clamp_start(area.y + dy, area.h),
        w=area.w,
        h=area.h,
    )


def _clamp_start(start: float, extent: float) -> float:
    return min(max(start, 0.0), max(1.0 - extent, 0.0))


def _fit_gaps(gap_norm: float, n: int, extent: float) -> tuple[float, float]:
    """返回（单个间隙, 间隙总量）；间隙总量超过可用长度时按比例压缩。

    压缩而非溢出，保证子区域始终落在父区域内。
    """
    if n <= 1 or gap_norm <= 0.0:
        return 0.0, 0.0
    total = (n - 1) * gap_norm
    if total <= extent:
        return gap_norm, total
    if extent <= 0.0:
        return 0.0, 0.0
    return extent / (n - 1), extent


def _split_area(node: FlexContainer, area: Rect) -> list[Rect]:
    n = len(node.children)
    if n == 0:
        return []

    if node.type == "row":
        gap_norm, total_gap = _fit_gaps(node.gap_pt / CANVAS_WIDTH_PT, n, area.w)
        weights = _row_weights(node.ratios, n)
        total_w = max(area.w - total_gap, 0.0)
        end = area.x + area.w
        cursor = area.x
        rects: list[Rect] = []
        for index, weight in enumerate(weights):
            # 末项贴紧父区域右缘，吸收浮点残差
            w = end - cursor if index == n - 1 else total_w * weight
            rects.append(Rect(x=cursor, y=area.y, w=max(w, 1e-9), h=area.h))
            cursor += w
            if index < n - 1:
                cursor += gap_norm
        return rects

    gap_norm, total_gap = _fit_gaps(node.gap_pt / CANVAS_HEIGHT_PT, n, area.h)
    weights = _column_weights(node.children)
    total_h = max(area.h - total_gap, 0.0)
    end = area.y + area.h
    cursor = area.y
    rects = []
    for index, weight in enumerate(weights):
        h = end - cursor if index == n - 1 else total_h * weight
        rects.append(Rect(x=area.x, y=cursor, w=area.w, h=max(h, 1e-9)))
        cursor += h
        if index < n - 1:
            cursor += gap_norm
    return rects


def _row_weights(ratios: list[float] | None, n: int) -> list[float]:
    if ratios is None or len(ratios) != n:
        return [1.0 / n] * n
    total = sum(ratios)
    if total <= 0:
        return [1.0 / n] * n
    return [r / total for r in ratios]


def _column_weights(children: list[FlexNode]) -> list[float]:
    grows = [child.grow for child in children]
    total = sum(grows)
    if total <= 0:
        n = len(children)
        return [1.0 / n] * n
    return [g / total for g in grows]


def _apply_preset_inset(container: FlexContainer, child_area: Rect) -> Rect:
    if container.preset is None:
        return child_area
    inset_pt = PRESET_INSET_PT[container.preset]
    inset_x = inset_pt / CANVAS_WIDTH_PT
    inset_y = inset_pt / CANVAS_HEIGHT_PT
    w = child_area.w - 2 * inset_x
    h = child_area.h - 2 * inset_y
    if w <= 0 or h <= 0:
        return child_area
    return Rect(
        x=child_area.x + inset_x,
        y=child_area.y + inset_y,
        w=w,
        h=h,
    )
