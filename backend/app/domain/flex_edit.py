"""灵活布局编辑：默认块内容、fixed→flex 槽位聚类建树。"""

from __future__ import annotations

from typing import Any, Literal

from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.layout import Layout, Slot

BlockCreateType = Literal[
    "text", "bullets", "image", "chart", "table", "kpi", "cards", "callout"
]

_Y_TOLERANCE = 0.05

_DEFAULT_TEXT_STYLE: dict[str, str] = {
    "title": "title",
    "bullets": "bullet",
    "text": "body",
    "cards": "body",
    "callout": "body",
}


def default_text_style_for_type(block_type: BlockCreateType) -> str | None:
    return _DEFAULT_TEXT_STYLE.get(block_type)


def default_block_dict(block_type: BlockCreateType, block_id: str) -> dict[str, Any]:
    """新建块的最小可用内容；slot_id 与 id 对齐（flex 约定）。"""
    base: dict[str, Any] = {
        "id": block_id,
        "slot_id": block_id,
        "locked": False,
        "style": None,
    }
    if block_type == "text":
        return {**base, "type": "text", "text": "新文本"}
    if block_type == "bullets":
        return {**base, "type": "bullets", "items": ["要点"]}
    if block_type == "image":
        return {
            **base,
            "type": "image",
            "alt": "图片",
            "source": "placeholder",
            "url": None,
            "credit": None,
        }
    if block_type == "chart":
        return {
            **base,
            "type": "chart",
            "chart_type": "bar",
            "categories": ["类别A", "类别B"],
            "series": [{"name": "系列1", "values": [3.0, 5.0]}],
            "unit": None,
        }
    if block_type == "table":
        return {
            **base,
            "type": "table",
            "header": ["列1", "列2"],
            "rows": [["", ""]],
        }
    if block_type == "cards":
        return {
            **base,
            "type": "cards",
            "items": [
                {"title": "要点一", "desc": "补充说明", "icon": None},
                {"title": "要点二", "desc": "补充说明", "icon": None},
            ],
        }
    if block_type == "callout":
        return {
            **base,
            "type": "callout",
            "text": "补充说明或数据来源",
            "icon": None,
            "variant": "note",
        }
    return {
        **base,
        "type": "kpi",
        "value": "—",
        "label": "指标",
        "note": None,
    }


def build_flex_tree_from_fixed(
    layout: Layout,
    blocks: list[dict[str, Any]],
) -> FlexContainer:
    """按槽位几何聚类：相近 y 成行，行内按 x 排序，宽度比作 ratios。"""
    placed: list[tuple[Slot, dict[str, Any]]] = []
    for block in blocks:
        slot = layout.slot_by_id(str(block.get("slot_id", "")))
        if slot is None:
            continue
        placed.append((slot, block))

    placed.sort(key=lambda item: (item[0].rect.y, item[0].rect.x))

    rows: list[list[tuple[Slot, dict[str, Any]]]] = []
    for item in placed:
        if not rows:
            rows.append([item])
            continue
        row_y = rows[-1][0][0].rect.y
        if abs(item[0].rect.y - row_y) <= _Y_TOLERANCE:
            rows[-1].append(item)
        else:
            rows.append([item])

    row_nodes: list[FlexContainer] = []
    for row_index, row in enumerate(rows):
        row.sort(key=lambda item: item[0].rect.x)
        leaves = [
            FlexLeaf(
                id=f"leaf-{block['id']}",
                block_id=str(block["id"]),
                text_style=slot.text_style,
            )
            for slot, block in row
        ]
        widths = [slot.rect.w for slot, _ in row]
        total_w = sum(widths) or 1.0
        ratios = [w / total_w * 100.0 for w in widths] if len(row) > 1 else None
        row_nodes.append(
            FlexContainer(
                type="row",
                id=f"row-{row_index}",
                children=leaves,
                ratios=ratios,
            )
        )

    return FlexContainer(type="column", id="root", children=row_nodes)
