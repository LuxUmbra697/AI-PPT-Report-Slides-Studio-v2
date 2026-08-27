"""单页 AI 局部修改的块级操作。

只允许替换已有可写块的内容：布局槽位是硬约束，AI 自由增删块
会破坏「受约束布局」这条系统纲领。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

from app.domain.content import (
    Block,
    BulletsBlock,
    CalloutBlock,
    CalloutVariant,
    CardItem,
    CardsBlock,
    KpiBlock,
    TableBlock,
    TextBlock,
)

EditableBlockType = Literal["text", "bullets", "kpi", "table", "cards", "callout"]
EDITABLE_BLOCK_TYPES: frozenset[str] = frozenset(
    {"text", "bullets", "kpi", "table", "cards", "callout"}
)


class TextPatch(BaseModel):
    block_id: str
    type: Literal["text"] = "text"
    text: str


class BulletsPatch(BaseModel):
    block_id: str
    type: Literal["bullets"] = "bullets"
    items: list[str]


class KpiPatch(BaseModel):
    block_id: str
    type: Literal["kpi"] = "kpi"
    value: str
    label: str
    note: str | None = None


class TablePatch(BaseModel):
    block_id: str
    type: Literal["table"] = "table"
    header: list[str]
    rows: list[list[str]]


class CardItemPatch(BaseModel):
    title: str
    desc: str
    icon: str | None = None


class CardsPatch(BaseModel):
    block_id: str
    type: Literal["cards"] = "cards"
    items: list[CardItemPatch]


class CalloutPatch(BaseModel):
    block_id: str
    type: Literal["callout"] = "callout"
    text: str
    icon: str | None = None
    variant: CalloutVariant = "note"


BlockPatch = Annotated[
    TextPatch | BulletsPatch | KpiPatch | TablePatch | CardsPatch | CalloutPatch,
    Field(discriminator="type"),
]

_block_patch_list = TypeAdapter(list[BlockPatch])


class DiscardedPatch(BaseModel):
    block_id: str
    reason: str


class PatchFilterResult(BaseModel):
    accepted: list[BlockPatch]
    discarded: list[DiscardedPatch]


def parse_block_patches(raw: object) -> list[BlockPatch]:
    return _block_patch_list.validate_python(raw)


def is_editable_block(block: Block) -> bool:
    return block.type in EDITABLE_BLOCK_TYPES


def unlocked_editable_blocks(blocks: list[Block]) -> list[Block]:
    """可交给模型改写的块：排除 locked，也排除 image/chart。"""
    return [block for block in blocks if is_editable_block(block) and not block.locked]


def filter_patches(blocks: list[Block], patches: list[BlockPatch]) -> PatchFilterResult:
    """丢弃指向 locked / 不存在 / 类型不符的操作，并说明原因。

    生成提案与最终应用都必须走这里，不能只靠提示词约束模型。
    """
    by_id = {block.id: block for block in blocks}
    accepted: list[BlockPatch] = []
    discarded: list[DiscardedPatch] = []
    seen: set[str] = set()

    for patch in patches:
        if patch.block_id in seen:
            discarded.append(
                DiscardedPatch(block_id=patch.block_id, reason="同一块出现重复操作，已忽略后续项")
            )
            continue
        seen.add(patch.block_id)

        block = by_id.get(patch.block_id)
        if block is None:
            discarded.append(DiscardedPatch(block_id=patch.block_id, reason="内容块不存在"))
            continue
        if not is_editable_block(block):
            discarded.append(
                DiscardedPatch(block_id=patch.block_id, reason="该类型块不支持 AI 文字修改")
            )
            continue
        if block.locked:
            discarded.append(
                DiscardedPatch(
                    block_id=patch.block_id,
                    reason="该块已人工修改，AI 不会覆盖",
                )
            )
            continue
        if block.type != patch.type:
            discarded.append(
                DiscardedPatch(
                    block_id=patch.block_id,
                    reason=f"块类型不匹配，当前为 {block.type}，不能按 {patch.type} 修改",
                )
            )
            continue
        # 模型有时会原样回抄一个块。这类空操作不进 discarded：
        # 它对用户没有信息量，列出来只会让预览界面显得像出了错。
        if content_snapshot(block) == patch:
            continue
        accepted.append(patch)

    return PatchFilterResult(accepted=accepted, discarded=discarded)


def apply_patches(blocks: list[Block], patches: list[BlockPatch]) -> list[Block]:
    """把操作清单应用到块列表的副本上；幂等且不就地修改入参。"""
    by_id = {patch.block_id: patch for patch in patches}
    result: list[Block] = []
    for block in blocks:
        patch = by_id.get(block.id)
        if patch is None:
            result.append(block.model_copy(deep=True))
            continue
        result.append(_apply_one(block, patch))
    return result


def content_snapshot(
    block: Block,
) -> TextPatch | BulletsPatch | KpiPatch | TablePatch | CardsPatch | CalloutPatch:
    """抽出块的可写内容，供提案 before/after 对比。"""
    match block:
        case TextBlock():
            return TextPatch(block_id=block.id, text=block.text)
        case BulletsBlock():
            return BulletsPatch(block_id=block.id, items=list(block.items))
        case KpiBlock():
            return KpiPatch(
                block_id=block.id,
                value=block.value,
                label=block.label,
                note=block.note,
            )
        case TableBlock():
            return TablePatch(
                block_id=block.id,
                header=list(block.header),
                rows=[list(row) for row in block.rows],
            )
        case CardsBlock():
            return CardsPatch(
                block_id=block.id,
                items=[
                    CardItemPatch(title=item.title, desc=item.desc, icon=item.icon)
                    for item in block.items
                ],
            )
        case CalloutBlock():
            return CalloutPatch(
                block_id=block.id,
                text=block.text,
                icon=block.icon,
                variant=block.variant,
            )
        case _:
            raise TypeError(f"块类型 {block.type} 不支持内容快照")


def _apply_one(block: Block, patch: BlockPatch) -> Block:
    match block, patch:
        case TextBlock(), TextPatch():
            return block.model_copy(update={"text": patch.text})
        case BulletsBlock(), BulletsPatch():
            return block.model_copy(update={"items": list(patch.items)})
        case KpiBlock(), KpiPatch():
            return block.model_copy(
                update={"value": patch.value, "label": patch.label, "note": patch.note}
            )
        case TableBlock(), TablePatch():
            return block.model_copy(
                update={
                    "header": list(patch.header),
                    "rows": [list(row) for row in patch.rows],
                }
            )
        case CardsBlock(), CardsPatch():
            return block.model_copy(
                update={
                    "items": [
                        CardItem(title=item.title, desc=item.desc, icon=item.icon)
                        for item in patch.items
                    ]
                }
            )
        case CalloutBlock(), CalloutPatch():
            return block.model_copy(
                update={
                    "text": patch.text,
                    "icon": patch.icon,
                    "variant": patch.variant,
                }
            )
        case _:
            raise TypeError(f"无法将 {patch.type} 操作应用到 {block.type} 块")
