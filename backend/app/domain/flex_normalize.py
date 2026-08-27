"""布局树美学归一化：比值吸附、深度/子数限制、grow 钳制。纯函数，幂等。"""

from __future__ import annotations

from app.domain.flex_layout import FlexContainer, FlexLeaf, FlexNode, is_spacer

RATIO_TOKENS = (33.0, 38.0, 50.0, 62.0, 67.0)
# 只在离设计比值足够近时吸附：无条件吸附会把用户拖出的精确比例改回去
RATIO_SNAP_TOLERANCE = 2.5
GROW_MIN = 0.25
GROW_MAX = 4.0
TITLE_GROW_MAX = 0.5
TITLE_STYLES = frozenset({"display", "title", "subtitle", "caption"})
# 4 层足够容纳「根列 → 行 → 单元格列 → 叶子」：拉伸行内单个单元格的高度
# 需要把该叶子单独包一层列，深度上限太小会把这层包装摊平掉。
MAX_DEPTH = 4
MAX_ROW_CHILDREN = 4


def normalize(tree: FlexContainer, *, clamp_title_grow: bool = True) -> FlexContainer:
    """返回规范化后的新树；normalize(normalize(t)) == normalize(t)。

    clamp_title_grow 为 False 时不再把标题类叶子的 grow 压到 TITLE_GROW_MAX：
    用于高度已由真实文字度量或用户拖拽决定的树，避免把结果改回去。
    """
    return _normalize_container(tree, depth=1, clamp_title=clamp_title_grow)


def _normalize_container(node: FlexContainer, depth: int, *, clamp_title: bool) -> FlexContainer:
    children = [
        _normalize_child(child, depth + 1, clamp_title=clamp_title) for child in node.children
    ]
    if depth >= MAX_DEPTH:
        children = _flatten_container_children(children, clamp_title=clamp_title)
    if node.type == "row":
        children = _enforce_max_row_children(node.id, children)
    children = [_clamp_node_grow(child, clamp_title=clamp_title) for child in children]
    children = _normalize_sibling_grows(children, clamp_title=clamp_title)
    ratios = _normalize_ratios(node.ratios if node.type == "row" else None, len(children))
    self_grow = _clamp_spacer_grow(node.grow) if is_spacer(node) else _clamp_grow(node.grow)
    return node.model_copy(
        update={
            "children": children,
            "ratios": ratios if node.type == "row" else None,
            "grow": self_grow,
        }
    )


def _normalize_child(node: FlexNode, depth: int, *, clamp_title: bool) -> FlexNode:
    if isinstance(node, FlexLeaf):
        return _clamp_leaf(node, clamp_title=clamp_title)
    return _normalize_container(node, depth, clamp_title=clamp_title)


def _flatten_container_children(
    children: list[FlexNode], *, clamp_title: bool = True
) -> list[FlexNode]:
    """超过最大深度时，把更深层的容器摊平到当前层。

    占位容器天生没有 children，摊平时必须整体保留，否则拖拽留出的空白会被吞掉。
    拉伸单元格同理：摊平会让其中的占位块变成同行兄弟，被拉矮的块又弹回满行。
    """
    flat: list[FlexNode] = []
    for child in children:
        if (
            isinstance(child, FlexContainer)
            and not is_spacer(child)
            and not _is_resize_cell(child)
        ):
            for grandchild in child.children:
                if isinstance(grandchild, FlexContainer):
                    flat.extend(
                        _flatten_container_children([grandchild], clamp_title=clamp_title)
                    )
                else:
                    flat.append(_clamp_leaf(grandchild, clamp_title=clamp_title))
        else:
            flat.append(child)
    return flat


def _is_resize_cell(node: FlexContainer) -> bool:
    """前端边手柄拉伸时包出的单元格：gap=0 的列，内含一个占位块吃掉让出的空间。"""
    if node.type != "column" or node.gap_pt != 0:
        return False
    return any(
        isinstance(child, FlexContainer) and is_spacer(child) for child in node.children
    )


def _enforce_max_row_children(parent_id: str, children: list[FlexNode]) -> list[FlexNode]:
    if len(children) <= MAX_ROW_CHILDREN:
        return children
    head = children[: MAX_ROW_CHILDREN - 1]
    tail = children[MAX_ROW_CHILDREN - 1 :]
    wrapped = FlexContainer(
        type="column",
        id=f"{parent_id}__overflow",
        children=tail,
        gap_pt=16.0,
        grow=1.0,
    )
    return [*head, wrapped]


def _clamp_leaf(leaf: FlexLeaf, *, clamp_title: bool = True) -> FlexLeaf:
    grow = _clamp_grow(leaf.grow)
    if clamp_title and leaf.text_style in TITLE_STYLES:
        grow = min(grow, TITLE_GROW_MAX)
    return leaf.model_copy(update={"grow": grow})


def _clamp_node_grow(node: FlexNode, *, clamp_title: bool = True) -> FlexNode:
    if isinstance(node, FlexLeaf):
        return _clamp_leaf(node, clamp_title=clamp_title)
    if is_spacer(node):
        return node.model_copy(update={"grow": _clamp_spacer_grow(node.grow)})
    return node.model_copy(update={"grow": _clamp_grow(node.grow)})


def _clamp_grow(grow: float) -> float:
    return max(GROW_MIN, min(GROW_MAX, grow))


def _clamp_spacer_grow(grow: float) -> float:
    """占位块允许 grow=0，才能把顶/底边拖回满高原位并在保存后保持。"""
    return max(0.0, min(GROW_MAX, grow))


def _normalize_sibling_grows(
    children: list[FlexNode], *, clamp_title: bool = True
) -> list[FlexNode]:
    """标题与 spacer 固定；其余按权重分剩余额度，触边后锁定再分配，保证幂等。"""
    if not children:
        return children
    n = len(children)
    grows: list[float] = []
    locked: list[bool] = []
    for child in children:
        if clamp_title and isinstance(child, FlexLeaf) and child.text_style in TITLE_STYLES:
            grows.append(min(_clamp_grow(child.grow), TITLE_GROW_MAX))
            locked.append(True)
        elif isinstance(child, FlexContainer) and is_spacer(child):
            # 占位空白不参与重平衡；grow 可到 0，避免被抬到 GROW_MIN
            grows.append(_clamp_spacer_grow(child.grow))
            locked.append(True)
        else:
            grows.append(_clamp_grow(child.grow))
            locked.append(False)

    free = [index for index, is_locked in enumerate(locked) if not is_locked]
    has_spacer = any(
        isinstance(child, FlexContainer) and is_spacer(child) for child in children
    )
    for _ in range(n + 2):
        if not free:
            break
        locked_sum = sum(grows[index] for index in range(n) if index not in free)
        weight_sum = sum(grows[index] for index in free)
        # 有 spacer 时保留内容块绝对权重，避免占位把邻居重标扁
        remaining = weight_sum if has_spacer else float(n) - locked_sum
        if remaining <= 0:
            for index in free:
                grows[index] = GROW_MIN
            break
        if weight_sum <= 0:
            equal = remaining / len(free)
            for index in free:
                grows[index] = equal
        else:
            for index in free:
                grows[index] = grows[index] * remaining / weight_sum

        next_free: list[int] = []
        for index in free:
            clamped = _clamp_grow(grows[index])
            if clamped != grows[index]:
                grows[index] = clamped
            else:
                next_free.append(index)
        if len(next_free) == len(free):
            break
        free = next_free

    return [
        child.model_copy(update={"grow": grows[index]})
        for index, child in enumerate(children)
    ]


def _normalize_ratios(ratios: list[float] | None, n: int) -> list[float] | None:
    if n <= 0:
        return None
    if ratios is None or len(ratios) != n:
        return [100.0 / n] * n
    if n == 2:
        return _snap_pair(ratios[0], ratios[1])
    # 多列无稳定双端 token 对，只做比例归一到 sum=100
    total = sum(ratios)
    if total <= 0:
        return [100.0 / n] * n
    if _sums_to_100(total):
        return list(ratios)
    return [r / total * 100.0 for r in ratios]


def _sums_to_100(total: float) -> bool:
    """已经以 100 为基准时跳过除乘，避免每次保存都引入浮点抖动。"""
    return abs(total - 100.0) < 1e-9


def _snap_pair(a: float, b: float) -> list[float]:
    total = a + b
    if total <= 0:
        return [50.0, 50.0]
    pct = a if _sums_to_100(total) else a / total * 100.0
    pairs = [(x, y) for x in RATIO_TOKENS for y in RATIO_TOKENS if abs(x + y - 100.0) < 1e-9]
    best = min(pairs, key=lambda pair: abs(pair[0] - pct))
    if abs(best[0] - pct) <= RATIO_SNAP_TOLERANCE:
        return [best[0], best[1]]
    return [pct, 100.0 - pct]

