"""按内容自然高度回填 column grow，避免内容少的块白占大片空间。

solver 只按权重瓜分画布、不读字体度量，所以预设里写死的 grow 会让
「3 条要点」和「8 条要点」占一样高。这里在生成期用 text_metrics 估算每个
叶子的自然高度，换算成 grow；富余高度交给可吸收的块（图片/图表）或尾部
占位块，而不是摊回文字块。

纯函数，只改 grow 与尾部占位块，不动块内容与 row 的横向比例。
"""

from __future__ import annotations

from app.domain.block_style import content_rect_pt, merge_text_style, resolve_box
from app.domain.content import Block
from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode, is_spacer
from app.domain.flex_normalize import GROW_MAX, GROW_MIN, TITLE_STYLES, normalize
from app.domain.flex_solve import solve
from app.domain.geometry import (
    CANVAS_HEIGHT_PT,
    CANVAS_WIDTH_PT,
    SAFE_AREA_HEIGHT_PT,
    SAFE_AREA_WIDTH_PT,
)
from app.domain.text_metrics import TEXTBOX_MARGIN_PT, measure_bullets, measure_text
from app.domain.theme import Theme

# 文字块在自然高度上留一点呼吸余量，避免贴着字挤成一条
_BREATHING = 1.12

# 没有可度量内容的块给一个偏好高度（pt，相对 540 高画布）
_PREFERRED_HEIGHT_PT: dict[str, float] = {
    "image": 224.0,
    "chart": 240.0,
    "kpi": 96.0,
    "callout": 48.0,
}
_TABLE_ROW_HEIGHT_PT = 26.0
_CARD_BASE_HEIGHT_PT = 88.0
_CARD_LINE_HEIGHT_PT = 22.0
_MIN_LEAF_HEIGHT_PT = 36.0

# 这些块可以无限吃掉富余高度：拉大反而更好看
_ABSORBING_TYPES = frozenset({"image", "chart"})

# 有限吸收：可在偏好高度的这个倍数内吃富余（KPI/表/卡片拉高观感更好）
_LIMITED_ABSORB_TYPES = frozenset({"kpi", "table", "cards"})
_LIMITED_ABSORB_MAX_RATIO = 1.6

# 富余高度小于列高的这个比例时不再造占位块，直接摊给内容
_SURPLUS_MIN_RATIO = 0.06

# 尾部占位块最多吃掉列高的这个比例：只做收边，不吞下半页
_MAX_SPACER_RATIO = 0.16

# 封面/章节页不铺满，而是把富余拆到内容上下两侧；上方占这个比例，
# 让标题落在视觉中线偏上，与固定布局 cover.json 的观感一致
_CENTERED_ROLES = frozenset({"cover", "section"})
_LEAD_SPACER_RATIO = 0.38


def fit_tree_to_content(
    tree: FlexContainer,
    blocks: list[Block],
    *,
    theme: Theme,
    page_role: str | None = None,
) -> FlexContainer:
    """返回 grow 已按内容自然高度重算的新树。

    只在生成期调用：用户手动调过版面的页面不应被重新压扁。
    """
    block_map = {block.id: block for block in blocks}
    # 叶子宽度只由 row ratios 决定，与 grow 无关，因此求解一次即可定
    widths_pt = {
        placed.block_id: placed.rect.w * CANVAS_WIDTH_PT for placed in solve(tree)
    }
    ctx = _FitContext(
        block_map=block_map,
        widths_pt=widths_pt,
        theme=theme,
        centered=page_role in _CENTERED_ROLES,
    )
    fitted = _fit_container(tree, SAFE_AREA_HEIGHT_PT, ctx, is_root=True)
    # 高度来自真实度量，不需要再按标题上限回钳
    return normalize(fitted, clamp_title_grow=False)


class _FitContext:
    def __init__(
        self,
        *,
        block_map: dict[str, Block],
        widths_pt: dict[str, float],
        theme: Theme,
        centered: bool = False,
    ) -> None:
        self.block_map = block_map
        self.widths_pt = widths_pt
        self.theme = theme
        self.centered = centered


def _fit_container(
    node: FlexContainer,
    avail_h_pt: float,
    ctx: _FitContext,
    *,
    is_root: bool = False,
) -> FlexContainer:
    if not node.children:
        return node

    if node.type == "row":
        # 同一行的子项共享整行高度，横向比例不在本函数职责内
        return node.model_copy(
            update={
                "children": [_fit_child(child, avail_h_pt, ctx) for child in node.children]
            }
        )

    children = list(node.children)
    gaps_pt = max(len(children) - 1, 0) * node.gap_pt
    targets = [_natural_height_pt(child, ctx) for child in children]
    surplus = avail_h_pt - gaps_pt - sum(targets)

    if surplus > 0 and is_root and ctx.centered:
        children, targets = _center_vertically(children, targets, surplus, node.gap_pt)
    elif surplus > 0:
        children, targets = _absorb_surplus(
            children, targets, surplus, avail_h_pt, node.gap_pt, ctx
        )

    grows = _targets_to_grows(targets)
    fitted = [
        _fit_child(child, target, ctx).model_copy(update={"grow": grow})
        for child, target, grow in zip(children, targets, grows, strict=True)
    ]
    return node.model_copy(update={"children": fitted})


def _fit_child(child: FlexNode, avail_h_pt: float, ctx: _FitContext) -> FlexNode:
    if isinstance(child, FlexContainer):
        return _fit_container(child, avail_h_pt, ctx)
    return child


def _absorb_surplus(
    children: list[FlexNode],
    targets: list[float],
    surplus: float,
    avail_h_pt: float,
    gap_pt: float,
    ctx: _FitContext,
) -> tuple[list[FlexNode], list[float]]:
    """把富余高度交给吸收型块或尾部占位块，不摊回文字块。"""
    remaining = surplus

    # 1) 图片/图表无限吸收
    absorbers = [index for index, child in enumerate(children) if _is_absorbing(child, ctx)]
    if absorbers:
        return children, _distribute(targets, remaining, absorbers)

    # 2) KPI/表/卡片有限吸收（偏好高度 × 1.6）
    limited = [
        index for index, child in enumerate(children) if _is_limited_absorber(child, ctx)
    ]
    if limited:
        room = [
            max(0.0, targets[index] * _LIMITED_ABSORB_MAX_RATIO - targets[index])
            for index in limited
        ]
        take = min(remaining, sum(room))
        if take > 0:
            targets = _distribute_capped(targets, take, limited, room)
            remaining -= take

    if remaining <= 0:
        return children, targets

    # 3) 加一个占位块要多算一道间隙；富余不足时不值得造，直接摊给正文
    surplus_after_gap = remaining - gap_pt
    if surplus_after_gap < avail_h_pt * _SURPLUS_MIN_RATIO:
        body = [index for index, child in enumerate(children) if not _is_title(child)]
        return children, _distribute(targets, remaining, body or range(len(targets)))

    # 占位块只做收边；剩下的给正文而不是标题
    spacer_h = min(surplus_after_gap, avail_h_pt * _MAX_SPACER_RATIO)
    leftover = surplus_after_gap - spacer_h
    if leftover > 0:
        body = [index for index, child in enumerate(children) if not _is_title(child)]
        targets = _distribute(targets, leftover, body or range(len(targets)))

    return [*children, _fit_spacer("spacer-fit")], [*targets, spacer_h]


def _center_vertically(
    children: list[FlexNode],
    targets: list[float],
    surplus: float,
    gap_pt: float,
) -> tuple[list[FlexNode], list[float]]:
    """封面/章节页：富余拆到内容上下两侧，内容整体落在视觉中线偏上。"""
    budget = surplus - 2 * gap_pt
    if budget <= 0:
        return children, targets
    lead = budget * _LEAD_SPACER_RATIO
    return (
        [_fit_spacer("spacer-fit-lead"), *children, _fit_spacer("spacer-fit-trail")],
        [lead, *targets, budget - lead],
    )


def _fit_spacer(node_id: str) -> FlexContainer:
    return FlexContainer(type="column", id=node_id, children=[], gap_pt=0.0, grow=1.0)


def _distribute(targets: list[float], amount: float, indices) -> list[float]:
    """按现有目标高度的比例把 amount 分给指定下标。"""
    picked = list(indices)
    if not picked or amount <= 0:
        return list(targets)
    weight_sum = sum(targets[index] for index in picked)
    result = list(targets)
    if weight_sum <= 0:
        share = amount / len(picked)
        for index in picked:
            result[index] += share
        return result
    for index in picked:
        result[index] += amount * targets[index] / weight_sum
    return result


def _distribute_capped(
    targets: list[float],
    amount: float,
    indices: list[int],
    rooms: list[float],
) -> list[float]:
    """按各块剩余容量比例分配，且不超过各自 room。"""
    if not indices or amount <= 0:
        return list(targets)
    room_sum = sum(rooms)
    if room_sum <= 0:
        return list(targets)
    result = list(targets)
    for index, room in zip(indices, rooms, strict=True):
        result[index] += amount * room / room_sum
    return result


def _is_title(node: FlexNode) -> bool:
    return isinstance(node, FlexLeaf) and node.text_style in TITLE_STYLES


def _targets_to_grows(targets: list[float]) -> list[float]:
    """把目标高度换算成均值为 1 的 grow，并夹在 normalize 允许的区间内。"""
    n = len(targets)
    total = sum(targets)
    if n == 0:
        return []
    if total <= 0:
        return [1.0] * n
    return [min(GROW_MAX, max(GROW_MIN, target / total * n)) for target in targets]


def _is_absorbing(node: FlexNode, ctx: _FitContext) -> bool:
    """拉大反而更好看的节点：图片/图表，以及已有的占位块。"""
    if isinstance(node, FlexLeaf):
        block = ctx.block_map.get(node.block_id)
        return block is not None and block.type in _ABSORBING_TYPES
    if is_spacer(node):
        return True
    return any(_is_absorbing(child, ctx) for child in node.children)


def _is_limited_absorber(node: FlexNode, ctx: _FitContext) -> bool:
    if isinstance(node, FlexLeaf):
        block = ctx.block_map.get(node.block_id)
        return block is not None and block.type in _LIMITED_ABSORB_TYPES
    if is_spacer(node):
        return False
    return any(_is_limited_absorber(child, ctx) for child in node.children)


def _natural_height_pt(node: FlexNode, ctx: _FitContext) -> float:
    if isinstance(node, FlexLeaf):
        return _leaf_height_pt(node, ctx)

    if is_spacer(node) and not node.children:
        return 0.0
    if not node.children:
        return _MIN_LEAF_HEIGHT_PT

    heights = [_natural_height_pt(child, ctx) for child in node.children]
    if node.type == "row":
        return max(heights)
    return sum(heights) + max(len(heights) - 1, 0) * node.gap_pt


def _leaf_height_pt(leaf: FlexLeaf, ctx: _FitContext) -> float:
    block = ctx.block_map.get(leaf.block_id)
    if block is None:
        return _MIN_LEAF_HEIGHT_PT

    if block.type == "text":
        return _measured_height_pt(leaf, block, ctx, kind="text")
    if block.type == "bullets":
        return _measured_height_pt(leaf, block, ctx, kind="bullets")
    if block.type == "table":
        rows = 1 + len(block.rows)
        return max(_MIN_LEAF_HEIGHT_PT, rows * _TABLE_ROW_HEIGHT_PT)
    if block.type == "cards":
        # 横排卡片高度取最高一张的标题+描述估算
        tallest = max(
            (
                _CARD_BASE_HEIGHT_PT
                + max(0, (len(item.title) + len(item.desc)) // 28) * _CARD_LINE_HEIGHT_PT
            )
            for item in block.items
        )
        return max(_MIN_LEAF_HEIGHT_PT, tallest)
    if block.type == "callout":
        return _PREFERRED_HEIGHT_PT["callout"]
    return _PREFERRED_HEIGHT_PT.get(block.type, _MIN_LEAF_HEIGHT_PT)


def _measured_height_pt(
    leaf: FlexLeaf,
    block: Block,
    ctx: _FitContext,
    *,
    kind: str,
) -> float:
    width_pt = ctx.widths_pt.get(leaf.block_id, SAFE_AREA_WIDTH_PT)
    box = resolve_box(ctx.theme, block.style)
    # 度量只关心宽度；高度给足，避免把 overflow 判定卷进来
    avail_w, _ = content_rect_pt(width_pt, CANVAS_HEIGHT_PT, padding_pt=box.padding_pt)
    default_style = "bullet" if kind == "bullets" else "body"
    style = merge_text_style(ctx.theme, leaf.text_style or default_style, block.style)

    if kind == "bullets":
        used = measure_bullets(
            block.items, style=style, width_pt=avail_w, height_pt=CANVAS_HEIGHT_PT
        ).height_pt
    else:
        used = measure_text(
            block.text, style=style, width_pt=avail_w, height_pt=CANVAS_HEIGHT_PT
        ).height_pt

    chrome = 2 * TEXTBOX_MARGIN_PT + 2 * box.padding_pt
    return max(_MIN_LEAF_HEIGHT_PT, used * _BREATHING + chrome)
