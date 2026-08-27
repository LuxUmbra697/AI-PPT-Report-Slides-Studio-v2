"""改稿结构操作：增删块、改类型。与人手 flex 编辑共用同一套树函数。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from pydantic import TypeAdapter

from app.domain.content import Block
from app.domain.flex_edit import default_block_dict, default_text_style_for_type
from app.domain.flex_layout import (
    FlexContainer,
    FlexLeaf,
    find_leaf_parent,
    insert_leaf,
    insert_leaf_after,
    iter_leaf_block_ids,
    prune_empty_containers,
    remove_leaf_by_block_id,
)
from app.domain.flex_normalize import normalize

_block_adapter = TypeAdapter(Block)

STRUCTURAL_TYPES: frozenset[str] = frozenset(
    {"text", "bullets", "image", "chart", "table", "kpi", "cards", "callout"}
)


class EditStructureError(ValueError):
    """结构工具或 apply 无法执行时的可读原因。"""


def parse_block(raw: dict[str, Any]) -> Block:
    return _block_adapter.validate_python(raw)


def dump_block(block: Block) -> dict[str, Any]:
    return block.model_dump(mode="json")


def previous_block_id(tree: FlexContainer | None, block_id: str) -> str | None:
    if tree is None:
        return None
    ids = iter_leaf_block_ids(tree)
    try:
        index = ids.index(block_id)
    except ValueError:
        return None
    if index <= 0:
        return None
    return ids[index - 1]


def add_block(
    blocks: list[Block],
    tree: FlexContainer,
    *,
    block_type: str,
    after_block_id: str,
    content: dict[str, Any] | None = None,
    block_id: str | None = None,
) -> tuple[list[Block], FlexContainer, Block]:
    if block_type not in STRUCTURAL_TYPES:
        raise EditStructureError(f"不支持的块类型 {block_type}")
    if not any(block.id == after_block_id for block in blocks):
        raise EditStructureError(f"锚点块 {after_block_id} 不存在")

    new_id = block_id or uuid4().hex[:12]
    raw = default_block_dict(block_type, new_id)  # type: ignore[arg-type]
    if content:
        raw.update({key: value for key, value in content.items() if key not in {"id", "slot_id"}})
        raw["id"] = new_id
        raw["slot_id"] = new_id
        raw["type"] = block_type
    block = parse_block(raw)

    draft_tree = tree.model_copy(deep=True)
    leaf = FlexLeaf(
        id=f"leaf-{new_id}",
        block_id=new_id,
        text_style=default_text_style_for_type(block_type),  # type: ignore[arg-type]
    )
    if not insert_leaf_after(draft_tree, after_block_id, leaf):
        raise EditStructureError("无法把新块插入布局树")
    normalized = normalize(draft_tree, clamp_title_grow=False)
    return [*blocks, block], normalized, block


def delete_block(
    blocks: list[Block],
    tree: FlexContainer,
    block_id: str,
) -> tuple[list[Block], FlexContainer, Block]:
    target = next((block for block in blocks if block.id == block_id), None)
    if target is None:
        raise EditStructureError(f"内容块 {block_id} 不存在")
    if target.locked:
        raise EditStructureError("该块已人工修改，AI 不会覆盖")

    leaf_ids = iter_leaf_block_ids(tree)
    if block_id in leaf_ids and len(leaf_ids) <= 1:
        raise EditStructureError("至少保留一个内容块")

    draft_tree = tree.model_copy(deep=True)
    if not remove_leaf_by_block_id(draft_tree, block_id):
        raise EditStructureError("布局树中不存在该内容块")
    pruned = prune_empty_containers(draft_tree)
    if not iter_leaf_block_ids(pruned):
        raise EditStructureError("至少保留一个内容块")
    normalized = normalize(pruned, clamp_title_grow=False)
    remaining = [block for block in blocks if block.id != block_id]
    return remaining, normalized, target


def change_block_type(
    blocks: list[Block],
    tree: FlexContainer | None,
    *,
    block_id: str,
    new_type: str,
    content: dict[str, Any] | None = None,
) -> tuple[list[Block], FlexContainer | None, Block, Block]:
    if new_type not in STRUCTURAL_TYPES:
        raise EditStructureError(f"不支持的块类型 {new_type}")
    original = next((block for block in blocks if block.id == block_id), None)
    if original is None:
        raise EditStructureError(f"内容块 {block_id} 不存在")
    if original.locked:
        raise EditStructureError("该块已人工修改，AI 不会覆盖")
    if original.type == new_type:
        raise EditStructureError("块类型没有变化")

    raw = default_block_dict(new_type, block_id)  # type: ignore[arg-type]
    if content:
        raw.update({key: value for key, value in content.items() if key not in {"id", "slot_id"}})
    raw["id"] = block_id
    raw["slot_id"] = original.slot_id
    raw["type"] = new_type
    raw["locked"] = False
    updated = parse_block(raw)

    replaced = [updated if block.id == block_id else block for block in blocks]
    if tree is None:
        return replaced, None, original, updated

    draft_tree = tree.model_copy(deep=True)
    found = find_leaf_parent(draft_tree, block_id)
    if found is not None:
        _parent, _index, leaf = found
        leaf.text_style = default_text_style_for_type(new_type)  # type: ignore[arg-type]
    normalized = normalize(draft_tree, clamp_title_grow=False)
    return replaced, normalized, original, updated


def restore_block(
    blocks: list[Block],
    tree: FlexContainer,
    *,
    block: Block,
    after_block_id: str | None,
) -> tuple[list[Block], FlexContainer]:
    """把删除的块按原位置插回（apply 点「改动前」）。"""
    if any(item.id == block.id for item in blocks):
        return blocks, tree
    draft_tree = tree.model_copy(deep=True)
    leaf = FlexLeaf(
        id=f"leaf-{block.id}",
        block_id=block.id,
        text_style=default_text_style_for_type(block.type)  # type: ignore[arg-type]
        if block.type in STRUCTURAL_TYPES
        else None,
    )
    if after_block_id and any(item.id == after_block_id for item in blocks):
        ok = insert_leaf_after(draft_tree, after_block_id, leaf)
    else:
        ok = insert_leaf(draft_tree, draft_tree.id, 0, leaf)
    if not ok:
        raise EditStructureError("无法把块插回布局树")
    normalized = normalize(draft_tree, clamp_title_grow=False)
    return [*blocks, block], normalized
