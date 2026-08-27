"""按最小可读宽度修正 row 的横向分配。

solver 只按 ratios 瓜分宽度、不认识文字，所以「左边一大段正文 + 右边四张卡」
这类树会把卡片压到几十 pt，中文一行只剩四五个字。这里在生成期把过窄的列补回来：
先从同行宽裕的兄弟借，借不够就把并排的卡片折成两行。

纯函数，只改 row 的 ratios 与过窄子节点的分组，不动块内容与纵向 grow。
必须跑在 flex_fit 之前：高度度量依赖的列宽得先定下来。
"""

from __future__ import annotations

from app.domain.block_style import merge_text_style, resolve_box
from app.domain.content import Block
from app.domain.flex_layout import PRESET_INSET_PT, FlexContainer, FlexLeaf, FlexNode, is_spacer
from app.domain.flex_normalize import normalize
from app.domain.geometry import SAFE_AREA_WIDTH_PT
from app.domain.text_metrics import BULLET_INDENT_PT
from app.domain.theme import Theme

# 一行至少排得下这么多个全角字。参考成稿的卡片正文约 14 字/行，
# 这里取更宽松的下限：只拦「窄到读不了」的情况，不去规定审美。
MIN_CHARS_PER_LINE = 9.0

# 拉丁字母按全角的这个比例折算，与 text_metrics 的估算系数一致
_LATIN_EM = 0.55

# 与 app.render.pptx / 前端 CardsView 对齐的卡片排版常量
_CARD_GAP_PT = 16.0
_CARD_PAD_PT = 12.0
# KPI 在两端都有一个不小于 14pt 的内边距
_KPI_PAD_PT = 14.0

_MIN_VISUAL_WIDTH_PT = 96.0
_MIN_TABLE_COLUMN_PT = 56.0
_MIN_LEAF_WIDTH_PT = 48.0

# 两列 row 的 ratios 会被 normalize 吸附到设计比值，最多挪动 RATIO_SNAP_TOLERANCE。
# 预留略大于该容差的余量，避免刚补够宽度又被吸附吃回去。
_SNAP_SLACK_RATIO = 0.026

_EPS = 0.5

# 折行补救最多再走一轮：一次不够说明宽度是真不够，交给溢出告警。
_MAX_PASSES = 2


def fit_row_widths(
    tree: FlexContainer,
    blocks: list[Block],
    *,
    theme: Theme,
) -> FlexContainer:
    """返回横向分配已满足最小可读宽度的新树。

    只在生成期调用：用户手动拖出来的窄列是他自己的选择，不该被改回去。
    """
    ctx = _WidthContext(block_map={block.id: block for block in blocks}, theme=theme)
    return normalize(_fix_container(tree, SAFE_AREA_WIDTH_PT, ctx))


class _WidthContext:
    def __init__(self, *, block_map: dict[str, Block], theme: Theme) -> None:
        self.block_map = block_map
        self.theme = theme

    def min_width_pt(self, node: FlexNode) -> float:
        """节点内容排得下所需的最小宽度。"""
        return _min_width_pt(node, self)


def _fix_container(node: FlexContainer, avail_w_pt: float, ctx: _WidthContext) -> FlexContainer:
    if not node.children:
        return node
    if node.type == "row":
        return _fix_row(node, avail_w_pt, ctx, pass_index=0)
    inner = _inset(node, avail_w_pt)
    return node.model_copy(
        update={"children": [_fix_child(child, inner, ctx) for child in node.children]}
    )


def _fix_child(child: FlexNode, avail_w_pt: float, ctx: _WidthContext) -> FlexNode:
    if isinstance(child, FlexContainer):
        return _fix_container(child, avail_w_pt, ctx)
    return child


def _fix_row(
    node: FlexContainer,
    avail_w_pt: float,
    ctx: _WidthContext,
    *,
    pass_index: int,
) -> FlexContainer:
    n = len(node.children)
    inner_total = max(avail_w_pt - node.gap_pt * (n - 1), 1.0)
    percents = _ratio_percents(node)
    allocs = [inner_total * percent / 100.0 for percent in percents]
    # preset 会在每个子区域内再收一圈边，最小宽度要连这圈一起要
    chrome = 2 * PRESET_INSET_PT[node.preset] if node.preset is not None else 0.0
    slack = inner_total * _SNAP_SLACK_RATIO if n == 2 else 0.0
    needs = [ctx.min_width_pt(child) + chrome + slack for child in node.children]

    if all(alloc + _EPS >= need for alloc, need in zip(allocs, needs, strict=True)):
        return _recurse_row(node, allocs, ctx)

    if sum(needs) <= inner_total:
        balanced = _rebalance(allocs, needs)
        return _recurse_row(_with_allocs(node, balanced), balanced, ctx)

    regrouped = _regroup(node, allocs, needs, ctx, pass_index=pass_index)
    if regrouped is None:
        return _recurse_row(node, allocs, ctx)
    if regrouped.type != "row":
        return _fix_container(regrouped, avail_w_pt, ctx)
    if pass_index + 1 >= _MAX_PASSES:
        return _recurse_row(regrouped, _allocs_of(regrouped, avail_w_pt), ctx)
    return _fix_row(regrouped, avail_w_pt, ctx, pass_index=pass_index + 1)


def _recurse_row(node: FlexContainer, allocs: list[float], ctx: _WidthContext) -> FlexContainer:
    inner = [_inset(node, alloc) for alloc in allocs]
    return node.model_copy(
        update={
            "children": [
                _fix_child(child, width, ctx)
                for child, width in zip(node.children, inner, strict=True)
            ]
        }
    )


def _rebalance(allocs: list[float], needs: list[float]) -> list[float]:
    """让过窄的列拿到 need，缺口按富余比例从宽裕的兄弟身上扣，总宽不变。"""
    surplus = [max(0.0, alloc - need) for alloc, need in zip(allocs, needs, strict=True)]
    pool = sum(surplus)
    deficit = sum(max(0.0, need - alloc) for alloc, need in zip(allocs, needs, strict=True))
    if pool <= 0 or deficit <= 0:
        return list(allocs)
    ratio = min(1.0, deficit / pool)
    return [
        max(alloc, need) if alloc < need else alloc - room * ratio
        for alloc, need, room in zip(allocs, needs, surplus, strict=True)
    ]


def _regroup(
    node: FlexContainer,
    allocs: list[float],
    needs: list[float],
    ctx: _WidthContext,
    *,
    pass_index: int,
) -> FlexContainer | None:
    """把并排挤不下的一串子节点折成多行，返回改造后的容器；无从下手时返回 None。"""
    run = _longest_needy_run(allocs, needs)
    if run is None:
        return None

    gap = node.gap_pt
    group_w = sum(allocs[index] for index in run) + gap * (len(run) - 1)
    unit = max(needs[index] for index in run)
    per_row = int((group_w + gap) // (unit + gap))
    per_row = max(1, min(per_row, len(run) - 1))
    chunks = [run[start : start + per_row] for start in range(0, len(run), per_row)]
    if len(chunks) <= 1:
        return None

    rows = [
        FlexContainer(
            type="row",
            id=f"{node.id}__wrap{pass_index}r{index}",
            children=[node.children[position] for position in chunk],
            gap_pt=gap,
            ratios=[100.0 / len(chunk)] * len(chunk),
            grow=1.0,
        )
        for index, chunk in enumerate(chunks)
    ]
    wrapper = FlexContainer(
        type="column",
        id=f"{node.id}__wrap{pass_index}",
        children=rows,
        gap_pt=gap,
        grow=max(node.children[position].grow for position in run),
    )

    head, tail = run[0], run[-1] + 1
    children = [*node.children[:head], wrapper, *node.children[tail:]]
    if len(children) == 1:
        # 整行都折进去了，行本身没有存在意义，直接由 wrapper 顶替
        return wrapper.model_copy(update={"grow": node.grow})

    percents = _ratio_percents(node)
    ratios = [
        *percents[:head],
        sum(percents[head:tail]),
        *percents[tail:],
    ]
    return node.model_copy(update={"children": children, "ratios": ratios})


def _longest_needy_run(allocs: list[float], needs: list[float]) -> list[int] | None:
    """找出最长的一段连续「排不下」的子节点；不足两个就没得折。"""
    best: list[int] = []
    current: list[int] = []
    for index, (alloc, need) in enumerate(zip(allocs, needs, strict=True)):
        if alloc + _EPS < need:
            current.append(index)
            if len(current) > len(best):
                best = list(current)
        else:
            current = []
    return best if len(best) >= 2 else None


def _with_allocs(node: FlexContainer, allocs: list[float]) -> FlexContainer:
    total = sum(allocs)
    if total <= 0:
        return node
    return node.model_copy(update={"ratios": [alloc / total * 100.0 for alloc in allocs]})


def _allocs_of(node: FlexContainer, avail_w_pt: float) -> list[float]:
    n = len(node.children)
    inner_total = max(avail_w_pt - node.gap_pt * (n - 1), 1.0)
    return [inner_total * percent / 100.0 for percent in _ratio_percents(node)]


def _ratio_percents(node: FlexContainer) -> list[float]:
    n = len(node.children)
    ratios = node.ratios
    if ratios is None or len(ratios) != n:
        return [100.0 / n] * n
    total = sum(ratios)
    if total <= 0:
        return [100.0 / n] * n
    return [value / total * 100.0 for value in ratios]


def _inset(node: FlexContainer, width_pt: float) -> float:
    if node.preset is None:
        return width_pt
    return max(width_pt - 2 * PRESET_INSET_PT[node.preset], 1.0)


def _min_width_pt(node: FlexNode, ctx: _WidthContext) -> float:
    if isinstance(node, FlexLeaf):
        return _leaf_min_width_pt(node, ctx)
    if not node.children or is_spacer(node):
        return 0.0

    chrome = 2 * PRESET_INSET_PT[node.preset] if node.preset is not None else 0.0
    mins = [ctx.min_width_pt(child) + chrome for child in node.children]
    if node.type == "row":
        return sum(mins) + node.gap_pt * (len(mins) - 1)
    return max(mins)


def _leaf_min_width_pt(leaf: FlexLeaf, ctx: _WidthContext) -> float:
    block = ctx.block_map.get(leaf.block_id)
    if block is None:
        return _MIN_LEAF_WIDTH_PT

    theme = ctx.theme
    box = resolve_box(theme, block.style)
    padding = 2 * box.padding_pt

    def size_of(name: str) -> float:
        return merge_text_style(theme, name, block.style).size_pt

    match block.type:
        case "text":
            return _text_width_pt(block.text, size_of(leaf.text_style or "body")) + padding
        case "bullets":
            size_pt = size_of(leaf.text_style or "bullet")
            widest = max((_text_width_pt(item, size_pt) for item in block.items), default=0.0)
            return widest + BULLET_INDENT_PT + padding
        case "callout":
            # 渲染器按 variant 固定取样式，不看叶子的 text_style
            size_pt = size_of("caption" if block.variant == "source" else "body")
            return _text_width_pt(block.text, size_pt) + 2 * _CARD_PAD_PT
        case "cards":
            size_pt = size_of("body")
            card = max(
                max(_text_width_pt(item.title, size_pt), _text_width_pt(item.desc, size_pt))
                for item in block.items
            )
            n = len(block.items)
            return n * (card + 2 * _CARD_PAD_PT) + (n - 1) * _CARD_GAP_PT
        case "kpi":
            widest = max(
                _text_width_pt(text, size_of(name))
                for text, name in (
                    (block.value, "kpi_value"),
                    (block.label, "kpi_label"),
                    (block.note or "", "kpi_note"),
                )
            )
            return widest + 2 * max(box.padding_pt, _KPI_PAD_PT)
        case "table":
            return max(len(block.header), 1) * _MIN_TABLE_COLUMN_PT
        case "image" | "chart":
            return _MIN_VISUAL_WIDTH_PT

    return _MIN_LEAF_WIDTH_PT


def _text_width_pt(text: str, size_pt: float) -> float:
    """一行至少要排下 MIN_CHARS_PER_LINE 个字；文字本身更短就按它自己算。

    短标题不该被强行要求九个字的宽度，否则一行标题就能撑爆整个版面。
    """
    em = sum(_LATIN_EM if char.isascii() else 1.0 for char in text if not char.isspace())
    return min(MIN_CHARS_PER_LINE, em) * size_pt
