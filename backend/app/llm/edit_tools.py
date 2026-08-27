"""改稿工具：改提案副本，不写库。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool

from app.domain.content import Block
from app.domain.edit_ops import (
    EditStructureError,
    add_block,
    change_block_type,
    delete_block,
    dump_block,
)
from app.domain.flex_layout import FlexContainer
from app.domain.slide_patch import (
    BulletsPatch,
    CalloutPatch,
    CardItemPatch,
    CardsPatch,
    KpiPatch,
    TablePatch,
    TextPatch,
    apply_patches,
    is_editable_block,
)


@dataclass
class EditSession:
    blocks: list[Block]
    tree: FlexContainer | None
    layout_mode: str
    messages: list[str] = field(default_factory=list)

    def by_id(self, block_id: str) -> Block | None:
        return next((block for block in self.blocks if block.id == block_id), None)

    def replace(self, block_id: str, expected_type: str, patch: Any) -> str:
        block = self.by_id(block_id)
        if block is None:
            return f"错误：内容块 {block_id} 不存在"
        if block.locked:
            return "错误：该块已人工修改，AI 不会覆盖"
        if not is_editable_block(block):
            return f"错误：{block.type} 块不支持文字替换"
        if block.type != expected_type:
            return f"错误：块 {block_id} 类型为 {block.type}，不能按 {expected_type} 修改"
        self.blocks = apply_patches(self.blocks, [patch])
        return f"已更新 {expected_type} 块 {block_id}"


def build_edit_tools(session: EditSession) -> list[BaseTool]:
    @tool
    def replace_text(block_id: str, text: str) -> str:
        """替换一个 text 块的全文。"""
        return session.replace(block_id, "text", TextPatch(block_id=block_id, text=text))

    @tool
    def replace_bullets(block_id: str, items: list[str]) -> str:
        """替换一个 bullets 块的全部要点。"""
        return session.replace(block_id, "bullets", BulletsPatch(block_id=block_id, items=items))

    @tool
    def replace_kpi(block_id: str, value: str, label: str, note: str | None = None) -> str:
        """替换一个 kpi 块的数值、标签和备注。"""
        return session.replace(
            block_id, "kpi", KpiPatch(block_id=block_id, value=value, label=label, note=note)
        )

    @tool
    def replace_table(block_id: str, header: list[str], rows: list[list[str]]) -> str:
        """替换一个 table 块的表头和行。"""
        return session.replace(
            block_id, "table", TablePatch(block_id=block_id, header=header, rows=rows)
        )

    @tool
    def replace_cards(
        block_id: str, items: list[dict[str, Any]]
    ) -> str:
        """替换一个 cards 块。items 为 {title, desc, icon?} 列表。"""
        parsed = [
            CardItemPatch(
                title=str(item.get("title", "")),
                desc=str(item.get("desc", "")),
                icon=item.get("icon"),
            )
            for item in items
        ]
        return session.replace(block_id, "cards", CardsPatch(block_id=block_id, items=parsed))

    @tool
    def replace_callout(
        block_id: str, text: str, icon: str | None = None, variant: str = "note"
    ) -> str:
        """替换一个 callout 块。variant 为 note 或 source。"""
        if variant not in {"note", "source"}:
            variant = "note"
        return session.replace(
            block_id,
            "callout",
            CalloutPatch(block_id=block_id, text=text, icon=icon, variant=variant),  # type: ignore[arg-type]
        )

    tools: list[BaseTool] = [
        replace_text,
        replace_bullets,
        replace_kpi,
        replace_table,
        replace_cards,
        replace_callout,
    ]
    if session.layout_mode != "flex" or session.tree is None:
        return tools

    @tool("add_block")
    def add_block_tool(
        after_block_id: str,
        block_type: str,
        text: str | None = None,
        items: list[str] | None = None,
        value: str | None = None,
        label: str | None = None,
        note: str | None = None,
        header: list[str] | None = None,
        rows: list[list[str]] | None = None,
        alt: str | None = None,
        card_items: list[dict[str, Any]] | None = None,
        variant: str | None = None,
        icon: str | None = None,
    ) -> str:
        """在 after_block_id 后面新增一块。flex 页可用。image 只创建占位图。"""
        content: dict[str, Any] = {}
        if text is not None:
            content["text"] = text
        if items is not None:
            content["items"] = items
        if value is not None:
            content["value"] = value
        if label is not None:
            content["label"] = label
        if note is not None:
            content["note"] = note
        if header is not None:
            content["header"] = header
        if rows is not None:
            content["rows"] = rows
        if alt is not None:
            content["alt"] = alt
        if card_items is not None:
            content["items"] = card_items
        if variant is not None:
            content["variant"] = variant
        if icon is not None:
            content["icon"] = icon
        if block_type == "image":
            content.setdefault("alt", alt or "图片")
            content["source"] = "placeholder"
            content["url"] = None
        try:
            session.blocks, session.tree, created = add_block(
                session.blocks,
                session.tree,
                block_type=block_type,
                after_block_id=after_block_id,
                content=content or None,
            )
        except (EditStructureError, Exception) as error:
            return f"错误：{error}"
        return f"已新增 {created.type} 块 {created.id}"

    @tool("delete_block")
    def delete_block_tool(block_id: str) -> str:
        """删除一个内容块。flex 页可用。不能删除已锁定的块，至少保留一块。"""
        assert session.tree is not None
        try:
            session.blocks, session.tree, removed = delete_block(
                session.blocks, session.tree, block_id
            )
        except EditStructureError as error:
            return f"错误：{error}"
        return f"已删除 {removed.type} 块 {block_id}"

    @tool("change_type")
    def change_type_tool(
        block_id: str,
        new_type: str,
        text: str | None = None,
        items: list[str] | None = None,
        value: str | None = None,
        label: str | None = None,
        note: str | None = None,
        header: list[str] | None = None,
        rows: list[list[str]] | None = None,
        alt: str | None = None,
        card_items: list[dict[str, Any]] | None = None,
        variant: str | None = None,
        icon: str | None = None,
    ) -> str:
        """把已有块改成另一种类型，并提供新类型的完整内容。flex 页可用。"""
        content: dict[str, Any] = {}
        if text is not None:
            content["text"] = text
        if items is not None:
            content["items"] = items
        if value is not None:
            content["value"] = value
        if label is not None:
            content["label"] = label
        if note is not None:
            content["note"] = note
        if header is not None:
            content["header"] = header
        if rows is not None:
            content["rows"] = rows
        if alt is not None:
            content["alt"] = alt
        if card_items is not None:
            content["items"] = card_items
        if variant is not None:
            content["variant"] = variant
        if icon is not None:
            content["icon"] = icon
        if new_type == "image":
            content.setdefault("alt", alt or "图片")
            content["source"] = "placeholder"
            content["url"] = None
        try:
            session.blocks, session.tree, _old, updated = change_block_type(
                session.blocks,
                session.tree,
                block_id=block_id,
                new_type=new_type,
                content=content or None,
            )
        except (EditStructureError, Exception) as error:
            return f"错误：{error}"
        return f"已将块 {block_id} 改为 {updated.type}"

    tools.extend([add_block_tool, delete_block_tool, change_type_tool])
    return tools


def sketch_tree(node: FlexContainer) -> dict[str, Any]:
    def walk(item: Any) -> Any:
        if getattr(item, "type", None) == "block":
            return {"block_id": item.block_id}
        return {
            "type": item.type,
            "id": item.id,
            "children": [walk(child) for child in item.children],
        }

    return walk(node)


def block_preview(block: Block) -> dict[str, Any]:
    data = dump_block(block)
    data.pop("style", None)
    return data
