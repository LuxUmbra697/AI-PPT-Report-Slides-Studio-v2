"""布局切换的兼容性判定与槽位重映射。

只开放能完整安置当前页所有块的布局；不引入「未放置」块，也不丢弃内容。
匹配结果必须确定可重复，因此按视觉阅读顺序固定候选顺序后再回溯。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.domain.content import BlockType
from app.domain.layout import Layout, Slot, get_layout, load_layouts

_TYPE_LABELS: dict[str, str] = {
    "text": "文字",
    "bullets": "要点",
    "image": "图片",
    "chart": "图表",
    "table": "表格",
    "kpi": "指标",
    "cards": "卡片",
    "callout": "提示",
}


class BlockLike(Protocol):
    id: str
    type: BlockType | str
    slot_id: str


@dataclass(frozen=True)
class LayoutSwitchOk:
    mapping: dict[str, str]


@dataclass(frozen=True)
class LayoutSwitchErr:
    reason: str


LayoutSwitchResult = LayoutSwitchOk | LayoutSwitchErr


@dataclass(frozen=True)
class LayoutCandidate:
    layout_id: str
    name: str
    usage: str
    compatible: bool
    reason: str | None
    current: bool


def _as_block(block: BlockLike | dict[str, Any]) -> tuple[str, str, str]:
    if isinstance(block, dict):
        return str(block["id"]), str(block["type"]), str(block["slot_id"])
    return str(block.id), str(block.type), str(block.slot_id)


def _slot_order_key(slot: Slot) -> tuple[float, float, str]:
    return (slot.rect.y, slot.rect.x, slot.id)


def _sort_slots(slots: list[Slot]) -> list[Slot]:
    return sorted(slots, key=_slot_order_key)


def _sort_blocks(
    blocks: list[tuple[str, str, str]],
    current: Layout,
) -> list[tuple[str, str, str]]:
    """按块在原布局中的视觉位置排序；未知槽位排到最后以保持确定。"""

    def key(item: tuple[str, str, str]) -> tuple[float, float, str]:
        _block_id, _block_type, slot_id = item
        slot = current.slot_by_id(slot_id)
        if slot is None:
            return (1e9, 1e9, slot_id)
        return (slot.rect.y, slot.rect.x, slot.id)

    return sorted(blocks, key=key)


def _type_label(block_type: str) -> str:
    return _TYPE_LABELS.get(block_type, block_type)


def _explain_incompatible(
    blocks: list[tuple[str, str, str]],
    target: Layout,
) -> str:
    # 优先给出类型级原因，便于界面说明「为什么置灰」
    type_counts: dict[str, int] = {}
    for _block_id, block_type, _slot_id in blocks:
        type_counts[block_type] = type_counts.get(block_type, 0) + 1

    for block_type, count in sorted(type_counts.items()):
        capacity = sum(1 for slot in target.slots if block_type in slot.accepts)
        if count > capacity:
            label = _type_label(block_type)
            return f"目标布局最多放 {capacity} 个{label}块，当前页有 {count} 个"

    present = set(type_counts)
    required = [slot for slot in target.slots if slot.required]
    for slot in _sort_slots(required):
        if not any(accepted in present for accepted in slot.accepts):
            labels = "、".join(_type_label(item) for item in slot.accepts)
            return f"目标布局需要{labels}内容，当前页没有"

    if len(blocks) > len(target.slots):
        return f"目标布局只有 {len(target.slots)} 个槽位，当前页有 {len(blocks)} 个内容块"

    if len(blocks) < len(required):
        return f"目标布局需要至少 {len(required)} 个内容块，当前页只有 {len(blocks)} 个"

    return "当前页内容无法完整安置到目标布局的槽位"


def _backtrack(
    blocks: list[tuple[str, str, str]],
    slots: list[Slot],
    used: set[str],
    mapping: dict[str, str],
) -> dict[str, str] | None:
    if len(mapping) == len(blocks):
        required_ok = all((not slot.required) or slot.id in mapping.values() for slot in slots)
        return mapping if required_ok else None

    block_id, block_type, _ = blocks[len(mapping)]
    for slot in slots:
        if slot.id in used:
            continue
        if block_type not in slot.accepts:
            continue
        used.add(slot.id)
        mapping[block_id] = slot.id
        found = _backtrack(blocks, slots, used, mapping)
        if found is not None:
            return found
        del mapping[block_id]
        used.remove(slot.id)
    return None


def plan_layout_switch(
    blocks: list[BlockLike] | list[dict[str, Any]],
    current_layout_id: str,
    target_layout_id: str,
) -> LayoutSwitchResult:
    """判定目标布局是否兼容，并给出块 id → 新 slot_id 的完整映射。"""
    current = get_layout(current_layout_id)
    target = get_layout(target_layout_id)
    normalized = [_as_block(block) for block in blocks]

    # 已在当前布局上：身份映射即可，避免空页/残缺页把「当前」标成不可选
    if target_layout_id == current_layout_id:
        return LayoutSwitchOk({block_id: slot_id for block_id, _type, slot_id in normalized})

    ordered_blocks = _sort_blocks(normalized, current)
    ordered_slots = _sort_slots(list(target.slots))
    mapping = _backtrack(ordered_blocks, ordered_slots, set(), {})
    if mapping is None:
        return LayoutSwitchErr(_explain_incompatible(normalized, target))
    return LayoutSwitchOk(mapping)


def list_layout_candidates(
    blocks: list[BlockLike] | list[dict[str, Any]],
    current_layout_id: str,
) -> list[LayoutCandidate]:
    """返回全部布局的候选列表，供接口直接驱动置灰。"""
    layouts = load_layouts()
    candidates: list[LayoutCandidate] = []
    for layout_id in sorted(layouts):
        layout = layouts[layout_id]
        result = plan_layout_switch(blocks, current_layout_id, layout_id)
        compatible = isinstance(result, LayoutSwitchOk)
        candidates.append(
            LayoutCandidate(
                layout_id=layout.id,
                name=layout.name,
                usage=layout.usage,
                compatible=compatible,
                reason=None if compatible else result.reason,
                current=layout_id == current_layout_id,
            )
        )
    return candidates
